import os
import sys
import re
from functools import lru_cache
from typing import List
from dataclasses import dataclass

from lark import Lark, ast_utils, Transformer, v_args
from lark.tree import Meta

this_module = sys.modules[__name__]

class _Ast(ast_utils.Ast):
    # This will be skipped by create_transformer(), because it starts with an underscore
    pass

@dataclass
class RuleId(_Ast):
    name: str

@dataclass
class Rule(_Ast, ast_utils.WithMeta):
    meta: Meta # line number, etc.
    id: RuleId
    expansion: _Ast

@dataclass
class Alternate(_Ast, ast_utils.AsList):
    choices: List[_Ast]

@dataclass
class Sequence(_Ast, ast_utils.AsList):
    terms: List[_Ast]

@dataclass
class CharClass(_Ast):
    chars: _Ast

@dataclass
class OneOrMore(_Ast):
    of: _Ast

@dataclass
class ZeroOrMore(_Ast):
    of: _Ast

@dataclass
class ZeroOrOne(_Ast):
    of: _Ast


import re

def get_escaped_char(s, i):
    if i < len(s) and s[i] == '\\':
        if i + 1 < len(s) and (s[i + 1] == ']' or s[i + 1] == '-'):
            return s[i + 1], i + 2
    return None, i

ESCAPE_MAP = {
    ']': ']',
    '-': '-',
    't': '\t',
    'n': '\n',
    '[': '['
}

def get_escaped_char(s, i):
    if i < len(s) and s[i] == '\\' and i + 1 < len(s) and s[i + 1] in ESCAPE_MAP:
        return ESCAPE_MAP[s[i + 1]], i + 2
    return None, i

def get_hex_char(s, i):
    match = re.match(r'#x([0-9a-fA-F]{2})', s[i:])
    if match:
        char_code = int(match.group(1), 16)
        return chr(char_code), i + len(match.group(0))
    return None, i

def process_char_class(s):
    result = []
    i = 0
    while i < len(s):
        char, new_i = get_escaped_char(s, i)
        if not char:
            char, new_i = get_hex_char(s, i)
        if not char:
            char, new_i = s[i], i + 1

        if new_i < len(s) and s[new_i] == '-':
            next_char, new_i_next = get_escaped_char(s, new_i + 1)
            if not next_char:
                next_char, new_i_next = get_hex_char(s, new_i + 1)
            if not next_char:
                next_char, new_i_next = s[new_i + 1], new_i + 2

            result.append((char, next_char))
            i = new_i_next
        else:
            result.append(char)
            i = new_i
    return result

class ToAst(Transformer):
    def RULE_ID(self, s):
        return s.value

    def CHAR_CLASS(self, s):
        return process_char_class(s[1:-1])

    def ESCAPED_STRING(self, s):
        return s[1:-1].encode().decode("unicode_escape")

    @v_args(inline=True)
    def start(self, *defs):
        return defs

transformer = ast_utils.create_transformer(this_module, ToAst())

@lru_cache(maxsize=1)
def parser():
    source_dir = os.path.dirname(os.path.abspath(__file__))
    ebnf_path = os.path.join(source_dir, "ebnf.lark")
    with open(ebnf_path, "r") as f:
        return Lark(f.read())

def parse(text):
    tree = parser().parse(text)
    return transformer.transform(tree)

if __name__ == "__main__":
    ast = parse("""
    root      ::= (commands eol)+
    commands  ::=  info | nav
    nav       ::= "nav(\\"/" [a-z/]*  "\\")"
    info      ::= "info(" string ")"

    # comments
    color     ::= "\\"#" (hex hex hex (hex hex hex)?) "\\""
    hex       ::= [0-9a-fA-F]
    json_path ::= "\\"" [a-zA-Z0-9._\-]+ "\\""
    string    ::= "\\"" ([ \\t!#-\\[#x5D-~|\n] | ("\\\\\\""))* "\\""
    number    ::= ([0-9.] | "-")+
    boolean   ::= ("true" | "false")
    eol       ::= "\\n"
    """)

    print("=================================================================")
    for node in ast:
        print(node)
        print("")
