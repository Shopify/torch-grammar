import unittest
import torch
from transformers import LlamaTokenizer
from torch_grammar import GrammarSampler


class TestGrammarSampler(unittest.TestCase):
    def test_generated_tokens(self):
        # Set the seed
        torch.manual_seed(17804610096251488775)

        # Initialize tokenizer and grammar
        tokenizer = LlamaTokenizer.from_pretrained("huggyllama/llama-7b")
        with open("examples/grammar.ebnf", "r") as file:
            input_text = file.read()
        grammar = GrammarSampler(input_text, "root", tokenizer)

        # Initialize ids and logits_processor
        ids = [[1]]
        logits_processor = grammar.logits_processor()

        # Generate tokens
        for i in range(10):
            logits = torch.randn((1, len(tokenizer.get_vocab())))
            logits = logits_processor(ids, logits)
            token = torch.argmax(logits).item()
            ids[0].append(token)

        # Check if the generated tokens match the expected output
        expected_output = "<s>info(_angolbez prinighteriert reactainingchild"
        self.assertEqual(tokenizer.decode(ids[0]), expected_output)


if __name__ == "__main__":
    unittest.main()
