"""Train + evaluate the Micro LM.   python -m app.microlm.train"""
from __future__ import annotations

import json
import random
import time

import numpy as np
import torch
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from torch import nn

from ..config import MICROLM_METRICS, MICROLM_PATH
from . import dataset
from .catalog import INTENTS, TAGS
from .model import MicroLM
from .vocab import BOS, EOS, PAD, UNK, build_vocab, encode

T2I = {t: i for i, t in enumerate(TAGS)}
I2I = {t: i for i, t in enumerate(INTENTS)}


def make_batch(samples, w2i, unk_drop=0.0, rng=None):
    seqs = [encode(t, w2i) for t, _, _ in samples]
    n = max(len(s) for s in seqs)
    ids = torch.zeros(len(seqs), n, dtype=torch.long)
    tags = torch.full((len(seqs), n), -100, dtype=torch.long)
    intents = torch.tensor([I2I[i] for _, _, i in samples])
    for b, ((toks, tg, _), s) in enumerate(zip(samples, seqs)):
        row = list(s)
        if unk_drop and rng is not None:
            for j in range(1, len(row) - 1):
                if tg[j - 1] == "O" and rng.random() < unk_drop:
                    row[j] = w2i[UNK]
        ids[b, : len(row)] = torch.tensor(row)
        tags[b, 0] = T2I["O"]
        tags[b, len(row) - 1] = T2I["O"]
        for j, x in enumerate(tg):
            tags[b, j + 1] = T2I[x]
    return ids, intents, tags


def spans(tags: list[str], toks: list[str]) -> set[tuple[str, str]]:
    out, cur_t, cur = set(), None, []
    for tag, tok in zip(tags + ["O"], toks + [""]):
        if tag.startswith("B-") or tag == "O" or (tag.startswith("I-") and tag[2:] != cur_t):
            if cur_t:
                out.add((cur_t, " ".join(cur)))
            cur_t, cur = (tag[2:], [tok]) if tag != "O" else (None, [])
        else:
            cur.append(tok)
    return out


def lm_loss_fn(lm_logits, ids):
    tgt = torch.zeros_like(ids)
    tgt[:, :-1] = ids[:, 1:]
    return nn.functional.cross_entropy(lm_logits.reshape(-1, lm_logits.size(-1)), tgt.reshape(-1), ignore_index=0)


@torch.no_grad()
def evaluate(model, samples, w2i, batch=128):
    model.eval()
    pi, gi, ents_p, ents_g, lm_sum, lm_n = [], [], 0, 0, 0.0, 0
    tp = fp = fn = 0
    for k in range(0, len(samples), batch):
        chunk = samples[k: k + batch]
        ids, intents, tags = make_batch(chunk, w2i)
        li, lt, ll = model(ids)
        pi += li.argmax(-1).tolist()
        gi += intents.tolist()
        pt = lt.argmax(-1)
        for b, (toks, gold_tags, _) in enumerate(chunk):
            pred_tags = [TAGS[pt[b, j + 1].item()] for j in range(len(toks))]
            P, G = spans(pred_tags, toks), spans(gold_tags, toks)
            tp += len(P & G); fp += len(P - G); fn += len(G - P)
        tgt = torch.zeros_like(ids); tgt[:, :-1] = ids[:, 1:]
        l = nn.functional.cross_entropy(ll.reshape(-1, ll.size(-1)), tgt.reshape(-1), ignore_index=0, reduction="sum")
        lm_sum += l.item(); lm_n += (tgt != 0).sum().item()
    acc = float(np.mean(np.array(pi) == np.array(gi)))
    p, r, f, _ = precision_recall_fscore_support(gi, pi, average="macro", zero_division=0)
    per = precision_recall_fscore_support(gi, pi, labels=list(range(len(INTENTS))), zero_division=0)
    ep = tp / (tp + fp) if tp + fp else 0.0
    er = tp / (tp + fn) if tp + fn else 0.0
    ef = 2 * ep * er / (ep + er) if ep + er else 0.0
    return {"intent_accuracy": round(acc, 4), "precision_macro": round(p, 4), "recall_macro": round(r, 4), "f1_macro": round(f, 4),
            "entity_precision": round(ep, 4), "entity_recall": round(er, 4), "entity_f1": round(ef, 4),
            "lm_perplexity": round(float(np.exp(lm_sum / max(1, lm_n))), 2),
            "per_intent": {INTENTS[i]: {"precision": round(float(per[0][i]), 3), "recall": round(float(per[1][i]), 3),
                                        "f1": round(float(per[2][i]), 3), "support": int(per[3][i])} for i in range(len(INTENTS))},
            "confusion_matrix": confusion_matrix(gi, pi, labels=list(range(len(INTENTS)))).tolist(), "n": len(samples)}


