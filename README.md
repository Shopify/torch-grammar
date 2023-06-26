# torch-grammar

**Alpha Quality: This might do what you want. It's likely to not do what you
want. Please open issues!**

Torch-Grammar restricts a model to output a token sequence that conforms to a
provided EBNF grammar.

For example:

```python
import torch
from torch_grammar import GrammarSampler
from transformers import LlamaTokenizer
tokenizer = LlamaTokenizer.from_pretrained("huggyllama/llama-7b")

with open("examples/grammar.ebnf", "r") as file:
    input_text = file.read()
grammar = GrammarSampler(input_text, "root", tokenizer)

ids = [[1]]
logits_processor = grammar.logits_processor()

vocab_size = len(tokenizer.get_vocab())
for i in range(10):
  logits = torch.randn((1, vocab_size))
  logits = logits_processor(ids, logits)
  token = torch.argmax(logits).item()
  # logits_processor.accept_token(token)
  ids[0].append(token)
print(f"\x1b[1mfirst 10 tokens: \x1b[1;35m{tokenizer.decode(ids[0])}\x1b[0m")
```

`logits_processor` is meant to be passed to `model.generate` in a HuggingFace
transformers model but this integration is not yet super clean. Take a look at
the notebook in this repo for more info.

### TODO / possible features

* UTF-8 support... a bit of fiddling but not terribly hard
* More expressive grammars... lookahead would be challenging.
* Easier integration with various tokenizers... LLaMA works well; T5 presents
  significant challenges; haven't even tried others.
* Testing and automatic benchmarking.
* Binary parse is probably not carrying its weight with all the caching and
  precomputation we're doing now; it should be rewritten to something less
  confusing. In fact it might work to just hijack Lark or something?

### Broken seeds

* 11833882144218229242

### Related Work

The code was originally adapted from
https://github.com/ggerganov/llama.cpp/pull/1773. In particular, the grammar
parser is a pretty straightforward mechanical translation and the binary grammar
format is identical.
