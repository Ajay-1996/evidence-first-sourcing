"""API for the demo shell. Thin: every AI route hands off to the pipeline/runner.
Run:  .venv/bin/uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException          # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel                      # noqa: E402

from . import pipeline, store                       # noqa: E402
from .agent_runner import load_agent_config, run_agent  # noqa: E402
from .tools import POLICY                           # noqa: E402

app = FastAPI(title="Parity agent layer", version="0.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/shell")
def shell():
    """Dependency-free fallback UI."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse((ROOT / "prototype" / "shell.html").read_text())


@app.get("/health")
def health() -> dict[str, Any]:
    import os
    return {"ok": True, "key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "agents": {a: load_agent_config(a) for a in ("draft", "evidence", "resolution", "analyst")}}


@app.get("/rfx")
def rfx() -> Any:
    return json.loads((ROOT / "data" / "rfx_fy27.json").read_text())


@app.get("/vendors")
def vendors() -> Any:
    return json.loads((ROOT / "data" / "vendors.json").read_text())


@app.get("/compare")
def compare() -> Any:
    """Everything the shell needs in one call — the comparison is a projection."""
    log_p = ROOT / "data" / "decision_log.json"
    return {"comparison": store.load_comparison(),
            "open_items": store.get_open_items(),
            "qualification": store.qualification(),
            "decisions": store.load_decisions(),
            "decision_log": json.loads(log_p.read_text()) if log_p.exists() else [],
            "rules": store.load_rules(),
            "policy": POLICY}


class RuleBody(BaseModel):
    op: str                      # create | toggle | delete
    rule_id: Optional[str] = None
    rtype: Optional[str] = None
    action: Optional[str] = None
    label: Optional[str] = None
    created_from: Optional[dict[str, Any]] = None


@app.post("/rules")
def rules(body: RuleBody) -> Any:
    if body.op == "create":
        try:
            return store.create_rule(body.rtype or "", body.action or "",
                                     body.label or body.rtype or "rule",
                                     body.created_from or {})
        except ValueError as e:
            raise HTTPException(400, str(e))
    rs = store.load_rules()
    for r in rs:
        if r["id"] == body.rule_id:
            if body.op == "toggle":
                r["enabled"] = not r["enabled"]
            elif body.op == "delete":
                rs.remove(r)
            break
    store.save_rules(rs)
    return rs


@app.get("/progress/{vendor_id}")
def progress(vendor_id: str) -> Any:
    """Current pipeline phase for a vendor — lets the UI show honest, reload-proof progress."""
    p = ROOT / "data" / "progress.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    return d.get(vendor_id, {"stage": "idle"})


@app.post("/rerun/{vendor_id}")
def rerun(vendor_id: str) -> Any:
    """Recompute one vendor's resolution with current facts + rules (evidence reused)."""
    try:
        return pipeline.run_vendor(vendor_id, resolution_only=True)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


@app.get("/evidence/{vendor_id}")
def evidence(vendor_id: str) -> Any:
    p = ROOT / "data" / "evidence" / f"{vendor_id}.json"
    if not p.exists():
        raise HTTPException(404, f"No evidence stored for {vendor_id} — ingest first.")
    return json.loads(p.read_text())


@app.post("/ingest/{vendor_id}")
def ingest(vendor_id: str) -> Any:
    """Run the REAL pipeline for one vendor: artifact → evidence agent → resolution agent."""
    try:
        return pipeline.run_vendor(vendor_id)
    except Exception as e:
        raise HTTPException(500, f"{type(e).__name__}: {e}")


class DecideBody(BaseModel):
    facts: dict[str, Any]          # e.g. {"CORRUG_case_pack_pieces": 102}
    note: str = ""
    rerun: bool = True


@app.post("/decide/{vendor_id}")
def decide(vendor_id: str, body: DecideBody) -> Any:
    """Buyer resolves a gate. The fact is recorded, then resolution re-runs WITH it."""
    store.record_decision(vendor_id, body.facts, body.note)
    if body.rerun:
        try:
            # evidence is unchanged by a buyer decision — re-run resolution only (fast)
            return {"decided": body.facts,
                    "rerun": pipeline.run_vendor(vendor_id, resolution_only=True)}
        except Exception as e:
            raise HTTPException(500, f"decision recorded, re-run failed: {e}")
    return {"decided": body.facts}


class AskBody(BaseModel):
    question: str


@app.post("/analyst/ask")
def analyst_ask(body: AskBody) -> Any:
    if not store.load_comparison():
        raise HTTPException(409, "No comparison yet — ingest responses first.")
    # phase 1 — the model plans read-only queries
    catalog = [{"tool": t["name"], "description": t["description"],
                "args": list(t["input_schema"].get("properties", {}))}
               for t in store.ANALYST_TOOL_SCHEMAS]
    text, t1 = run_agent("analyst", {"phase": "plan", "question": body.question,
                                     "tool_catalog": catalog})
    plan = pipeline.parse_agent_json(text)
    # phase 2 — code executes them
    results = []
    for call in (plan.get("calls") or [])[:8]:
        fn = store.ANALYST_TOOLS.get(call.get("tool"))
        if fn is None:
            results.append({"call": call, "error": "unknown tool"})
            continue
        try:
            results.append({"call": call, "result": fn(**(call.get("args") or {}))})
        except Exception as e:
            results.append({"call": call, "error": f"{type(e).__name__}: {e}"})
    # phase 3 — the model explains what the code computed
    text, t2 = run_agent("analyst", {"phase": "explain", "question": body.question,
                                     "executed": results})
    try:
        answer = pipeline.parse_agent_json(text)
    except Exception:
        answer = {"prose": text, "tables": [], "citations": [], "basis": ""}
    return {"answer": answer, "plan": plan,
            "trace": {"plan": t1.model_dump(), "explain": t2.model_dump()}}


class DraftBody(BaseModel):
    message: str
    history: Optional[list[dict[str, str]]] = None


@app.post("/draft/chat")
def draft_chat(body: DraftBody) -> Any:
    rfx_ = json.loads((ROOT / "data" / "rfx_fy27.json").read_text())
    text, trace = run_agent(
        "draft", {"message": body.message, "history": body.history or [],
                  "current_rfx_summary": {"lines": len(rfx_["lines"]),
                                          "questionnaire": len(rfx_["questionnaire"]),
                                          "basis": rfx_["delivery_basis"],
                                          "payment_days": rfx_["payment_terms_days"]}},
    )
    return {"reply_raw": text, "trace": trace.model_dump()}


# Serve the built React app (frontend/dist) at / when it exists — single-origin deploys.
_DIST = ROOT / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="app")
