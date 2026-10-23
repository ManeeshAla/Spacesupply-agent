"""A scripted stand-in for Gemini, so the assistant can be tested offline.

It implements only what the supervisor uses: `bind_tools(...)` followed by `astream(...)`.
Each entry in `script` is one model turn:

    {"tools": [("get_component", {"component": "CMP-021"})]}   -> ask for those tool calls
    {"text": "CMP-021 is in the warehouse."}                   -> final answer, streamed
    {"raise": SomeError("...")}                                -> fail this turn
"""
from __future__ import annotations

import json

from langchain_core.messages import AIMessageChunk
from langchain_core.messages.tool import tool_call_chunk


class FakeChatModel:
    def __init__(self, script: list[dict] | None = None, name: str = "fake-model"):
        self.script = list(script or [])
        self.name = name
        self.bound_tools: list = []
        self.seen: list[list] = []        # messages of every turn, for assertions
        self.turns = 0

    # the supervisor calls factory(model_name).bind_tools(tools).astream(messages)
    def bind_tools(self, tools):
        self.bound_tools = list(tools)
        return self

    def tool_names(self) -> list[str]:
        return [t.name for t in self.bound_tools]

    async def astream(self, messages):
        self.seen.append(list(messages))
        self.turns += 1
        turn = self.script.pop(0) if self.script else {"text": "I have nothing scripted to say."}
        if "raise" in turn:
            raise turn["raise"]
        if turn.get("tools"):
            chunks = [tool_call_chunk(name=n, args=json.dumps(a), id=f"call_{self.turns}_{i}", index=i)
                      for i, (n, a) in enumerate(turn["tools"])]
            yield AIMessageChunk(content=turn.get("text", ""), tool_call_chunks=chunks)
            return
        if not turn["text"]:
            return                         # a genuinely empty stream
        for word in turn["text"].split(" "):
            yield AIMessageChunk(content=word + " ")

    def factory(self):
        """A model factory the supervisor accepts (ignores the model name)."""
        return lambda _name: self


def script_factory(script: list[dict]):
    """Convenience: returns (factory, model) for one scripted conversation."""
    fake = FakeChatModel(script)
    return fake.factory(), fake