def main(epochs: int = 45, seed: int = 7):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    train, val, test = dataset.build()
    seen = {" ".join(x[0]) for x in train + val + test}
    leaked = [q for q, _ in dataset.CHALLENGE if " ".join(dataset.tokenize(q)) in seen]
    assert not leaked, f"challenge queries leaked into the generated data: {leaked}"
    vocab = build_vocab(train + val + test if False else train)
    w2i = {w: i for i, w in enumerate(vocab)}
    model = MicroLM(len(vocab), len(INTENTS), len(TAGS))
    n_params = model.count_parameters()
    print(f"vocab={len(vocab)}  train={len(train)} val={len(val)} test={len(test)}  trainable parameters={n_params:,}")
    opt = torch.optim.AdamW(model.parameters(), lr=4e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    rng = random.Random(seed)
    history, best, best_state = [], -1.0, None
    t0 = time.time()
    for ep in range(1, epochs + 1):
        model.train()
        rng.shuffle(train)
        tot = nb = 0
        for k in range(0, len(train), 64):
            ids, intents, tags = make_batch(train[k: k + 64], w2i, unk_drop=0.10, rng=rng)
            li, lt, ll = model(ids)
            loss = (nn.functional.cross_entropy(li, intents)
                    + nn.functional.cross_entropy(lt.reshape(-1, lt.size(-1)), tags.reshape(-1), ignore_index=-100)
                    + 0.3 * lm_loss_fn(ll, ids))
            opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
            tot += loss.item(); nb += 1
        sched.step()
        v = evaluate(model, val, w2i)
        vloss = None
        history.append({"epoch": ep, "train_loss": round(tot / nb, 4), "val_intent_acc": v["intent_accuracy"], "val_entity_f1": v["entity_f1"],
                        "val_lm_ppl": v["lm_perplexity"]})
        score = v["intent_accuracy"] + v["entity_f1"]
        if score > best:
            best, best_state = score, {k: x.clone() for k, x in model.state_dict().items()}
        if ep % 5 == 0 or ep == 1:
            print(f"epoch {ep:3d} loss {tot / nb:.4f}  val intent {v['intent_accuracy']:.3f}  entity F1 {v['entity_f1']:.3f}  ppl {v['lm_perplexity']}")
    model.load_state_dict(best_state)
    test_m = evaluate(model, test, w2i)
    val_m = evaluate(model, val, w2i)

    # hand-written challenge set
    model.eval()
    correct, fails = 0, []
    for text, gold in dataset.CHALLENGE:
        toks = dataset.tokenize(text)
        ids = torch.tensor([encode(toks, w2i)])
        with torch.no_grad():
            pred = INTENTS[model(ids)[0].argmax(-1).item()]
        if pred == gold:
            correct += 1
        else:
            fails.append({"text": text, "gold": gold, "pred": pred})
    # latency
    ids = torch.tensor([encode(dataset.tokenize("where is the fuel pump"), w2i)])
    with torch.no_grad():
        for _ in range(20): model(ids)
        t1 = time.perf_counter()
        for _ in range(300): model(ids)
        lat = (time.perf_counter() - t1) / 300 * 1000

    torch.save({"state": model.state_dict(), "vocab": vocab, "intents": INTENTS, "tags": TAGS,
                "cfg": {"emb": 32, "hidden": 48}}, MICROLM_PATH)
    out = {"framework": f"PyTorch {torch.__version__}", "parameters": n_params,
           "architecture": "Embedding(32) -> BiGRU(48) -> {intent head, BIO entity tagger, next-word LM head}",
           "vocab_size": len(vocab), "n_intents": len(INTENTS), "n_tags": len(TAGS),
           "data": {"train": len(train), "val": len(val), "test": len(test),
                    "note": "test set uses templates never seen in training"},
           "val": {k: v for k, v in val_m.items() if k not in ("per_intent", "confusion_matrix")},
           "test": test_m, "challenge": {"n": len(dataset.CHALLENGE), "intent_accuracy": round(correct / len(dataset.CHALLENGE), 4), "failures": fails},
           "inference_ms": round(lat, 3), "training_seconds": round(time.time() - t0, 1), "history": history, "intents": INTENTS}
    MICROLM_METRICS.write_text(json.dumps(out, indent=2))
    print(f"\nTEST  intent acc {test_m['intent_accuracy']}  macro-F1 {test_m['f1_macro']}  entity F1 {test_m['entity_f1']}  ppl {test_m['lm_perplexity']}")
    print(f"CHALLENGE (hand-written) intent acc {out['challenge']['intent_accuracy']}  failures: {len(fails)}")
    print(f"parameters {n_params:,}  inference {lat:.2f} ms  trained in {out['training_seconds']}s")
    for f in fails: print("  miss:", f)


if __name__ == "__main__":
    main()
