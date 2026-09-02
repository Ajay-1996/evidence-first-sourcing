"""Execute a resolution plan deterministically. The model proposed; this code disposes.

Every cell gets its transform_chain from the same tool functions the audit trail cites;
every price-affecting exception gets its annual impact computed and banded here — the model
never does arithmetic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from . import tools

DATA = Path(__file__).resolve().parent.parent / "data"


def _rfx_lines() -> dict[str, dict[str, Any]]:
    rfx = json.loads((DATA / "rfx_fy27.json").read_text())
    return {l["code"]: l for l in rfx["lines"]}


def _evidence_line(evidence: dict[str, Any], code: str) -> Optional[dict[str, Any]]:
    for l in evidence.get("lines", []):
        if l.get("code") == code:
            return l
    return None


def execute(plan_doc: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    lines = _rfx_lines()
    cells: list[dict[str, Any]] = []

    for item in plan_doc.get("plan", []):
        code = item.get("code")
        rl = lines.get(code)
        if rl is None:
            continue
        ev = _evidence_line(evidence, code) or {}
        action = item.get("action")
        params = item.get("params") or {}
        flags = list(item.get("flags") or [])
        chain: list[dict[str, Any]] = []
        state, value = "confirmed", None
        aq = ev.get("as_quoted")

        def weight() -> float:
            r = tools.estimate_box_weight_kg(rl["length_mm"], rl["width_mm"],
                                             rl["height_mm"], rl["gsm_combined"])
            chain.append(r["transform"])
            return r["value"]

        try:
            if action == "direct":
                value = (aq or {}).get("amount")
                if value is None:
                    state = "needs_review"
            elif action == "per_100":
                r = tools.convert_unit((aq or {}).get("amount"), (aq or {}).get("unit_raw", "per 100"), 100)
                chain.append(r["transform"]); value = r["value"]
            elif action == "per_pack":
                pk = params.get("pack_pieces")
                if not pk:
                    action, state = "gate", "needs_review"
                else:
                    r = tools.convert_unit((aq or {}).get("amount"), (aq or {}).get("unit_raw", "per case"), pk)
                    chain.append(r["transform"]); value = r["value"]
            elif action == "fx_usd":
                r = tools.convert_currency(params.get("usd_amount") or (aq or {}).get("amount"), "USD")
                chain.append(r["transform"]); value = r["value"]
            elif action == "per_kg_weight":
                w = weight()
                r = tools.derive_weight_price(params.get("rate_per_kg"), w)
                chain.append(r["transform"]); value = r["value"]
            if action == "gate":
                state, value = "needs_review", None
            elif action == "missing":
                state, value = "missing", None
            if value is not None and item.get("add_freight"):
                w = next((s["output"] for s in chain if s["tool"] == "estimate_box_weight_kg"), None)
                if w is None:
                    w = weight()
                r = tools.apply_freight_estimate(value, w)
                chain.append(r["transform"]); value = r["value"]
            if value is not None:
                value = round(value, 2)
        except Exception as e:
            state, value = "needs_review", None
            item["buyer_question"] = (item.get("buyer_question")
                                      or f"Normalization failed ({e}) — check this line by hand.")
            flags.append("needs_review")

        if state == "confirmed" and (flags or item.get("add_freight")):
            risky = {"basis_conflict", "reference", "illegible", "needs_review"}
            state = "assumed" if (set(flags) & risky or item.get("add_freight")) else "confirmed"

        cells.append({
            "code": code, "normalized_inr_per_unit": value, "state": state,
            "flags": flags, "transform_chain": chain,
            "as_quoted": aq, "source": ev.get("source"),
            "confidence": ev.get("confidence", 0.0 if value is None else 0.9),
            "buyer_question": item.get("buyer_question"),
            "note": item.get("note") or item.get("reason"),
        })

    by_code = {c["code"]: c for c in cells}

    def line_annual(code: str) -> float:
        c, rl = by_code.get(code), lines.get(code)
        if not c or not rl or c.get("normalized_inr_per_unit") is None:
            return 0.0
        return c["normalized_inr_per_unit"] * rl["qty_per_month"] * 12

    exceptions = []
    for e in plan_doc.get("exceptions", []):
        affected = [c for c in (e.get("affected_lines") or []) if c in lines]
        impact = None
        if e.get("type") == "FREIGHT_BASIS":
            # exact where chains applied freight; hypothetical (policy rate × weight) where
            # the conflict is still open and nothing was added yet
            total = 0.0
            for code in affected or list(by_code):
                c, rl = by_code.get(code), lines.get(code)
                if not c or not rl:
                    continue
                applied = sum(t["inputs"]["per_kg"] * t["inputs"]["weight_kg"]
                              for t in c.get("transform_chain", [])
                              if t.get("tool") == "apply_freight_estimate")
                if not applied:
                    w = tools.estimate_box_weight_kg(rl["length_mm"], rl["width_mm"],
                                                     rl["height_mm"], rl["gsm_combined"])["value"]
                    applied = tools.POLICY["freight_est_inr_per_kg"] * w
                total += applied * rl["qty_per_month"] * 12
            impact = round(total) or None
        elif e.get("delta_pct"):
            impact = round(sum(line_annual(code) for code in affected) * e["delta_pct"] / 100) or None
        elif e.get("delta_inr_per_unit"):
            impact = round(sum(tools.annual_impact(code, e["delta_inr_per_unit"])["value"]
                               for code in affected)) or None
        if impact and e.get("severity") != "AWARD_BLOCKING":
            e["severity"] = "HIGH" if impact > 500_000 else ("MEDIUM" if impact >= 100_000 else "LOW")
        exceptions.append({**e, "annual_impact_inr": impact})

    return {
        "vendor_id": plan_doc.get("vendor_id"),
        "cells": cells,
        "exceptions": exceptions,
        "questionnaire": plan_doc.get("questionnaire", []),
        "vendor_terms": plan_doc.get("vendor_terms", {}),
    }
