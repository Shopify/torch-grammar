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

        if "gpt2" in tokenizer.__class__.__name__.lower():
            special = tokenizer.additional_special_tokens_ids

            def fmt_token(id):
                if id in special:
                    return None
                return bytes(tokenizer.decode([id]), "utf-8")

        elif "llama" in tokenizer.__class__.__name__.lower():

            def fmt_token(id):
                token = tokenizer.convert_ids_to_tokens(id)
                token = re.sub(r"<0x([0-9a-fA-F]{2})>", replace_hex, token)
                token = token.replace("▁", " ")
                return bytes(token, "utf-8")

        else:
            print("Warning: unrecognized tokenizer: using default token formatting")

            def fmt_token(id):
                token = tokenizer.convert_ids_to_tokens(id)
                return bytes(token, "utf-8")

        self.tokens = [fmt_token(i) for i in range(tokenizer.vocab_size)]
        for token_id, token_bytes in enumerate(self.tokens):
            if token_bytes is not None:
                self.insert_into_trie(self.trie, token_bytes, token_id)

    def insert_into_trie(self, trie, token_bytes, token_id):
        current = trie
        for byte in token_bytes:
            if byte not in current:
                current[byte] = {}
            current = current[byte]
        current[LEAF] = token_id
