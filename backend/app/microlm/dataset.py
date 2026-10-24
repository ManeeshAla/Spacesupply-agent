"""Template-generated training data for the Micro LM: (query, intent, entity BIO tags)."""
from __future__ import annotations

import random
import re

from .catalog import (COMPONENT_NAMES, INTENTS, STAGE_WORDS, SUPPLIER_NAMES, SUPPLIER_SHORT, TASK_PHRASES,
                      WS_IDS, WS_NAMES)

TOKEN_RE = re.compile(r"cmp-?\d+|ws-?\d+|t-\d+|[a-z]+|\d+|[?!.,]")

TEMPLATES: dict[str, list[str]] = {
    "COMPONENT_LOCATION": [
        "where is {cmp}", "where is the {cname}", "locate {cmp}", "locate the {cname}", "what is the location of {cmp}",
        "where can i find the {cname}", "find the {cname}", "current location of {cmp}", "where is component {cmp} right now",
        "track {cmp}", "which bay is the {cname} in", "where did {cmp} go", "show me where the {cname} is", "where is {cname} stored",
        "where have we kept {cmp}", "tell me the position of {cmp}"],
    "COMPONENT_STATUS": [
        "status of {cmp}", "what is the status of {cmp}", "has the {cname} passed inspection", "is {cmp} approved",
        "show status for the {cname}", "how is {cmp} doing", "is the {cname} cleared for use", "inspection status of {cmp}",
        "tell me about {cmp}", "history of {cmp}", "what happened to {cmp}", "{cmp} status", "give me details on the {cname}",
        "is the {cname} ready to use", "show the event history of {cmp}", "has {cmp} been inspected yet"],
    "INVENTORY_STATUS": [
        "check inventory", "show inventory status", "how is our stock", "inventory summary", "what is in stock",
        "how many components are available", "show low stock items", "inventory overview", "show me the stock levels",
        "give me the inventory report", "what is our inventory like for {stage}", "inventory for {stage}", "how much stock do we hold",
        "list available components", "what is the stock position", "how are we doing on inventory"],
    "COMPONENT_SHORTAGE": [
        "are we missing anything for {stage}", "do we have enough {cname}", "any shortages", "what components are missing for {task}",
        "is anything short for {task}", "which parts are we short of", "show shortages for {stage}", "do we have all components for {task}",
        "are there any missing components", "missing parts for {stage}", "is there a shortage of {cname}", "what are we lacking for {task}",
        "do we have all the parts for {stage}", "are we short on {cname}", "which components are not available yet",
        "are all parts available for {task}"],
    "SUPPLIER_INFO": [
        "who supplies the {cname}", "which supplier delivers {cmp}", "supplier details for {sup}", "what is {sup} delivering",
        "show upcoming deliveries", "when will {cmp} arrive", "when is the {cname} arriving", "delivery status of {cmp}",
        "pending deliveries", "when is the next delivery", "eta of the {cname}", "what deliveries are coming from {sup}",
        "list open deliveries", "who is the supplier of {cmp}", "when does {sup} deliver next", "has the {cname} shipped yet"],
    "TASK_READINESS": [
        "can {task} start", "can {task} start today", "is {stage} ready to start assembly", "is {stage} ready",
        "are we ready for {task}", "can we begin {task}", "when can {task} start", "what is blocking {task}",
        "is {task} ready to begin", "can {stage} start today", "what is stopping {stage}", "ready to start {task}",
        "is {stage} good to go", "can we start {task} now", "what do we need before {task} can begin", "is {ws} free for {task}"],
    "VIEW_SCHEDULE": [
        "show todays schedule", "show the assembly schedule", "what is scheduled today", "what is on the schedule for {ws}",
        "schedule for {stage}", "what is next on the schedule", "show me the plan", "what are we working on now",
        "show upcoming tasks", "when is {task} scheduled", "what is running on {ws}", "list the schedule",
        "what is the plan for the next day", "show me the timeline", "which tasks are in progress", "when does {task} start"],
    "DELAY_DETECTION": [
        "which tasks are delayed", "are any tasks late", "show delayed tasks", "what is running behind", "any delays",
        "is anything behind schedule", "list late tasks", "which components are delayed", "what is delayed in {stage}",
        "show me the delays", "are there delays in {stage}", "which deliveries are late", "what is slipping",
        "anything running late", "give me the list of delayed items", "is {stage} behind"],
    "DELAY_EXPLANATION": [
        "why is {task} delayed", "why was {task} rescheduled", "why did {task} move", "explain the delay for {task}",
        "what caused the delay of {task}", "why is {stage} late", "why was {task} pushed back", "reason for the delay in {task}",
        "why is {task} late", "what changed in the schedule", "why has {task} slipped", "explain why {task} moved",
        "how come {task} is delayed", "what is the cause of the delay in {stage}", "tell me why {task} was delayed"],
    "RESCHEDULE_TASK": [
        "reschedule {task}", "re plan the schedule", "replan everything", "rerun the scheduler", "optimise the schedule",
        "recalculate the plan", "reschedule {stage}", "regenerate the schedule", "run the scheduling optimiser",
        "update the schedule", "can you reschedule {task}", "please rebuild the plan", "recompute the assembly schedule",
        "optimize the plan again", "fix the schedule", "re optimise {stage}"],
    "STAGE_PROGRESS": [
        "how is {stage} going", "progress of {stage}", "what is the progress of {stage}", "how far along is {stage}",
        "show stage progress", "launch vehicle progress", "overall progress", "how much of {stage} is complete",
        "stage completion status", "what percent of {stage} is done", "how close are we to launch", "progress report",
        "how is the vehicle coming along", "is {stage} complete", "give me progress for {stage}", "completion status"],
    "ALERTS_SUMMARY": [
        "show alerts", "any critical alerts", "what are the open alerts", "summarise the alerts", "what needs attention",
        "any warnings", "show me problems", "pending alerts", "what alerts do we have", "are there any issues",
        "anything critical", "what is wrong", "list active warnings", "give me the alert summary", "what should i worry about",
        "any problems right now"],
    "GREETING": ["hello", "hi", "hey there", "good morning", "hi agent", "hello spacesupply agent", "hey", "good evening",
                 "namaste", "hi there", "good afternoon", "hello there"],
    "HELP": ["help", "what can you do", "how do i use this", "what can i ask you", "show me what you can do",
             "list your capabilities", "how can you help", "what commands do you understand", "give me examples", "help me",
             "what are you able to do", "what questions can i ask"],
}


