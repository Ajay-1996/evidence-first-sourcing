"""Deterministic tools — all arithmetic lives here, none of it in a model.

Two families:
  - normalization tools: unit/currency/weight/freight/prior-award transforms. Each returns
    {"value": ..., "transform": TransformStep-shaped dict} so the chain writes itself.
  - analyst tools: read-only queries over the ComparisonStore.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ---------------- policy (event-wide, single source of truth) ----------------

POLICY = {
    "fx_usd_inr": 83.60,
    "fx_date": "2026-08-28 (RBI reference rate)",
    "freight_est_inr_per_kg": 2.1,
    "freight_lane": "Vapi → Bhiwandi, trailing 6-month lane average",
    "weight_tolerance_pct": 4.0,
    "clearance_rule": "valid ISO 9001 + burst-test certs on file",
}


def get_policy() -> dict[str, Any]:
    return dict(POLICY)


# ---------------- normalization tools ----------------

def _step(tool: str, inputs: dict[str, Any], output: Any, text: str) -> dict[str, Any]:
    return {"tool": tool, "inputs": inputs, "output": output, "text": text}


def convert_unit(amount: float, unit_raw: str, quantity_in_unit: float) -> dict[str, Any]:
    """e.g. ₹940 per 100 pcs → quantity_in_unit=100 → ₹9.40 per piece."""
    value = round(amount / quantity_in_unit, 2)
    return {"value": value, "transform": _step(
        "convert_unit", {"amount": amount, "unit_raw": unit_raw, "per": quantity_in_unit},
        value, f"÷ {quantity_in_unit:g} ({unit_raw}) → ₹{value} per piece")}


def convert_currency(amount: float, currency: str) -> dict[str, Any]:
    if currency.upper() != "USD":
        raise ValueError(f"No event rate for currency '{currency}'")
    rate = POLICY["fx_usd_inr"]
    value = round(amount * rate, 2)
    return {"value": value, "transform": _step(
        "convert_currency", {"amount": amount, "currency": "USD", "rate": rate},
        value, f"× ₹{rate}/USD ({POLICY['fx_date']}) → ₹{value}")}


def estimate_box_weight_kg(length_mm: int, width_mm: int, height_mm: int, gsm_combined: int) -> dict[str, Any]:
    """Blank-area model: (2(L+W)+40) × (W+H+30) × gsm × 1.05 corrugation take-up."""
    area_m2 = ((2 * (length_mm + width_mm) + 40) / 1000) * ((width_mm + height_mm + 30) / 1000)
    kg = round(area_m2 * gsm_combined * 1.05 / 1000, 3)
    return {"value": kg, "transform": _step(
        "estimate_box_weight_kg",
        {"dims_mm": [length_mm, width_mm, height_mm], "gsm_combined": gsm_combined},
        kg, f"box weight ≈ {kg} kg from dimensions + grammage (±{POLICY['weight_tolerance_pct']:g}%)")}


def derive_weight_price(rate_per_kg: float, weight_kg: float) -> dict[str, Any]:
    value = round(rate_per_kg * weight_kg, 2)
    return {"value": value, "transform": _step(
        "derive_weight_price", {"rate_per_kg": rate_per_kg, "weight_kg": weight_kg},
        value, f"₹{rate_per_kg:g}/kg × {weight_kg} kg → ₹{value} per piece")}


def apply_freight_estimate(amount: float, weight_kg: float) -> dict[str, Any]:
    per_kg = POLICY["freight_est_inr_per_kg"]
    value = round(amount + per_kg * weight_kg, 2)
    return {"value": value, "transform": _step(
        "apply_freight_estimate", {"amount": amount, "weight_kg": weight_kg, "per_kg": per_kg},
        value, f"+ ₹{per_kg}/kg freight estimate ({POLICY['freight_lane']}) → ₹{value} delivered")}


def lookup_prior_award(code: str) -> dict[str, Any]:
    table = json.loads((DATA_DIR / "prior_award_fy26.json").read_text())
    hit: Optional[dict[str, Any]] = table.get(code)
    if hit is None:
        return {"value": None, "transform": _step(
            "lookup_prior_award", {"code": code}, None,
            f"no FY26 award record exists for {code} — reference cannot resolve")}
    return {"value": hit["inr_per_unit"], "transform": _step(
        "lookup_prior_award", {"code": code}, hit["inr_per_unit"],
        f"FY26 award record for {code}: ₹{hit['inr_per_unit']} ({hit['vendor']}) — vendor must restate before award")}


def annual_impact(code: str, delta_inr_per_unit: float) -> dict[str, Any]:
    """Annual ₹ impact of a per-unit uncertainty/decision on one line, banded."""
    import json as _json
    rfx = _json.loads((DATA_DIR / "rfx_fy27.json").read_text())
    qty = next((l["qty_per_month"] for l in rfx["lines"] if l["code"] == code), 0)
    impact = round(abs(delta_inr_per_unit) * qty * 12)
    band = "HIGH" if impact > 500_000 else ("MEDIUM" if impact >= 100_000 else "LOW")
    return {"value": impact, "band": band, "transform": _step(
        "annual_impact", {"code": code, "delta_inr_per_unit": delta_inr_per_unit},
        impact, f"₹{delta_inr_per_unit:g}/pc × {qty:,}/mo × 12 → ₹{impact:,}/yr ({band})")}


NORMALIZE_TOOLS = {
    "annual_impact": annual_impact,
    "get_policy": get_policy,
    "convert_unit": convert_unit,
    "convert_currency": convert_currency,
    "estimate_box_weight_kg": estimate_box_weight_kg,
    "derive_weight_price": derive_weight_price,
    "apply_freight_estimate": apply_freight_estimate,
    "lookup_prior_award": lookup_prior_award,
}

NORMALIZE_TOOL_SCHEMAS = [
    {"name": "annual_impact", "description": "Annual ₹ impact of a per-unit price uncertainty/decision on one RFx line, with HIGH/MEDIUM/LOW band.",
     "input_schema": {"type": "object", "properties": {
         "code": {"type": "string"}, "delta_inr_per_unit": {"type": "number"}},
         "required": ["code", "delta_inr_per_unit"]}},
    {"name": "get_policy", "description": "Event-wide policy: FX rate, freight estimate, tolerances, clearance rule.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "convert_unit", "description": "Convert an as-quoted amount to per-piece by dividing by the pack quantity.",
     "input_schema": {"type": "object", "properties": {
         "amount": {"type": "number"}, "unit_raw": {"type": "string"},
         "quantity_in_unit": {"type": "number"}}, "required": ["amount", "unit_raw", "quantity_in_unit"]}},
    {"name": "convert_currency", "description": "Convert USD to INR at the single dated event rate.",
     "input_schema": {"type": "object", "properties": {
         "amount": {"type": "number"}, "currency": {"type": "string"}}, "required": ["amount", "currency"]}},
    {"name": "estimate_box_weight_kg", "description": "Estimate one box's weight from dimensions and combined grammage.",
     "input_schema": {"type": "object", "properties": {
         "length_mm": {"type": "integer"}, "width_mm": {"type": "integer"},
         "height_mm": {"type": "integer"}, "gsm_combined": {"type": "integer"}},
         "required": ["length_mm", "width_mm", "height_mm", "gsm_combined"]}},
    {"name": "derive_weight_price", "description": "Per-piece price from a ₹/kg rate × estimated weight.",
     "input_schema": {"type": "object", "properties": {
         "rate_per_kg": {"type": "number"}, "weight_kg": {"type": "number"}},
         "required": ["rate_per_kg", "weight_kg"]}},
    {"name": "apply_freight_estimate", "description": "Add the policy freight estimate to an ex-works per-piece price.",
     "input_schema": {"type": "object", "properties": {
         "amount": {"type": "number"}, "weight_kg": {"type": "number"}},
         "required": ["amount", "weight_kg"]}},
    {"name": "lookup_prior_award", "description": "Resolve a 'same as last year' reference from the FY26 award table.",
     "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
]
