# Demo — one narrative, ~5–6 minutes

**Two interchangeable UIs, one backend.** Primary: the Clearcut React app —
`cd frontend && npx vite --port 5174` → http://localhost:5174 (sidebar: RFx workspace /
Suppliers / Comparison / Analysis / Award brief; the beats below map 1:1 — Process lives on
the Suppliers page, decisions in its clarify sheet, evidence in the cell sheet). Fallback:
the single-file shell at http://localhost:8014. Both need the API running.

Prep: `.venv/bin/uvicorn backend.main:app --port 8014 --reload`, then
`.venv/bin/python scripts/stage_demo.py` (ALWAYS re-stage right before recording — exploring
the app changes its state). Open http://localhost:8014 and keep `data/vendor_files/` visible
in a second window. Navigation is a five-stage pipeline — 01 RFQ → 02 Responses → 03 Resolve
→ 04 Compare & Analyze (Grid / Questionnaire / Analyst) → 05 Award (soft-locked) — with a
readiness strip showing what's left before you can conclude. Gesture at it early: *"the
system always tells me what stage I'm in and what it still needs from me."*

Opening line, verbatim: *"One deliberate product decision: suppliers never adopt Parity.
They reply by email in whatever files they already use — the buyer is the only application
user. Parity absorbs the mess and only interrupts the buyer when ambiguity could materially
affect the award."*

**RFx — 20s.** "The buyer drafts this conversationally and approves before anything goes
out — 5 suppliers, email, 30 lines, 6 questionnaire items." (Optionally type one amendment
to show the co-pilot is live.) Move on.

**Responses — 60s.** "Four responses are already processed. GlobalPack is a two-line email
plus a CSV — I'll process that one live. This is not canned data; I'm triggering the actual
extraction and resolution pipeline now." While it runs, open **Details** on Corrugated:
received / captured / couldn't determine / requires you. Point at the badge: *"The model
found uncertainty across 18 lines — but they all stem from ONE unknown case-pack factor,
so Parity turns 18 uncertain cells into one decision."* When GlobalPack lands: it flagged,
on its own, that the email says freight-included while the attachment says ex-works — and
refused to pick.

**Decisions — 90s.** "Five messy files → a handful of decisions, ranked by what they could
do to the award. Everything else was handled automatically." On the pack-factor card:
**View source ›** (the claim is never just AI prose — there's the supplier's ink). Click
**Ask supplier** to show the drafted clarification email — that's the entire supplier-side
experience. Then resolve it: **Confirm factor → 102 → Save**. Note the semantics: a supplier
fact is *recorded* with how you know it, not manufactured by a click. Resolution re-runs
live (~2 min — narrate: model re-plans, code re-executes, decision hits the audit log).

**Rules moment — 30s (optional but strong).** After deciding PackRight's freight issue, the
matching issue on another supplier shows: *"⚡ You decided a similar freight-basis issue for
PackRight — set as standing rule?"* Open it, show the guardrails (every application is
marked on the cell; compliance can never be ruled away), and the **Standing rules** panel in
the readiness strip. Narrate: *"repeated decisions become governed policy — and the rule is
semantic: it only fires where its precondition actually holds, and its every application is
stamped on the cell it touched."* Create it live only if time allows (a recompute is ~2 min).

**Compare — 90s.** "Every bid on one basis. Gaps stay gaps — never ₹0. Unresolved values
say *held out* and stay out of the totals." Click a Corrugated cell: supplier ink →
extracted → pack factor (buyer-confirmed) → calculation → canonical value, with the
exposure if the factor were wrong. Click BoxCo's PKG-006 gap: NOT QUOTED, the supplier's
own words, excluded — not zero. Flip the pill to **Questionnaire**: answers beside the
numbers, evidence quoted, attachments listed, blanks counting against clearance — the
brief's requirement, on one screen.

**Analyst — 90s.** Ask the brief's own question: *"Split the award cheapest per line, but
only among vendors who cleared the quality questionnaire — what does the constraint cost?"*
Headline number → allocation table → exclusions → ⚠ assumptions → basis. Follow with
*"What material risks remain before I award?"* — it even flags that the freight estimate's
lane doesn't match PackRight's origin: it second-guesses its own policy inputs too.

**Close — 20s.** *"The supplier never adopted Parity. The buyer never retyped a quote. And
every value in the recommendation traces back to supplier evidence, through transformations
a human can audit, with the ambiguities resolved on the record. Parity doesn't make
suppliers cleaner — it makes supplier mess decision-safe."*

Fallbacks: if a live call stalls, keep narrating from the evidence chain on screen; the
state already rendered is real. Full reset: `scripts/reset_demo.sh` + `python -m
backend.pipeline all`; re-stage: `scripts/stage_demo.py`.
