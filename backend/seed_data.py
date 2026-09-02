"""Seed the event: the FY27 RFx (30 corrugated lines) and the FY26 prior-award table
that "same as last year" references resolve against. Run:  python -m backend.seed_data
"""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import LineItem, QuestionnaireItem, RFx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# code, L, W, H, ply, gsm_combined, print, qty/month, new-in-FY27
SKUS = [
    ("PKG-001", 200, 150, 100, 3, 390, "", 9000, 0), ("PKG-002", 240, 180, 120, 3, 400, "", 8000, 0),
    ("PKG-003", 300, 200, 150, 3, 400, "", 7500, 0), ("PKG-004", 300, 250, 200, 3, 410, "", 6200, 0),
    ("PKG-005", 350, 250, 200, 3, 410, "", 7000, 0), ("PKG-006", 400, 300, 250, 3, 420, "1c", 6500, 0),
    ("PKG-007", 250, 200, 150, 3, 395, "", 4000, 0), ("PKG-008", 450, 350, 300, 3, 430, "", 3600, 0),
    ("PKG-009", 400, 400, 300, 3, 430, "", 3000, 0), ("PKG-010", 350, 300, 250, 3, 415, "", 4500, 0),
    ("PKG-011", 500, 400, 350, 3, 435, "", 2400, 0), ("PKG-012", 300, 300, 300, 3, 420, "", 3300, 0),
    ("PKG-013", 400, 300, 300, 5, 620, "2c", 5000, 0), ("PKG-014", 450, 350, 350, 5, 640, "", 4500, 0),
    ("PKG-015", 500, 400, 400, 5, 650, "", 4200, 0), ("PKG-016", 550, 450, 400, 5, 660, "", 3600, 0),
    ("PKG-017", 600, 400, 400, 5, 660, "", 3900, 0), ("PKG-018", 600, 500, 450, 5, 680, "", 2800, 0),
    ("PKG-019", 450, 450, 400, 5, 650, "", 3400, 0), ("PKG-020", 500, 500, 450, 5, 670, "", 2500, 0),
    ("PKG-021", 650, 500, 450, 5, 680, "", 2100, 0), ("PKG-022", 700, 500, 500, 5, 690, "", 1700, 0),
    ("PKG-023", 550, 550, 500, 5, 680, "1c", 2000, 0), ("PKG-024", 600, 600, 500, 5, 690, "", 1400, 1),
    ("PKG-025", 750, 550, 500, 5, 700, "", 1300, 0), ("PKG-026", 800, 600, 550, 5, 700, "", 1100, 1),
    ("PKG-027", 800, 600, 600, 7, 940, "", 700, 0), ("PKG-028", 900, 700, 600, 7, 950, "", 550, 0),
    ("PKG-029", 1000, 800, 700, 7, 960, "", 420, 0), ("PKG-030", 1100, 800, 800, 7, 980, "", 350, 1),
]

QUESTIONNAIRE = [
    ("iso", "Valid ISO 9001:2015 certificate", "attachment"),
    ("burst", "Burst-strength test certs for quoted grades (BS as per IS 2771)", "attachment"),
    ("fsc", "FSC chain-of-custody for kraft supply", "boolean"),
    ("lead", "Standard lead time, order → delivery (days)", "number"),
    ("pay", "45-day payment terms accepted", "boolean"),
    ("cap", "Spare capacity headroom on current volumes (%)", "number"),
]


def _weight_kg(L: int, W: int, H: int, gsm: int) -> float:
    area = ((2 * (L + W) + 40) / 1000) * ((W + H + 30) / 1000)
    return round(area * gsm * 1.05 / 1000, 3)


def build_rfx() -> RFx:
    lines = []
    for code, L, W, H, ply, gsm, prn, qty, new in SKUS:
        desc = f"RSC {L}×{W}×{H}, {ply}-ply" + (
            f", printed {'1-col' if prn == '1c' else '2-col'}" if prn else ", plain")
        lines.append(LineItem(code=code, description=desc, length_mm=L, width_mm=W, height_mm=H,
                              ply=ply, gsm_combined=gsm, print=prn, qty_per_month=qty,
                              is_new=bool(new)))
    return RFx(
        event_id="RFQ-FY27-CORR",
        title="FY27 Corrugated Packaging — Annual Rate Contract",
        buyer="Priya Nair · Suraksha Consumer Products",
        lines=lines,
        questionnaire=[QuestionnaireItem(key=k, question=q, answer_type=t)
                       for k, q, t in QUESTIONNAIRE],
    )


def build_prior_award() -> dict:
    """FY26 award existed for all non-new lines; 7-ply entries are what 'same as last year'
    resolves to (awarded ~4% under this year's base market)."""
    table = {}
    for code, L, W, H, ply, gsm, prn, qty, new in SKUS:
        if new:
            continue
        base_per_kg = {3: 37.5, 5: 41.0, 7: 45.0}[ply]
        table[code] = {"inr_per_unit": round(_weight_kg(L, W, H, gsm) * base_per_kg * 0.96, 2),
                       "vendor": "Apex Corrugators" if ply == 7 else "Shree Ganesh Packwell",
                       "fy": "FY26"}
    return table


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "rfx_fy27.json").write_text(build_rfx().model_dump_json(indent=1))
    (DATA_DIR / "prior_award_fy26.json").write_text(json.dumps(build_prior_award(), indent=1))
    print(f"Seeded {DATA_DIR}/rfx_fy27.json (30 lines) and prior_award_fy26.json")


if __name__ == "__main__":
    main()
