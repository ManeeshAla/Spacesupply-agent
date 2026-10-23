"""The Micro Language Model (PyTorch).

Shared embedding + bidirectional GRU encoder with three heads trained jointly:
  1. intent classification  (what does the user want?)
  2. entity tagging (BIO)   (which component / task / stage / workstation / supplier?)
  3. next-word language-model head, driven by the *forward* GRU half only (no future leakage),
     used for chat auto-complete and as an auxiliary LM objective.
"""
from __future__ import annotations

import torch
from torch import nn


class MicroLM(nn.Module):
    def __init__(self, vocab_size: int, n_intents: int, n_tags: int, emb: int = 32, hidden: int = 48, pad_id: int = 0):
        super().__init__()
        self.hidden = hidden
        self.pad_id = pad_id
        self.embedding = nn.Embedding(vocab_size, emb, padding_idx=pad_id)
        self.encoder = nn.GRU(emb, hidden, batch_first=True, bidirectional=True)
        self.drop = nn.Dropout(0.1)
        self.intent_head = nn.Linear(2 * hidden, n_intents)
        self.tag_head = nn.Sequential(nn.Linear(2 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, n_tags))
        self.lm_head = nn.Linear(hidden, vocab_size)

    def forward(self, ids: torch.Tensor):
        mask = (ids != self.pad_id).unsqueeze(-1)
        h, _ = self.encoder(self.drop(self.embedding(ids)))
        pooled = h.masked_fill(~mask, -1e4).max(dim=1).values
        return self.intent_head(self.drop(pooled)), self.tag_head(self.drop(h)), self.lm_head(h[..., : self.hidden])

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
