"""Event store + the analyst's read-only query tools.

JSON-file persistence (data/) — deliberately boring. The interesting property is the shape:
the store holds NormalizedCell objects with full transform chains, so every query the analyst
answers is over provenance-bearing data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .schemas import RFx
from .tools import POLICY

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_rfx() -> RFx:
    return RFx.model_validate_json((DATA_DIR / "rfx_fy27.json").read_text())


def load_comparison() -> dict[str, Any]:
    """{vendor_id: resolved quote} — written by the pipeline's resolution step."""
    path = DATA_DIR / "comparison.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_comparison(cmp_: dict[str, Any]) -> None:
    (DATA_DIR / "comparison.json").write_text(json.dumps(cmp_, indent=1, default=str))


def load_decisions() -> dict[str, Any]:
    path = DATA_DIR / "decisions.json"
    return json.loads(path.read_text()) if path.exists() else {}


def record_decision(vendor_id: str, facts: dict[str, Any], note: str) -> None:
    """Buyer resolves a gate: store the confirmed fact(s); caller re-runs the pipeline for
    that vendor so the resolution agent recomputes WITH the fact — the loop stays real."""
    import time
    dec = load_decisions()
    dec.setdefault(vendor_id, {}).update(facts)
    (DATA_DIR / "decisions.json").write_text(json.dumps(dec, indent=1))
    log_path = DATA_DIR / "decision_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    log.append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "vendor": vendor_id,
                "facts": facts, "note": note})
    log_path.write_text(json.dumps(log, indent=1))


def load_rules() -> list[dict[str, Any]]:
    p = DATA_DIR / "rules.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_rules(rules: list[dict[str, Any]]) -> None:
    (DATA_DIR / "rules.json").write_text(json.dumps(rules, indent=1))


def create_rule(rtype: str, action: str, label: str, created_from: dict[str, Any]) -> dict[str, Any]:
    """Promote a repeated buyer decision to standing policy. Compliance is not promotable."""
    import time
    if "QUESTIONNAIRE" in rtype.upper():
        raise ValueError("Compliance issues cannot become rules — they are raised every time.")
    rules = load_rules()
    rule = {"id": f"R-{len(rules)+1}", "type": rtype, "action": action, "label": label,
            "scope": "this event", "enabled": True,
            "created_from": {**created_from, "ts": time.strftime("%Y-%m-%d %H:%M")}}
    rules.append(rule)
    save_rules(rules)
    return rule


def qualification() -> dict[str, Any]:
    """Per-vendor clearance against the event rule (valid ISO + burst certs provided).
    Heuristic read of extracted answers; blanks fail — absence of evidence is failure."""
    def ok(ans: Any) -> bool:
        if not ans:
            return False
        s = str(ans).strip().lower()
        return not (s.startswith("no") or s.startswith("not") or "expired" in s or s in ("-", "—", "null"))
    out = {}
    for vid, quote in load_comparison().items():
        answers = {str(q.get("key", "")).split(":")[0].strip(): q.get("answer")
                   for q in quote.get("questionnaire", [])}
        iso, burst = ok(answers.get("iso")), ok(answers.get("burst"))
        out[vid] = {"iso": iso, "burst": burst, "answers": answers,
                    "cleared": iso and burst,
                    "rule": POLICY["clearance_rule"]}
    return out


# ---------------- analyst query tools ----------------

def _cells(vendor: Optional[str] = None, line: Optional[str] = None,
           state: Optional[str] = None) -> list[dict[str, Any]]:
    out = []
    for vid, quote in load_comparison().items():
        if vendor and vid != vendor:
            continue
        for c in quote.get("cells", []):
            if line and c.get("code") != line:
                continue
            if state and c.get("state") != state:
                continue
            out.append({**c, "vendor_id": vid})
    return out


def get_event() -> dict[str, Any]:
    rfx = load_rfx()
    return {"event_id": rfx.event_id, "title": rfx.title, "lines": len(rfx.lines),
            "vendors": sorted(load_comparison().keys()), "policy": POLICY}


def get_lines(codes: Optional[list[str]] = None) -> list[dict[str, Any]]:
    rfx = load_rfx()
    return [l.model_dump() for l in rfx.lines if not codes or l.code in codes]


def get_cells(vendor: Optional[str] = None, line: Optional[str] = None,
              state: Optional[str] = None) -> list[dict[str, Any]]:
    return _cells(vendor, line, state)


def _usable(c: dict[str, Any]) -> bool:
    return c["state"] in ("confirmed", "assumed") and c["normalized_inr_per_unit"] is not None


def _qty(code: str) -> int:
    return next(l.qty_per_month for l in load_rfx().lines if l.code == code)


