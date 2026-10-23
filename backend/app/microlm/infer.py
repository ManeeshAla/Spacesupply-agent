"""Run-time wrapper around the trained Micro LM."""
from __future__ import annotations

import re
import threading
import time

import torch

from ..config import MICROLM_PATH
from .dataset import norm_token, tokenize
from .model import MicroLM
from .vocab import BOS, EOS, SPECIALS, UNK

KEYWORD_PRIOR = [  # used ONLY when the model is unsure (confidence < threshold); reported in the trace
    (r"reschedul|re-?plan|optimi[sz]|re-?plan|new plan|recompute|solver", "RESCHEDULE_TASK"),
    (r"\bwhy\b|explain|reason|cause", "DELAY_EXPLANATION"),
    (r"alert|critical|warning|urgent|problem|issue", "ALERTS_SUMMARY"),
    (r"progress|percent|complete|how far|finished|built", "STAGE_PROGRESS"),
    (r"late|delay|behind|slip|overdue", "DELAY_DETECTION"),
    (r"ready|start|block|begin|proceed|in the way", "TASK_READINESS"),
    (r"short|missing|enough|lack", "COMPONENT_SHORTAGE"),
    (r"supplier|vendor|deliver|arriv|eta|shipment", "SUPPLIER_INFO"),
    (r"stock|inventory|warehouse stock", "INVENTORY_STATUS"),
    (r"where|locat|find|whereabouts", "COMPONENT_LOCATION"),
    (r"status|inspect|approved|cleared|condition", "COMPONENT_STATUS"),
    (r"schedule|timeline|gantt|plan", "VIEW_SCHEDULE"),
    (r"^(hi|hello|hey|good (morning|evening|afternoon)|namaste)\b", "GREETING"),
    (r"help|what can you", "HELP"),
]


class MicroNLU:
    def __init__(self, path=MICROLM_PATH):
        ck = torch.load(path, map_location="cpu", weights_only=True)
        self.vocab: list[str] = ck["vocab"]
        self.w2i = {w: i for i, w in enumerate(self.vocab)}
        self.i2w = self.vocab
        self.intents: list[str] = ck["intents"]
        self.tags: list[str] = ck["tags"]
        cfg = ck["cfg"]
        self.model = MicroLM(len(self.vocab), len(self.intents), len(self.tags), cfg["emb"], cfg["hidden"])
        self.model.load_state_dict(ck["state"])
        self.model.eval()
        self.parameters = self.model.count_parameters()
        self._lock = threading.Lock()

    def _ids(self, toks: list[str], eos: bool = True) -> torch.Tensor:
        ids = [self.w2i[BOS]] + [self.w2i.get(norm_token(t), self.w2i[UNK]) for t in toks] + ([self.w2i[EOS]] if eos else [])
        return torch.tensor([ids])

    def predict(self, text: str, threshold: float = 0.6) -> dict:
        t0 = time.perf_counter()
        toks = tokenize(text)
        if not toks:
            return {"intent": "HELP", "confidence": 0.0, "top": [], "entities": [], "tokens": [], "fallback": False, "latency_ms": 0.0}
        with self._lock, torch.no_grad():
            li, lt, _ = self.model(self._ids(toks))
        probs = torch.softmax(li[0], -1)
        top = torch.topk(probs, 3)
        intent, conf = self.intents[top.indices[0].item()], float(top.values[0])
        tags = [self.tags[lt[0, j + 1].argmax().item()] for j in range(len(toks))]
        entities = decode(tags, toks)
        fallback = False
        unk = sum(1 for t in toks if norm_token(t) not in self.w2i) / len(toks)
        if unk >= 0.5 and not entities:       # mostly unknown words and nothing recognised -> the model is guessing
            conf = min(conf, 0.2)
        if conf < threshold and conf >= 0.3:
            joined = " ".join(toks)
            for pat, it in KEYWORD_PRIOR:
                if re.search(pat, joined):
                    if it != intent:
                        fallback = True
                    intent = it
                    break
        return {"intent": intent, "confidence": round(conf, 4), "fallback": fallback,
                "top": [{"intent": self.intents[i.item()], "p": round(float(p), 4)} for p, i in zip(top.values, top.indices)],
                "entities": entities, "tokens": toks, "tags": tags, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}

    def suggest(self, text: str, k: int = 3, extend: int = 2) -> list[str]:
        """Next-word auto-complete from the LM head (greedy continuation of the top-k first words)."""
        toks = tokenize(text)
        partial = ""
        if text and not text.endswith(" ") and toks:
            partial, toks = toks[-1], toks[:-1]
        with self._lock, torch.no_grad():
            def next_words(ctx, prefix="", n=k):
                _, _, lm = self.model(self._ids(ctx, eos=False))
                p = torch.softmax(lm[0, -1], -1)
                out = []
                for i in torch.argsort(p, descending=True).tolist():
                    w = self.i2w[i]
                    if w in SPECIALS or w.startswith("<") or not w.startswith(prefix) or w in "?.,!":
                        continue
                    out.append(w)
                    if len(out) == n:
                        break
                return out
            outs = []
            for w in next_words(toks, partial, k):
                phrase, ctx = [w], toks + [w]
                for _ in range(extend):
                    nxt = [x for x in next_words(ctx, "", 3) if x not in phrase]
                    if not nxt:
                        break
                    phrase.append(nxt[0]); ctx.append(nxt[0])
                outs.append(" ".join(phrase))
        base = " ".join(tokenize(text)[:-1] if partial else tokenize(text))
        return [(base + " " + o).strip() for o in outs]


def decode(tags: list[str], toks: list[str]) -> list[dict]:
    out, cur = [], None
    for i, (tag, tok) in enumerate(zip(tags, toks)):
        if tag == "O":
            cur = None
        elif tag.startswith("B-") or cur is None or cur["type"] != tag[2:]:
            cur = {"type": tag[2:], "text": tok, "start": i, "end": i + 1}
            out.append(cur)
        else:
            cur["text"] += " " + tok
            cur["end"] = i + 1
    return out


_nlu: MicroNLU | None = None


def get_nlu() -> MicroNLU:
    global _nlu
    if _nlu is None:
        _nlu = MicroNLU()
    return _nlu
