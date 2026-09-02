"""Golden-dataset check: validates a live pipeline run (data/comparison.json) against the
deterministic ground truth baked into the five fabricated vendor artifacts.

  .venv/bin/python -m tests.golden_check

Run it after `python -m backend.pipeline all` (or after processing vendors in the UI).
Exact checks on as-quoted values (the model must read the document faithfully); tolerant
checks on normalized values (rounding); presence checks on planted exceptions.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from backend.make_vendor_files import CASE_PACK, FX, ROWS, _jit, base_pc  # noqa: E402
from backend.seed_data import _weight_kg  # noqa: E402

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
FREIGHT = 2.1
PASS, FAIL = 0, 0


def check(ok: bool, msg: str) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ✗ FAIL {msg}")


def cell(q, code):
    return next((c for c in q.get("cells", []) if c.get("code") == code), None)


def aq(q, code):
    c = cell(q, code)
    return (c or {}).get("as_quoted") or {}


def has_exc(q, *types):
    return any(e.get("type") in types for e in q.get("exceptions", []))


def main() -> None:
    cmp_ = json.loads((DATA / "comparison.json").read_text()) if (DATA / "comparison.json").exists() else {}
    dec = json.loads((DATA / "decisions.json").read_text()) if (DATA / "decisions.json").exists() else {}
    if not cmp_:
        raise SystemExit("No comparison.json — process vendors first.")

    G = {}  # golden per code
    for c, L, W, H, ply, gsm, prn, qty in ROWS:
        G[c] = {
            "ply": ply, "printed": bool(prn), "w": _weight_kg(L, W, H, gsm),
            "alpha": round(base_pc(c, L, W, H, ply, gsm) * _jit("ALPHA" + c), 2),
            "boxco": None if prn else round(base_pc(c, L, W, H, ply, gsm)
                     * (1.035 if ply == 3 else (0.995 if ply == 5 else 1.01)) * _jit("BOXCO" + c), 2),
            "packrt": round(base_pc(c, L, W, H, ply, gsm) * 0.962 * _jit("PACKRT" + c), 2),
            "cor100": round(base_pc(c, L, W, H, ply, gsm) * 0.99 * _jit("CORRUG" + c) * 100 / 5) * 5 if ply == 3 else None,
            "corcase": None if ply == 3 else round(base_pc(c, L, W, H, ply, gsm) * 0.985 * _jit("CORRUG" + c) * CASE_PACK / 10) * 10,
            "glob_usd": round(base_pc(c, L, W, H, ply, gsm) * 0.952 * _jit("GLOBAL" + c) / FX, 2) if ply == 7 else None,
            "glob_inr": None if ply == 7 else round(base_pc(c, L, W, H, ply, gsm) * 1.02 * _jit("GLOBAL" + c), 2),
        }
    probes = ["PKG-001", "PKG-007", "PKG-013", "PKG-015", "PKG-027", "PKG-030"]

    if "ALPHA" in cmp_:
        q = cmp_["ALPHA"]
        print("ALPHA (clean control)")
        check(sum(1 for c in q["cells"] if c["state"] != "missing") == 30, "30/30 lines captured")
        for p in probes:
            check(abs((aq(q, p).get("amount") or 0) - G[p]["alpha"]) < 0.011,
                  f"{p} as-quoted {aq(q, p).get('amount')} vs golden {G[p]['alpha']}")
        check(not has_exc(q, "FREIGHT_BASIS", "SOURCE_CONFLICT", "PACK_FACTOR"),
              "no planted price exceptions (control must stay clean)")

    if "BOXCO" in cmp_:
        q = cmp_["BOXCO"]
        print("BOXCO (27/30 + references)")
        missing = sorted(c["code"] for c in q["cells"] if c["state"] == "missing")
        check(missing == ["PKG-006", "PKG-013", "PKG-023"], f"missing exactly the 3 printed lines, got {missing}")
        for p in ["PKG-001", "PKG-015", "PKG-027"]:
            check(abs((aq(q, p).get("amount") or 0) - G[p]["boxco"]) < 0.011,
                  f"{p} as-quoted {aq(q, p).get('amount')} vs golden {G[p]['boxco']}")
        check(has_exc(q, "TERM_REFERENCE"), "TERM_REFERENCE ('same as last year' payment) surfaced")
        check(has_exc(q, "QUESTIONNAIRE_GAP"), "QUESTIONNAIRE_GAP (burst certs) surfaced")

    if "PACKRT" in cmp_:
        q = cmp_["PACKRT"]
        print("PACKRT (ex-works + footnotes)")
        for p in probes:
            check(abs((aq(q, p).get("amount") or 0) - G[p]["packrt"]) < 0.011,
                  f"{p} as-quoted {aq(q, p).get('amount')} vs golden {G[p]['packrt']}")
            c = cell(q, p)
            if c and c.get("normalized_inr_per_unit") is not None:
                want = G[p]["packrt"] + FREIGHT * G[p]["w"]
                check(abs(c["normalized_inr_per_unit"] - want) < max(0.06, want * 0.006),
                      f"{p} normalized {c['normalized_inr_per_unit']} ≈ quoted+freight {round(want,2)}")
                check(c["normalized_inr_per_unit"] >= G[p]["packrt"],
                      f"{p} discount NOT applied (normalized ≥ ex-works quote)")
        check(has_exc(q, "FREIGHT_BASIS"), "FREIGHT_BASIS exception surfaced")
        check(has_exc(q, "DISCOUNT_CONDITIONAL"), "DISCOUNT_CONDITIONAL exception surfaced")

    if "CORRUG" in cmp_:
        q = cmp_["CORRUG"]
        decided = bool((dec.get("CORRUG") or {}).get("case_pack_pieces"))
        print(f"CORRUG (photo; pack factor {'decided=102' if decided else 'undecided'})")
        for p in ["PKG-001", "PKG-007"]:
            check(abs((aq(q, p).get("amount") or 0) - G[p]["cor100"]) < 0.011,
                  f"{p} per-100 as-quoted {aq(q, p).get('amount')} vs golden {G[p]['cor100']}")
        check(aq(q, "PKG-022").get("amount") is None, "PKG-022 blurred rate reported as null (never guessed)")
        gated = [c["code"] for c in q["cells"] if c["state"] == "needs_review"]
        if decided:
            c15 = cell(q, "PKG-015")
            want = round(G["PKG-015"]["corcase"] / (dec["CORRUG"]["case_pack_pieces"]), 2)
            check(c15 and abs((c15.get("normalized_inr_per_unit") or 0) - want) < 0.02,
                  f"PKG-015 normalized {c15 and c15.get('normalized_inr_per_unit')} == case/{dec['CORRUG']['case_pack_pieces']} = {want}")
            check(len(gated) <= 2, f"after decision ≤2 gated remain (illegible), got {len(gated)}")
        else:
            check(len(gated) >= 17, f"pack factor undecided → ≥17 per-case lines gated, got {len(gated)}")
            check(has_exc(q, "PACK_FACTOR"), "PACK_FACTOR exception surfaced")
            check(abs((aq(q, "PKG-015").get("amount") or 0) - G["PKG-015"]["corcase"]) < 0.011,
                  f"PKG-015 per-case as-quoted {aq(q,'PKG-015').get('amount')} vs golden {G['PKG-015']['corcase']}")

    if "GLOBAL" in cmp_:
        q = cmp_["GLOBAL"]
        print("GLOBAL (USD + conflict)")
        for p in ["PKG-027", "PKG-030"]:
            check(abs((aq(q, p).get("amount") or 0) - G[p]["glob_usd"]) < 0.011,
                  f"{p} USD as-quoted {aq(q, p).get('amount')} vs golden {G[p]['glob_usd']}")
            c = cell(q, p)
            if c and c.get("normalized_inr_per_unit") is not None:
                want = round(G[p]["glob_usd"] * FX, 2)
                check(abs(c["normalized_inr_per_unit"] - want) < max(0.05, want * 0.004),
                      f"{p} normalized {c['normalized_inr_per_unit']} == USD×{FX} = {want}")
        check(abs((aq(q, "PKG-001").get("amount") or 0) - G["PKG-001"]["glob_inr"]) < 0.011,
              f"PKG-001 csv as-quoted {aq(q,'PKG-001').get('amount')} vs golden {G['PKG-001']['glob_inr']}")
        check(has_exc(q, "FREIGHT_BASIS", "SOURCE_CONFLICT"),
              "email-vs-attachment freight conflict surfaced")

    absent = [v for v in ("ALPHA", "BOXCO", "PACKRT", "CORRUG", "GLOBAL") if v not in cmp_]
    if absent:
        print(f"(skipped — not processed: {', '.join(absent)})")
    print(f"\nGOLDEN CHECK: {PASS} passed, {FAIL} failed" + (" — ALL GOOD" if not FAIL else ""))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
