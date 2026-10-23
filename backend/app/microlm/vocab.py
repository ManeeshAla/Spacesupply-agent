from __future__ import annotations

from .catalog import COMPONENT_NAMES, SUPPLIER_NAMES, TASK_PHRASES, WS_NAMES
from .dataset import norm_token, tokenize

PAD, UNK, BOS, EOS = "<pad>", "<unk>", "<bos>", "<eos>"
SPECIALS = [PAD, UNK, BOS, EOS]


def build_vocab(samples) -> list[str]:
    words = {norm_token(t) for toks, _, _ in samples for t in toks}
    for phrase in COMPONENT_NAMES + TASK_PHRASES + SUPPLIER_NAMES + WS_NAMES:
        words |= {norm_token(t) for t in tokenize(phrase)}
    words |= {"<cmp>", "<ws>", "<tid>", "<num>", "one", "two", "three", "four"}
    return SPECIALS + sorted(words - set(SPECIALS))


def encode(tokens: list[str], w2i: dict[str, int]) -> list[int]:
    return [w2i[BOS]] + [w2i.get(norm_token(t), w2i[UNK]) for t in tokens] + [w2i[EOS]]
