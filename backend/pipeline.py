"""The end-to-end loop: artifact → evidence agent → resolution agent → comparison store.

  python -m backend.pipeline ALPHA            # one vendor
  python -m backend.pipeline all              # all five
  python -m backend.pipeline CORRUG --show    # print the stored result

Buyer decisions (data/decisions.json) are injected into resolution as
`buyer_confirmed_facts`, so resolving a gate = re-running this pipeline for that vendor —
the loop stays real end to end.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")

from . import resolve_exec                               # noqa: E402
from .agent_runner import load_agent_config, run_agent   # noqa: E402
from .ingest import FILES_DIR, artifact_to_content       # noqa: E402
from .tools import POLICY                                # noqa: E402

DATA = ROOT / "data"


def parse_agent_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(json)?\s*|\s*```$", "", t, flags=re.S)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in agent output: {t[:300]}")
    return json.loads(t[start:end + 1])


def _load(name: str, default):
    p = DATA / name
    return json.loads(p.read_text()) if p.exists() else default


def _prog(vid: str, stage: str) -> None:
    """Record the pipeline's current phase so the UI can show honest progress —
    and survive page reloads (the truth lives server-side, not in the tab)."""
    import time
    d = _load("progress.json", {})
    prev = d.get(vid, {})
    run_ts = time.time() if stage == "evidence" else (prev.get("run_ts") or time.time())
    d[vid] = {"stage": stage, "ts": time.time(), "run_ts": run_ts}
    _save("progress.json", d)


def _save(name: str, obj) -> None:
    (DATA / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False))


def rfx_brief() -> dict:
    rfx = _load("rfx_fy27.json", {})
    return {
        "event": rfx.get("event_id"),
        "basis": {"currency": "INR", "unit": "per piece",
                  "delivery": rfx.get("delivery_basis"),
                  "payment_days": rfx.get("payment_terms_days")},
        "lines": [{"code": l["code"], "desc": l["description"],
                   "qty_per_month": l["qty_per_month"], "unit": l["unit"]}
                  for l in rfx.get("lines", [])],
        "questionnaire": [{"key": q["key"], "question": q["question"]}
                          for q in rfx.get("questionnaire", [])],
    }


def run_vendor(vid: str, resolution_only: bool = False) -> dict:
    vendors = _load("vendors.json", {})
    if vid not in vendors:
        raise SystemExit(f"unknown vendor {vid}; known: {sorted(vendors)}")
    v = vendors[vid]

    if resolution_only:
        ev_path = DATA / "evidence" / f"{vid}.json"
        if ev_path.exists():
            import time
            d = _load("progress.json", {})
            d[vid] = {"stage": "resolution", "ts": time.time(), "run_ts": time.time()}
            _save("progress.json", d)
            return _resolve(vid, json.loads(ev_path.read_text()), None)

    # ---- 1. evidence ----
    _prog(vid, "evidence")
    blocks = [{"type": "text", "text":
               "RFX (match against these lines; extract questionnaire answers by key):\n"
               + json.dumps(rfx_brief(), ensure_ascii=False)
               + f"\n\nVENDOR: {vid} ({v['name']}). Their response follows."}]
    image_as_path = load_agent_config("evidence")["provider"] == "claude_code"
    for fname in v["files"]:
        kind, content = artifact_to_content(fname)
        if kind == "image":
            if image_as_path:
                blocks.append({"type": "text", "text":
                               f"--- {fname} (photograph) ---\n"
                               f"Read this image file: {FILES_DIR / fname}"})
            else:
                blocks.append({"type": "text", "text": f"--- {fname} (photograph) ---"})
                blocks.append(content)
        else:
            blocks.append({"type": "text", "text": content})
    print(f"[{vid}] evidence agent…", flush=True)
    text, ev_trace = run_agent("evidence", blocks)
    evidence = parse_agent_json(text)
    evidence["vendor_id"] = vid
    (DATA / "evidence").mkdir(exist_ok=True)
    _save(f"evidence/{vid}.json", evidence)

    return _resolve(vid, evidence, ev_trace)


def _resolve(vid: str, evidence: dict, ev_trace) -> dict:
    # ---- 2. resolution ----
    _prog(vid, "resolution")
    facts = _load("decisions.json", {}).get(vid, {})
    rules = [r for r in _load("rules.json", []) if r.get("enabled")]
    res_input = {
        "rfx": rfx_brief(),
        "policy": POLICY,
        "buyer_confirmed_facts": facts,
        "standing_rules": rules,
        "evidence": evidence,
    }
    print(f"[{vid}] resolution agent…", flush=True)
    text, res_trace = run_agent("resolution", res_input)
    plan_doc = parse_agent_json(text)
    plan_doc["vendor_id"] = vid
    resolved = resolve_exec.execute(plan_doc, evidence)   # model proposed; code disposes

    cmp_ = _load("comparison.json", {})
    cmp_[vid] = resolved
    _save("comparison.json", cmp_)
    traces = _load("traces.json", {})
    prev = traces.get(vid, {})
    traces[vid] = {"evidence": ev_trace.model_dump() if ev_trace else prev.get("evidence"),
                   "resolution": res_trace.model_dump()}
    _save("traces.json", traces)

    _prog(vid, "done")
    states = {}
    for c in resolved.get("cells", []):
        states[c["state"]] = states.get(c["state"], 0) + 1
    print(f"[{vid}] done — cells {states}, exceptions {len(resolved.get('exceptions', []))}")
    return resolved


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: python -m backend.pipeline <VENDOR|all> [--show]")
    vendors = _load("vendors.json", {})
    targets = sorted(vendors) if args[0] == "all" else args
    if "--show" in sys.argv:
        cmp_ = _load("comparison.json", {})
        for t in targets:
            print(json.dumps(cmp_.get(t, {}), indent=1, ensure_ascii=False)[:4000])
        return
    for t in targets:
        run_vendor(t)


if __name__ == "__main__":
    main()