EXTRA = {
    "COMPONENT_LOCATION": ["is the {cname} in the warehouse", "which area is {cmp} sitting in", "where are we keeping the {cname}", "has {cmp} reached the assembly bay",
        "i cannot find {cmp}", "need the whereabouts of the {cname}", "is {cmp} in quarantine or in the warehouse", "position of the {cname} please",
        "which room holds {cmp}", "where is part {cmp}"],
    "COMPONENT_STATUS": ["did the {cname} clear inspection", "is {cmp} still waiting for inspection", "what condition is the {cname} in", "was {cmp} rejected",
        "inspection result for the {cname}", "is the {cname} usable yet", "give me an update on {cmp}", "what stage of the lifecycle is {cmp} in",
        "how far is the {cname} through inspection", "check on {cmp}"],
    "INVENTORY_STATUS": ["are we running low on anything in the store", "what do we have in the warehouse", "are we well stocked", "stock check please", "tell me about our parts inventory",
        "what is the inventory count", "how many parts do we have on hand", "give me a stock overview for {stage}", "what is low on stock", "which items are running low"],
    "COMPONENT_SHORTAGE": ["anything short for {stage}", "is the {cname} in short supply", "do we lack any parts for {task}", "what is not yet available for {task}",
        "any gaps in components for {stage}", "which items are we waiting on for {task}", "are we short of anything", "what parts do we still need for {stage}",
        "is every part for {task} on hand", "check availability of the {cname}"],
    "SUPPLIER_INFO": ["which vendor makes the {cname}", "what is the delivery date for {cmp}", "is {sup} on time", "tell me about {sup}", "when will the {cname} land",
        "what is incoming from {sup}", "show me inbound shipments", "any parts arriving soon", "who do we buy {cmp} from", "how reliable is {sup}"],
    "TASK_READINESS": ["could we start {task} right away", "what is holding up {task}", "is anything blocking {stage}", "do we have what we need to start {task}",
        "are we clear to proceed with {task}", "is it possible to start {task} today", "what are the blockers for {stage}", "go no go for {task}",
        "is {ws} available for {task}", "why can we not start {task}"],
    "VIEW_SCHEDULE": ["what is happening on {ws}", "what is planned for tomorrow", "display the gantt chart", "list tasks by start time", "what is the workstation plan",
        "what comes after {task}", "show me whats queued", "what is on the board today", "tell me the schedule for {stage}", "which jobs run next on {ws}"],
    "DELAY_DETECTION": ["are any jobs slipping", "are there overdue tasks", "what is behind plan", "tell me what is late", "which jobs will miss their deadline",
        "show tasks that will finish late", "is there any slippage", "any deadline risks", "what is going to be late in {stage}", "which items are overdue"],
    "DELAY_EXPLANATION": ["what is the reason {task} moved", "can you explain why {task} changed", "why did the plan change for {task}", "what is behind the delay of {task}",
        "who or what delayed {task}", "root cause of the delay in {task}", "why is {task} not starting on time", "what pushed {task} later",
        "explain the schedule change", "why was {stage} postponed"],
    "RESCHEDULE_TASK": ["run the optimiser once more", "plan everything again", "regenerate the plan for {task}", "make a new schedule", "can the schedule be recomputed",
        "run the solver again", "build a fresh plan", "please re optimise everything", "trigger a reschedule for {stage}", "update the plan with the latest data"],
    "STAGE_PROGRESS": ["what fraction of the vehicle is finished", "how much work is left on {stage}", "how complete is {stage}", "give me a progress update on the vehicle",
        "where are we on {stage}", "are we on track overall", "how far are we from completion", "tell me how {stage} is progressing", "what is done and what is left", "status of the build"],
    "ALERTS_SUMMARY": ["what is burning right now", "what needs my attention", "show me the red flags", "are there any open problems", "tell me about critical issues",
        "what alarms are active", "anything i should know about", "give me the warnings", "what is going wrong", "list outstanding issues"],
    "GREETING": ["hey agent", "yo", "greetings", "hello team", "morning", "hi spacesupply"],
    "HELP": ["what can i do here", "how does this work", "tell me what you can answer", "show commands", "what should i ask"],
}
for _k, _v in EXTRA.items():
    TEMPLATES[_k] = TEMPLATES[_k] + _v

