# Parity — Kill the Quote Spreadsheet

One flow, end to end: an RFx goes out, five suppliers reply in five different shapes —
a clean Excel, a Word doc, a PDF with the commercials in footnotes, a photographed rate
card, a two-line email contradicting its own attachment — and every number lands on one
basis with its chain of custody intact. The buyer decides only what's materially uncertain,
then interrogates the comparison in plain language.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m backend.seed_data          # the RFx (30 lines) + FY26 award table
.venv/bin/python -m backend.make_vendor_files  # fabricate the five supplier artifacts
.venv/bin/uvicorn backend.main:app --port 8014 # API + fallback UI at http://localhost:8014
```

**Primary UI (Clearcut design, React)** — same backend, richer front end:

```bash
cd frontend && npm install && npx vite --port 5174   # UI at http://localhost:5174
```

`frontend/` is the Clearcut UI/UX migrated onto this agent layer: its synthetic data module
was replaced by `frontend/lib/live.ts`, which reads the canonical comparison from the API and
drives every action (Process, decisions, analyst, co-pilot) through the real pipeline.
The single-file shell at `http://localhost:8014/` remains as a dependency-free fallback.

**Model runtime — two interchangeable providers** (`models.yaml`):
- `claude_code` (default): agents run through the local `claude` CLI in headless mode, on a
  Claude subscription. No API key. Requires Claude Code installed and logged in.
- `anthropic`: raw API. Put `ANTHROPIC_API_KEY=...` in `.env.local` (plus
  `ANTHROPIC_WORKSPACE_ID=...` for identity-linked keys) and flip the provider per agent.

Ingest vendors from the **Responses** tab (or `.venv/bin/python -m backend.pipeline all`).
`scripts/reset_demo.sh` returns the event to its pre-ingestion state.

## The architecture in one paragraph

Evidence interpretation is separated from calculation and decision-making. A model reads the
messy artifact and reports **what the supplier said** — as-quoted values, provenance
(sheet+cell / page+excerpt / image region), conditions, conflicts, gaps — but never converts
anything. A second model pass **classifies** how each line reaches the common basis (per-100,
pack factor, USD, ₹/kg × weight, gate, missing) and proposes typed exceptions. Then
**deterministic code executes that plan**: every conversion is a tool function whose output
becomes the cell's transform chain, and every exception's ₹ impact is computed and banded
(HIGH > ₹5L / MEDIUM ₹1–5L / LOW; compliance gaps are AWARD_BLOCKING, no invented rupees).
Anything the evidence can't establish — a smudged pack factor, an illegible rate, "same as
last year" — is **gated, never guessed**: it becomes a buyer decision, and deciding it
re-runs resolution with the fact on record, so the loop stays real end to end. The analyst
answers questions in two phases: it plans read-only queries, code executes them over the
canonical data, and the model explains the computed results with an explicit basis paragraph.
The comparison table is just a projection; the evidence-bearing canonical model is the truth.

## Map

| Piece | Where |
|---|---|
| Agent behaviour (editable markdown, hot-reloaded per call) | `agents/evidence.md`, `resolution.md`, `analyst.md`, `draft.md` |
| Model routing per agent | `models.yaml` |
| Provider seam (claude_code / anthropic / mock) | `backend/providers.py` |
| Shared runner + traces | `backend/agent_runner.py` |
| Deterministic parsers (xlsx/pdf/docx/email; images pass to vision) | `backend/ingest.py` |
| Pipeline: artifact → evidence → plan → executed cells | `backend/pipeline.py`, `backend/resolve_exec.py` |
| Conversion & impact tools (all arithmetic lives here) | `backend/tools.py` |
| Store, qualification, buyer decisions, analyst query tools | `backend/store.py` |
| API + demo shell | `backend/main.py`, `prototype/shell.html` |
| The five fabricated suppliers | `backend/make_vendor_files.py` → `data/vendor_files/` |
| Keyless plumbing tests | `tests/smoke_test.py` |

## What's stubbed (deliberately)

SMTP/outbound clarifications, exports, auth, persistence beyond JSON files, and the early
UX exploration in `prototype/parity.html`. The AI loops — reading all five artifacts
(including the photo), the normalization plan, gate re-resolution, and the analyst — are
real model calls at demo time, per the brief's one rule.
