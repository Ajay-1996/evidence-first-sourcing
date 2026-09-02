"""Stage the exact demo opening state:
  - four vendors ingested (ALPHA, BOXCO, PACKRT, CORRUG), GLOBAL left for LIVE ingestion
  - no buyer decisions yet, so CORRUG sits gated on the pack factor (the marquee moment)
Requires a prior full run (data/evidence/*.json present).  Run:
  .venv/bin/python scripts/stage_demo.py
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

cmp_p = DATA / "comparison.json"
cmp_ = json.loads(cmp_p.read_text()) if cmp_p.exists() else {}
if "GLOBAL" in cmp_:
    del cmp_["GLOBAL"]
cmp_p.write_text(json.dumps(cmp_, indent=1, ensure_ascii=False))
(DATA / "evidence" / "GLOBAL.json").unlink(missing_ok=True)

# vendors whose state was touched by decisions/rules must be recomputed clean
dec_p = DATA / "decisions.json"
touched = set(json.loads(dec_p.read_text()).keys()) if dec_p.exists() else set()
for vid, q in cmp_.items():  # rule-applied cells also mean non-pristine state
    if any("rule_applied" in (c.get("flags") or []) for c in q.get("cells", [])):
        touched.add(vid)
touched.discard("EVENT"); touched.discard("GLOBAL"); touched.add("CORRUG")
for f in ("decisions.json", "decision_log.json", "rules.json"):
    (DATA / f).unlink(missing_ok=True)

for vid in sorted(touched):
    print(f"Restoring {vid} to its pristine pre-decision state (resolution only)…")
    subprocess.run([str(ROOT / ".venv/bin/python"), "-c",
                    f"from backend.pipeline import run_vendor; run_vendor('{vid}', resolution_only=True)"],
                   cwd=ROOT, check=True)
print("Staged: 4 vendors in (CORRUG gated), GLOBAL ready for live ingestion, no decisions, no rules.")