def vendor_totals(basis: str = "quoted") -> list[dict[str, Any]]:
    """Annual totals per vendor. basis='quoted' totals each vendor's own usable lines and says
    how many that is; basis='common_lines' totals only lines every vendor quoted usably."""
    cmp_ = load_comparison()
    common: Optional[set] = None
    if basis == "common_lines":
        for quote in cmp_.values():
            codes = {c["code"] for c in quote["cells"] if _usable(c)}
            common = codes if common is None else common & codes
    out = []
    for vid, quote in cmp_.items():
        cells = [c for c in quote["cells"]
                 if _usable(c) and (common is None or c["code"] in common)]
        total = sum(c["normalized_inr_per_unit"] * _qty(c["code"]) * 12 for c in cells)
        pending = sum(1 for c in quote["cells"] if c["state"] == "needs_review")
        out.append({"vendor": vid, "annual_inr": round(total), "lines": len(cells),
                    "pending_cells": pending,
                    "full_basket": len(cells) == len(load_rfx().lines) and pending == 0})
    return sorted(out, key=lambda r: r["annual_inr"])


def compute_split(pool) -> dict[str, Any]:
    """Cheapest usable price per line within the vendor pool.
    pool: list of vendor ids, or the shortcuts "cleared" / "all"."""
    cmp_ = load_comparison()
    if isinstance(pool, str):
        if pool.lower() == "cleared":
            pool = [v for v, q in qualification().items() if q["cleared"]]
        elif pool.lower() == "all":
            pool = list(cmp_.keys())
        else:
            pool = [pool]
    rows, share, wins, uncovered = [], {}, {}, []
    for line in load_rfx().lines:
        best = None
        for vid in pool:
            for c in cmp_.get(vid, {}).get("cells", []):
                if c["code"] == line.code and _usable(c):
                    if best is None or c["normalized_inr_per_unit"] < best[1]:
                        best = (vid, c["normalized_inr_per_unit"])
        if best is None:
            uncovered.append(line.code)
            continue
        annual = best[1] * line.qty_per_month * 12
        share[best[0]] = share.get(best[0], 0) + annual
        wins[best[0]] = wins.get(best[0], 0) + 1
        rows.append({"code": line.code, "vendor": best[0], "inr_per_unit": best[1]})
    return {"pool": pool, "annual_inr": round(sum(share.values())),
            "share": {k: round(v) for k, v in share.items()}, "wins": wins,
            "uncovered": uncovered, "rows": rows}


def get_questionnaire() -> dict[str, Any]:
    cmp_ = load_comparison()
    return {vid: quote.get("questionnaire", []) for vid, quote in cmp_.items()}


def get_open_items() -> list[dict[str, Any]]:
    items = []
    for vid, quote in load_comparison().items():
        for e in quote.get("exceptions", []):
            items.append({"kind": "exception", "vendor": vid, **e})
    for c in _cells(state="needs_review"):
        code = c.get("code")
        if not any(i for i in items if i.get("kind") == "exception"
                   and code in (i.get("affected_lines") or [])):
            items.append({"kind": "cell", "vendor": c.get("vendor_id"), "code": code,
                          "question": c.get("buyer_question")})
    sev_rank = {"AWARD_BLOCKING": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    items.sort(key=lambda i: (sev_rank.get(i.get("severity"), 4),
                              -(i.get("annual_impact_inr") or 0)))
    return items


ANALYST_TOOLS = {
    "get_event": get_event,
    "get_lines": get_lines,
    "get_cells": get_cells,
    "vendor_totals": vendor_totals,
    "compute_split": compute_split,
    "get_questionnaire": get_questionnaire,
    "get_open_items": get_open_items,
    "get_policy": lambda: dict(POLICY),
    "qualification": qualification,
}

ANALYST_TOOL_SCHEMAS = [
    {"name": "get_event", "description": "Event summary: title, line count, vendors present, policy.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_lines", "description": "RFx line items, optionally filtered by codes.",
     "input_schema": {"type": "object", "properties": {"codes": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "get_cells", "description": "Normalized cells with provenance; filter by vendor, line, or state.",
     "input_schema": {"type": "object", "properties": {"vendor": {"type": "string"},
                                                        "line": {"type": "string"},
                                                        "state": {"type": "string"}}}},
    {"name": "vendor_totals", "description": "Annual totals per vendor; basis 'quoted' or 'common_lines'. Refuses nothing — but reports coverage so YOU refuse bad comparisons.",
     "input_schema": {"type": "object", "properties": {"basis": {"type": "string", "enum": ["quoted", "common_lines"]}}}},
    {"name": "compute_split", "description": "Cheapest usable price per line within a vendor pool; returns total, share, wins, uncovered lines. pool = list of vendor ids, or \"cleared\" / \"all\".",
     "input_schema": {"type": "object", "properties": {"pool": {"anyOf": [
         {"type": "array", "items": {"type": "string"}}, {"type": "string"}]}}, "required": ["pool"]}},
    {"name": "get_questionnaire", "description": "All vendors' extracted questionnaire answers.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_open_items", "description": "Unresolved review items: unconfirmed cells and undecided policy calls.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_policy", "description": "Event policy: FX rate/date, freight estimate, clearance rule.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "qualification", "description": "Per-vendor clearance against the event rule (ISO + burst certs), with the extracted answers behind it. Use this for any 'quality-cleared' constraint and name who is in/out and why.",
     "input_schema": {"type": "object", "properties": {}}},
]
