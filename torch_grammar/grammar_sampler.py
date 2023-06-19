import re
from math import inf
from . import grammar_parser
from functools import lru_cache
import time
import torch

class LogitsProcessor:
    def __init__(self, grammar):
        self.grammar = grammar
        self.stacks = grammar.init_stacks()
        self.last_size = 0

    def accept_token(self, token):
        self.stacks = self.grammar.accept_token(token, self.stacks)

    def __call__(self, input_ids, scores):
        if len(input_ids[0]) != self.last_size + 1:
            raise "Input size changed"
        if self.last_size != 0:
            self.stacks = self.grammar.accept_token(input_ids[0][-1], self.stacks)

        # TODO: the <s> token should be accounted for directly rather than just
        # dropped here...
        self.grammar.filter_logits(input_ids[0][1:], scores, self.stacks)

        self.last_size += 1
        return scores


class GrammarSampler:
    def __init__(self, input_text, start_rule_name, tokenizer):
        self.tt = 0
        self.nt = 0
        state = grammar_parser.parse(input_text)
        src = state.out_grammar
        self.start_rule_id = state.symbol_ids.get(start_rule_name)

        self.eos_token_id = tokenizer.eos_token_id
        self.tokens_trie = {}
        self.load_tokens(tokenizer)
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

    def insert_into_trie(self, trie, token_bytes, token_id):
        current = trie
        for byte in token_bytes:
            if byte not in current:
                current[byte] = {}
            current = current[byte]
        current[-1] = token_id

    def load_tokens(self, tokenizer):
        def replace_hex(match):
            hex_value = match.group(1)
            return chr(int(hex_value, 16))

        def fmt_token(token):
            token = re.sub(r"<0x([0-9a-fA-F]{2})>", replace_hex, token)
            token = token.replace("▁", " ")
            return bytes(token, "utf-8")

        self.tokens = [
            fmt_token(tokenizer.convert_ids_to_tokens(i))
            for i in range(tokenizer.vocab_size)
        ]
        for token_id, token_bytes in enumerate(self.tokens):
            self.insert_into_trie(self.tokens_trie, token_bytes, token_id)

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
            assert False

        for byte in self.tokens[token]:
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

        accepts = [False] * len(self.tokens)
        accepts[self.eos_token_id] = len(stack) == 0

        def traverse_trie(trie, stacks):
            for byte, next_trie in trie.items():
                if byte == -1:
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

        traverse_trie(self.tokens_trie, [stack])

        et = time.time() - st
        x = torch.tensor(accepts, dtype=torch.bool)
        self.tt += et
        self.nt += 1
        return x

    def debug_stacks(self, stacks):
        print("\x1b[1;35m/========== STACK DEBUG =============")
        for stack in stacks:
            n_els = self.src[stack[-1]]
            stuff = self.src[stack[-1] : stack[-1] + n_els + 1]
            if stuff[0] == 1:
                print(f"| \x1b[3m{stack} -- rule#{stuff[1]}\x1b[0m")
            else:
                char_ranges = stuff[1:]
                # each pair of elements is a range of chars (e.g. 97,122 for a-z).
                # print them like a regex... e.g. 97,122,95,95,32,32 is [a-z_ ]
                regex_str = "["
                for i in range(0, len(char_ranges), 2):
                    start, end = char_ranges[i], char_ranges[i + 1]
                    if start == end:
                        regex_str += chr(start)
                    else:
                        regex_str += f"{chr(start)}-{chr(end)}"
                regex_str += "]"
                print(f"| {stack} -- {regex_str}")
        print("\\========== / STACK DEBUG ===========\x1b[0m")

    def filter_logits(self, input_ids, logits, stacks):
        # resolve each stack to a tensor of True/False for each token
        # indicating acceptance
        acceptance = torch.cat(
            [self.token_acceptance_for_stack(tuple(stack)) for stack in stacks]
        )
        # Merge stacks: any True => True
        acceptance = acceptance.reshape(len(stacks), -1).any(dim=0)
        # Logits to -inf where False
        logits[0, ~acceptance] = -inf