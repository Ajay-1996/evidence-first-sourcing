"""Keyless smoke test of the agent layer. Run:  python -m tests.smoke_test

Proves, without any API key:
  1. seeds load; schemas validate
  2. the runner's tool loop works end-to-end (MockProvider playbook drives the normalize
     agent through real deterministic tools: weight → ₹/kg price → freight)
  3. the analyst's query tools compute correct math over a stub comparison
"""
from __future__ import annotations

import json

from backend import seed_data, store
from backend.agent_runner import run_agent
from backend.providers import MockProvider
from backend.tools import NORMALIZE_TOOL_SCHEMAS, NORMALIZE_TOOLS


def test_runner_tool_loop() -> None:
    """Drive: estimate weight for PKG-017 → derive ₹/kg price → add freight → final JSON."""
    playbook = [
        {"tool_calls": [{"id": "t1", "name": "estimate_box_weight_kg",
                         "arguments": {"length_mm": 600, "width_mm": 400, "height_mm": 400,
                                       "gsm_combined": 660}}]},
        {"tool_calls": [{"id": "t2", "name": "derive_weight_price",
                         "arguments": {"rate_per_kg": 42.0, "weight_kg": 1.184}}]},
        {"tool_calls": [{"id": "t3", "name": "apply_freight_estimate",
                         "arguments": {"amount": 49.73, "weight_kg": 1.184}}]},
        {"text": json.dumps({"code": "PKG-017", "normalized_inr_per_unit": 52.22,
                             "state": "assumed", "flags": ["weight_basis", "basis_conflict"]})},
    ]
    text, trace = run_agent("resolution", {"probe": True}, tools=NORMALIZE_TOOLS,
                            tool_schemas=NORMALIZE_TOOL_SCHEMAS,
                            provider_override=MockProvider(playbook))
    tool_steps = [s for s in trace.steps if s["type"] == "tool"]
    assert len(tool_steps) == 3, trace
    w = json.loads(tool_steps[0]["result_preview"].replace("'", '"'))
    assert abs(w["value"] - 1.184) < 0.02, w      # (2*1000+40)/1000 * 830/1000 * 660 * 1.05 / 1000
    assert json.loads(text)["code"] == "PKG-017"
    print(f"  runner loop ✓  weight={w['value']}kg, 3 tool steps, final JSON returned")


def test_store_math() -> None:
    def cell(v, code, price, state="confirmed"):
        return {"vendor_id": v, "code": code, "normalized_inr_per_unit": price,
                "state": state, "flags": [], "transform_chain": [], "confidence": 0.95}

    lines = store.load_rfx().lines[:3]            # PKG-001..003
    a, b, c = (l.code for l in lines)
    store.save_comparison({
        "V1": {"vendor_id": "V1", "cells": [cell("V1", a, 10.0), cell("V1", b, 20.0),
                                             cell("V1", c, 30.0)], "policy_decisions": []},
        "V2": {"vendor_id": "V2", "cells": [cell("V2", a, 12.0), cell("V2", b, 18.0),
                                             cell("V2", c, None, "needs_review")],
               "policy_decisions": []},
    })
    split = store.compute_split(["V1", "V2"])
    q = {l.code: l.qty_per_month for l in lines}
    expected = (10.0 * q[a] + 18.0 * q[b] + 30.0 * q[c]) * 12
    assert split["annual_inr"] == round(expected), split
    assert split["wins"] == {"V1": 2, "V2": 1}
    assert len(split["uncovered"]) == 27          # stub covers only 3 of 30 lines
    open_items = store.get_open_items()
    assert any(i["kind"] == "cell" and i["code"] == c for i in open_items)
    totals = store.vendor_totals("quoted")
    assert all(not t["full_basket"] for t in totals)
    print(f"  store math ✓  split=₹{split['annual_inr']:,}, wins={split['wins']}, "
          f"needs_review surfaced={len(open_items)}")


def main() -> None:
    seed_data.main()
    rfx = store.load_rfx()
    assert len(rfx.lines) == 30 and len(rfx.questionnaire) == 6
    print("  seed ✓  30 lines, 6 questionnaire items")
    test_runner_tool_loop()
    test_store_math()
    (store.DATA_DIR / "comparison.json").unlink()  # leave no stub behind
    print("smoke test: ALL PASS (keyless — MockProvider)")


if __name__ == "__main__":
    main()
