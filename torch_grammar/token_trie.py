import re

LEAF = -1


class TokenTrie:
    def __init__(self, tokenizer):
        self.eos_token_id = tokenizer.eos_token_id
        self.tokens = []
        self.trie = {}
        self.load_tokens(tokenizer)

    def id2str(self, token_id):
        return self.tokens[token_id]

    def __len__(self):
        return len(self.tokens)

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
            self.insert_into_trie(self.trie, token_bytes, token_id)

    def insert_into_trie(self, trie, token_bytes, token_id):
        current = trie
        for byte in token_bytes:
            if byte not in current:
                current[byte] = {}
            current = current[byte]
        current[LEAF] = token_id
