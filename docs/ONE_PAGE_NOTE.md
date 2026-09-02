# What I decided, and what I deliberately left out

**The problem I chose to solve.** Not "normalize bids with AI" — accept off-template
supplier evidence, build a canonical bid model with lineage, and ask a human only about
*materially important* uncertainty. The comparison table is a projection; the
evidence-bearing model underneath is the source of truth.

**The architecture is one separation, applied three times.** Models interpret; code
computes; humans decide. The **evidence agent** reads any artifact — Excel, Word, PDF,
a photographed rate card, a bare email — and reports what the supplier said, with
provenance (sheet+cell, page+excerpt, image region) and no conversions. The **resolution
agent** only *classifies* how each line reaches ₹/piece delivered (per-100, pack factor,
USD, ₹/kg×weight, gate, missing); a deterministic executor performs every conversion and
writes the transform chain — no model ever does arithmetic. The **analyst** answers in two
phases: it plans read-only queries, code executes them, and it explains the computed
results, ending every answer with its basis. Prompts live in editable markdown; models are
routed per-agent in one YAML — the layer runs on a Claude subscription via the local CLI or
on the raw API by dropping a key in `.env.local`, and swapping a frontier model is one line.

**The rule I held hardest: unsafe inference is never presented as automation.** The rate
card prices per case and the case size is smudged — the system gates 18 lines rather than
guess, tells the buyer the one fact it needs, and re-resolves live once it's confirmed,
with the decision cited in every affected chain. An illegible price gates; a missing line
stays an honest gap, never a zero. When the email said "freight included" and its own
attachment said ex-works, the system surfaced both and refused to pick a winner.

**Decisions compound into policy.** When the same issue type recurs, Parity offers to
promote the buyer's earlier call into a standing rule. Rules are governed, not silent:
every application is stamped on the cell it touched (`rule_applied`, with the rule's id in
the audit chain), the rule registry shows provenance and can be disabled at will, rules are
applied semantically (only where the precondition actually holds — an ambiguous freight
basis does not trigger a freight-exclusion rule), and compliance gaps can never be ruled
away. Over time, AI uncertainty converts into deterministic, human-owned policy.

**Materiality is a calculation, not an engine.** Exceptions are typed, first-class data.
Price-affecting ones get an annual ₹ impact computed from the actual quantities and banded
(HIGH > ₹5L / MEDIUM / LOW); compliance gaps are AWARD_BLOCKING with no invented rupees.
A conditional discount incompatible with the payment terms is recorded and *not* applied
— a discount you won't earn is bait, not a price.

**What I deliberately left out.** Supplier portals, discovery, auctions, POs, ERP, real
email transport and exports (stubbed, per the brief); a database (JSON files carry the
demo; the schema is the contribution); bounding-box highlights (locator + excerpt gives
most of the trust at a fraction of the cost); a workflow engine and extra agents — three
model roles plus a thin drafting co-pilot are enough, and every additional agent would
have added architecture without adding trust; general revision management (one honest
conflict beats a version tree); and polish on the RFx co-pilot, because the graded heart
of this product is what happens after the vendors reply.

**What I'd build next.** The clarification loop back to suppliers as a first-class
exception state; extraction eval suites against a corpus of real documents; per-cell
correction feedback into the prompts; and the award memo export with the decision log as
its audit appendix — the data for it already exists on disk.
