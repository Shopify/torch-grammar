import sys


class ParseState:
    def __init__(self):
        self.symbol_ids = {}
        self.out_grammar = []


def get_symbol_id(state, src):
    if src not in state.symbol_ids:
        state.symbol_ids[src] = len(state.symbol_ids)
    return state.symbol_ids[src]


def generate_symbol_id(state, base_name):
    next_id = len(state.symbol_ids)
    state.symbol_ids[base_name + "_" + str(next_id)] = next_id
    return next_id


def is_word_char(c):
    return c.isalnum() or c == "-" or c == "_"


def hex_to_int(c):
    if c.isdigit():
        return int(c)
    elif "a" <= c.lower() <= "f":
        return ord(c.lower()) - ord("a") + 10
    return -1


def parse_space(src, newline_ok):
    pos = 0
    while pos < len(src) and (src[pos].isspace() or src[pos] == "#"):
        if src[pos] == "#":
            while pos < len(src) and src[pos] not in ("\r", "\n"):
                pos += 1
        else:
            if not newline_ok and src[pos] in ("\r", "\n"):
                break
            pos += 1
    return src[pos:]


def parse_name(src):
    pos = 0
    while pos < len(src) and is_word_char(src[pos]):
        pos += 1
    if pos == 0:
        raise RuntimeError("expecting name at " + src)
    return src[:pos], src[pos:]


def parse_char(src):
    if src[0] == "\\":
        esc = src[1]
        if esc == "x":
            first = hex_to_int(src[2])
            if first > -1:
                second = hex_to_int(src[3])
                if second > -1:
                    return (first << 4) + second, src[4:]
            raise RuntimeError("expecting \\xNN at " + src)
        elif esc in ('"', "[", "]"):
            return esc, src[2:]
        elif esc == "r":
            return "\r", src[2:]
        elif esc == "n":
            return "\n", src[2:]
        elif esc == "t":
            return "\t", src[2:]
        raise RuntimeError("unknown escape at " + src)
    elif src:
        return src[0], src[1:]
    raise RuntimeError("unexpected end of input")


def parse_sequence(state, src, rule_name, outbuf, is_nested):
    out_start = len(outbuf)

    # sequence size, will be replaced at end when known
    outbuf.append(0)

    last_sym_start = len(outbuf)
    pos = src
    while pos:
        if pos[0] == '"':  # literal string
            pos = pos[1:]
            last_sym_start = len(outbuf)
            while pos[0] != '"':
                char_pair, pos = parse_char(pos)

                # each char of a literal is encoded as a "range" of char - char
                outbuf.append(2)
                outbuf.append(ord(char_pair))
                outbuf.append(ord(char_pair))
            pos = parse_space(pos[1:], is_nested)
        elif pos[0] == "[":  # char range(s)
            pos = pos[1:]
            last_sym_start = len(outbuf)
            # num chars in range - replaced at end of loop
            outbuf.append(0)
            while pos[0] != "]":
                char_pair, pos = parse_char(pos)

                outbuf.append(ord(char_pair))
                if pos[0] == "-" and pos[1] != "]":
                    endchar_pair, pos = parse_char(pos[1:])
                    outbuf.append(ord(endchar_pair))
                else:
                    # chars that aren't part of a c1-c2 range are just doubled (i.e., c-c)
                    outbuf.append(ord(char_pair))
            # replace num chars with actual
            outbuf[last_sym_start] = len(outbuf) - last_sym_start - 1
            pos = parse_space(pos[1:], is_nested)
        elif is_word_char(pos[0]):  # rule reference
            name, pos = parse_name(pos)
            ref_rule_id = get_symbol_id(state, name)
            pos = parse_space(pos, is_nested)
            last_sym_start = len(outbuf)
            outbuf.append(1)
            outbuf.append(ref_rule_id)
        elif pos[0] == "(":  # grouping
            # parse nested alternates into synthesized rule
            pos = parse_space(pos[1:], True)
            sub_rule_id = generate_symbol_id(state, rule_name)
            pos = parse_alternates(state, pos, rule_name, sub_rule_id, True)
            last_sym_start = len(outbuf)
            # output reference to synthesized rule
            outbuf.append(1)
            outbuf.append(sub_rule_id)
            if pos[0] != ")":
                raise RuntimeError("expecting ')' at " + pos)
            pos = parse_space(pos[1:], is_nested)
        elif pos[0] in ("*", "+", "?"):  # repetition operator
            if len(outbuf) - out_start - 1 == 0:
                raise RuntimeError("expecting preceeding item to */+/? at " + pos)
            out_grammar = state.out_grammar

            # apply transformation to previous symbol (last_sym_start -
            # end) according to rewrite rules:
            # S* --> S' ::= S S' |
            # S+ --> S' ::= S S' | S
            # S? --> S' ::= S |
            sub_rule_id = generate_symbol_id(state, rule_name)
            out_grammar.append(sub_rule_id)
            sub_rule_start = len(out_grammar)
            # placeholder for size of 1st alternate
            out_grammar.append(0)
            # add preceding symbol to generated rule
            out_grammar.extend(outbuf[last_sym_start:])
            if pos[0] in ("*", "+"):
                # cause generated rule to recurse
                out_grammar.append(1)
                out_grammar.append(sub_rule_id)
            # apply actual size
            out_grammar[sub_rule_start] = len(out_grammar) - sub_rule_start
            # mark end of 1st alternate
            out_grammar.append(0)
            sub_rule_start = len(out_grammar)
            # placeholder for size of 2nd alternate
            out_grammar.append(0)
            if pos[0] == "+":
                # add preceding symbol as alternate only for '+'
                out_grammar.extend(outbuf[last_sym_start:])
            # apply actual size of 2nd alternate
            out_grammar[sub_rule_start] = len(out_grammar) - sub_rule_start
            # mark end of 2nd alternate, then end of rule
            out_grammar.append(0)
            out_grammar.append(0)

            # in original rule, replace previous symbol with reference to generated rule
            outbuf[last_sym_start:] = [1, sub_rule_id]

            pos = parse_space(pos[1:], is_nested)
        else:
            break
    # apply actual size of this alternate sequence
    outbuf[out_start] = len(outbuf) - out_start
    # mark end of alternate
    outbuf.append(0)
    return pos