PREFIX = ["", "", "", "please ", "hey agent ", "can you tell me ", "quick question ", "i need to know ", "could you ", "agent "]
SUFFIX = ["", "", "", " please", " now", " today", " right now"]


def _cmp(rng):
    n = rng.randint(1, 95)
    return rng.choice([f"cmp-{n:03d}", f"cmp{n:03d}", f"cmp-{n}", f"CMP-{n:03d}"])


def _stage(rng):
    n = rng.randint(1, 4)
    return rng.choice([f"stage {n}", f"stage {n}", f"stage {list(STAGE_WORDS)[n - 1]}", f"stage{n}"])


SLOTS = {
    "cmp": ("CMP", _cmp),
    "cname": ("CNAME", lambda r: r.choice(COMPONENT_NAMES)),
    "stage": ("STAGE", _stage),
    "task": ("TASK", lambda r: r.choice(TASK_PHRASES)),
    "ws": ("WS", lambda r: r.choice([r.choice(WS_IDS), r.choice(WS_IDS).replace("-", ""), r.choice(WS_NAMES)])),
    "sup": ("SUP", lambda r: r.choice(SUPPLIER_NAMES + SUPPLIER_SHORT)),
}


def tokenize(text: str) -> list[str]:
    text = re.sub(r"(stage)(\d)", r"\1 \2", text.lower())
    return TOKEN_RE.findall(text)


def norm_token(tok: str) -> str:
    if re.fullmatch(r"cmp-?\d+", tok):
        return "<cmp>"
    if re.fullmatch(r"ws-?\d+", tok):
        return "<ws>"
    if re.fullmatch(r"t-\d+", tok):
        return "<tid>"
    if tok.isdigit():
        return "<num>"
    return tok


def _typo(tok: str, rng: random.Random) -> str:
    if len(tok) < 5 or tok.startswith("<"):
        return tok
    i = rng.randint(1, len(tok) - 2)
    return tok[:i] + tok[i + 1] + tok[i] + tok[i + 2:]


def render(template: str, rng: random.Random, noise: float = 0.0):
    """Fill slots -> (tokens, tags)."""
    toks: list[str] = []
    tags: list[str] = []
    for part in re.split(r"(\{\w+\})", template):
        if not part:
            continue
        m = re.fullmatch(r"\{(\w+)\}", part)
        if m:
            etype, fn = SLOTS[m.group(1)]
            ts = tokenize(fn(rng))
            for i, t in enumerate(ts):
                toks.append(t)
                tags.append(("B-" if i == 0 else "I-") + etype)
        else:
            for t in tokenize(part):
                toks.append(_typo(t, rng) if rng.random() < noise else t)
                tags.append("O")
    return toks, tags


