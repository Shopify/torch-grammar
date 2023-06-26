from math import inf
from . import grammar_parser
from .token_trie import TokenTrie, LEAF
from functools import lru_cache
import time
import torch


class LogitsProcessor:
    def __init__(self, grammar):
        self.grammar = grammar
        self.stacks = grammar.init_stacks()
        self.last_size = None

    def accept_token(self, token):
        self.stacks = self.grammar.accept_token(token, self.stacks)

    # TODO: batching
    def __call__(self, input_ids, scores):
        if self.last_size is None:
            pass
        elif len(input_ids[0]) == self.last_size + 1:
            self.stacks = self.grammar.accept_token(input_ids[0][-1], self.stacks)
        else:
            raise "Input size changed"

        # TODO: the <s> token should be accounted for directly rather than just
        # dropped here...
        self.grammar.filter_logits(scores[0], self.stacks)

        self.last_size = len(input_ids[0])
        return scores


class GrammarSampler:
    def __init__(self, input_text, start_rule_name, tokenizer):
        self.tt = 0
        self.nt = 0
        state = grammar_parser.parse(input_text)
        src = state.out_grammar
        self.start_rule_id = state.symbol_ids.get(start_rule_name)

        self.eos_token_id = tokenizer.eos_token_id
        self.token_trie = TokenTrie(tokenizer)
        self.src = src

        pos = 0
        rules = []

        while src[pos] != 0xFFFF:
            rule_id = src[pos]
            if len(rules) <= rule_id:
                rules.extend([None] * (rule_id + 1 - len(rules)))
            rules[rule_id] = pos
            pos += 1
            while src[pos]:
                pos += 1 + src[pos]
            pos += 1

        self.start_rule = rules[self.start_rule_id]
        self.rules = rules

    def logits_processor(self):
        return LogitsProcessor(self)

    def init_stacks(self):
        stack = [self.start_rule + 2]
        return self.advance_stack(tuple(stack))

    @lru_cache(maxsize=8000)
    def advance_stack(self, stack):
        stack = list(stack)
        if len(stack) == 0:
            return [stack]

        pos = stack[-1]

        if self.src[pos] > 1:
            return [stack]

        # The stack head is a nonterminal (a rule reference).
        # Resolving this rule gives a set of one or more possible positions
        # (e.g. two in `a ::= b | c`)
        # We pop the current rule off the stack and, for each option, push:
        # - the symbol following this symbol in the current rule; then
        # - the first symbol of the resolved rule.
        referenced_rule_id = self.src[pos + 1]
        subpos = self.rules[referenced_rule_id] + 1
        stacks = []
        while self.src[subpos]:
            new_stack = stack[:-1]
            if self.src[pos + 2]:
                new_stack.append(pos + 2)
            if self.src[subpos + 1]:
                new_stack.append(subpos + 1)
            stacks.extend(self.advance_stack(tuple(new_stack)))
            subpos += 1 + self.src[subpos]
        return stacks

    def accept(self, byte, stacks):
        new_stacks = []
        for stack in stacks:
            if not stack:
                continue

            pos = stack[-1]
            num_chars = self.src[pos]

            pos += 1
            found = False
            for i in range(0, num_chars, 2):
                if self.src[pos + i] <= byte and byte <= self.src[pos + i + 1]:
                    found = True
                    break
            if not found:
                continue

            pos += num_chars
            new_stack = stack[:-1]
            if self.src[pos]:
                new_stack.append(pos)
            new_stacks.extend(self.advance_stack(tuple(new_stack)))

        return new_stacks

    def accept_token(self, token, stacks):
        if token == self.eos_token_id:
            if any(len(stack) == 0 for stack in stacks):
                return []
            raise Exception(f"EOS token not accepted with PDA stacks: {stacks}")

        for byte in self.token_trie.id2str(token):
            stacks = self.accept(byte, stacks)
            assert stacks != []

        return stacks

    @lru_cache(maxsize=None)
    def pos_char_acceptance(self, pos):
        acceptance = [False] * 256
        num_chars = self.src[pos]
        pos += 1
        for i in range(0, num_chars, 2):
            start = self.src[pos + i]
            end = self.src[pos + i + 1]
            for j in range(start, end + 1):
                acceptance[j] = True
        return acceptance

    @lru_cache(maxsize=1024)
    def token_acceptance_for_stack(self, stack):
        st = time.time()
        stack = list(stack)  # needs to come in as a tuple for lru_cache

        accepts = [False] * len(self.token_trie)
        accepts[self.eos_token_id] = len(stack) == 0

        def traverse_trie(trie, stacks):
            for byte, next_trie in trie.items():
                if byte == LEAF:
                    token_id = next_trie
                    if token_id != self.eos_token_id:
                        accepts[token_id] = bool(stacks)
                    continue

                new_stacks = []
                for stk in stacks:
                    if not stk:
                        continue

                    pos = stk[-1]
                    num_chars = self.src[pos]

                    if not self.pos_char_acceptance(pos)[byte]:
                        continue

                    pos += num_chars + 1
                    new_stack = stk[:-1]
                    if self.src[pos]:
                        new_stack.append(pos)
                    new_stacks.extend(self.advance_stack(tuple(new_stack)))

                if new_stacks:
                    traverse_trie(next_trie, new_stacks)

        traverse_trie(self.token_trie.trie, [stack])

        et = time.time() - st
        x = torch.tensor(accepts, dtype=torch.bool)
        self.tt += et
        self.nt += 1
        return x

    def filter_logits(self, logits, stacks):
        # resolve each stack to a tensor of True/False for each token
        # indicating acceptance
        acceptance = torch.cat(
            [self.token_acceptance_for_stack(tuple(stack)) for stack in stacks]
        )
        # Merge stacks: any True => True
        acceptance = acceptance.reshape(len(stacks), -1).any(dim=0)
        # Logits to -inf where False
        logits[~acceptance] = -inf
