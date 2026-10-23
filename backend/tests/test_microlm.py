import json
from app.config import MICROLM_METRICS
from app.microlm.infer import get_nlu
from app.microlm.model import MicroLM


def test_parameter_count_at_least_1000():
    nlu = get_nlu()
    n = sum(p.numel() for p in nlu.model.parameters() if p.requires_grad)
    assert n >= 1000
    assert json.loads(MICROLM_METRICS.read_text())["parameters"] == n


def test_intent_and_entity():
    r = get_nlu().predict("where is the fuel pump")
    assert r["intent"] == "COMPONENT_LOCATION"
    assert any(e["type"] == "CNAME" for e in r["entities"])


def test_gibberish_is_low_confidence_or_fallback():
    r = get_nlu().predict("qzxv blorp wug")
    assert r["confidence"] < 0.6 or r["fallback"] or r["intent"] == "HELP"


def test_suggest_returns_words():
    assert isinstance(get_nlu().suggest("where is the"), list)


def test_metrics_report_honest_split():
    m = json.loads(MICROLM_METRICS.read_text())
    assert m["test"]["n"] > 500 and m["challenge"]["n"] >= 30