def parse_alternates(state, src, rule_name, rule_id, is_nested):
    outbuf = []
    pos = parse_sequence(state, src, rule_name, outbuf, is_nested)
    while pos[0] == "|":
        pos = parse_space(pos[1:], True)
        pos = parse_sequence(state, pos, rule_name, outbuf, is_nested)
    state.out_grammar.append(rule_id)
    state.out_grammar.extend(outbuf)
    state.out_grammar.append(0)
    return pos


def parse_rule(state, src):
    name, pos = parse_name(src)
    pos = parse_space(pos, False)
    rule_id = get_symbol_id(state, name)

    if pos[:3] != "::=":
        raise RuntimeError("expecting ::= at " + pos)
    pos = parse_space(pos[3:], True)

    pos = parse_alternates(state, pos, name, rule_id, False)

    if pos[0] == "\r":
        pos = pos[2:] if pos[1] == "\n" else pos[1:]
    elif pos[0] == "\n":
        pos = pos[1:]
    elif pos:
        raise RuntimeError("expecting newline or end at " + pos)
    return parse_space(pos, True)


def parse(src):
    try:
        state = ParseState()
        pos = parse_space(src, True)
        while pos:
            pos = parse_rule(state, pos)
        state.out_grammar.append(0xFFFF)
        return state
    except RuntimeError as err:
        print("error parsing grammar:", err)
        return ParseState()


def print_rule(file, base, index, symbol_id_names):
    rule_id = base[index]
    print("<{}>{} ::=".format(index, symbol_id_names[rule_id]), end=" ", file=file)
    pos = index + 1
    while base[pos]:
        if pos - 1 > index:
            print("|", end=" ", file=file)
        pos += 1  # sequence size, not needed here
        while base[pos]:
            if base[pos] == 1:
                ref_rule_id = base[pos + 1]
                print(
                    "<{}>{}".format(pos, symbol_id_names[ref_rule_id]),
                    end=" ",
                    file=file,
                )
                pos += 2
            else:
                print("<{}>[".format(pos), end="", file=file)
                num_chars = base[pos]
                pos += 1

                for i in range(0, num_chars, 2):
                    print("{}-".format(chr(base[pos + i])), end="", file=file)
                    if i + 1 < num_chars:
                        print("{}".format(chr(base[pos + i + 1])), end="", file=file)
                print("]", end=" ", file=file)
                pos += num_chars
        pos += 1
    print(file=file)
    return pos + 1


def print_grammar(file, state):
    pos = 0
    symbol_id_names = {v: k for k, v in state.symbol_ids.items()}
    while state.out_grammar[pos] != 0xFFFF:
        pos = print_rule(file, state.out_grammar, pos, symbol_id_names)
    pos = 0
    while state.out_grammar[pos] != 0xFFFF:
        print(f"{state.out_grammar[pos]:04x}", end=" ", file=file)
        pos += 1
    print("ffff\n")


if __name__ == "__main__":
    try:
        with open("examples/grammar.ebnf", "r") as file:
            input_text = file.read()
        state = parse(input_text)
        print_grammar(sys.stdout, state)
        print(state.symbol_ids)
    except FileNotFoundError:
        print("Error: File 'grammar.ebnf' not found.")
    except IOError as e:
        print("Error reading file 'grammar.ebnf':", e)