def wrap(toks, tags, rng, intent):
    if intent in ("GREETING", "HELP"):
        return toks, tags
    pre = tokenize(rng.choice(PREFIX))
    suf = tokenize(rng.choice(SUFFIX))
    if rng.random() < 0.55:
        suf = suf + ["?"]
    return pre + toks + suf, ["O"] * len(pre) + tags + ["O"] * len(suf)


def build(seed: int = 13, per_template: int = 36, test_frac: float = 0.25):
    """Template-level split: test templates are never seen in training (honest generalisation test)."""
    rng = random.Random(seed)
    train, test = [], []
    for intent, temps in TEMPLATES.items():
        order = list(temps)
        rng.shuffle(order)
        n_test = max(1, round(len(order) * test_frac)) if len(order) > 4 else 0
        test_t, train_t = order[:n_test], order[n_test:]
        if intent in ("GREETING", "HELP"):   # tiny closed sets: share templates, vary wrappers only
            train_t, test_t = order, order[:3]
        for t in train_t:
            for _ in range(per_template):
                toks, tags = wrap(*render(t, rng, noise=0.08), rng, intent)
                train.append((toks, tags, intent))
        for t in test_t:
            for _ in range(24):
                toks, tags = wrap(*render(t, rng, noise=0.05), rng, intent)
                test.append((toks, tags, intent))
    rng.shuffle(train)
    n_val = int(0.1 * len(train))
    return train[n_val:], train[:n_val], test


# Hand-written challenge queries (NOT generated from templates; train.py asserts zero overlap) -- a harder sanity check
CHALLENGE = [
    ("Where is CMP021?", "COMPONENT_LOCATION"), ("has the fuel pump made it to the warehouse yet", "COMPONENT_LOCATION"),
    ("show me where cmp 21 is", "COMPONENT_LOCATION"), ("Are we missing any components for engine assembly?", "COMPONENT_SHORTAGE"),
    ("do we have enough pressure sensors", "COMPONENT_SHORTAGE"), ("anything we are short of for stage 3", "COMPONENT_SHORTAGE"),
    ("Can Stage 2 start today?", "TASK_READINESS"), ("Is Stage 2 ready to start assembly?", "TASK_READINESS"),
    ("can we kick off engine assembly", "TASK_READINESS"), ("what is in the way of stage 4", "TASK_READINESS"),
    ("Why was Engine Assembly delayed?", "DELAY_EXPLANATION"), ("why is fuel line connection running late", "DELAY_EXPLANATION"),
    ("explain why the schedule changed", "DELAY_EXPLANATION"), ("Show today's assembly schedule", "VIEW_SCHEDULE"),
    ("what is going on at the test cell", "VIEW_SCHEDULE"), ("what is scheduled for ws-05", "VIEW_SCHEDULE"),
    ("Which tasks are running late?", "DELAY_DETECTION"), ("is anything falling behind this week", "DELAY_DETECTION"),
    ("how much is late in stage 2", "DELAY_DETECTION"), ("Reschedule engine assembly", "RESCHEDULE_TASK"),
    ("compute a new plan", "RESCHEDULE_TASK"), ("how is stage 2 progressing", "STAGE_PROGRESS"),
    ("give me a progress report on the launch vehicle", "STAGE_PROGRESS"), ("how many percent of the rocket is built", "STAGE_PROGRESS"),
    ("any critical alerts right now", "ALERTS_SUMMARY"), ("tell me what is urgent", "ALERTS_SUMMARY"),
    ("check the inventory", "INVENTORY_STATUS"), ("how is the warehouse stock", "INVENTORY_STATUS"),
    ("who supplies the hydraulic motor", "SUPPLIER_INFO"), ("when will the fuel pump arrive", "SUPPLIER_INFO"),
    ("list upcoming deliveries", "SUPPLIER_INFO"), ("what's the status of cmp-034", "COMPONENT_STATUS"),
    ("did the avionics unit clear inspection", "COMPONENT_STATUS"), ("is cmp-021 approved for use", "COMPONENT_STATUS"),
    ("hello spacesupply", "GREETING"), ("what are you able to help me with", "HELP"),
]
