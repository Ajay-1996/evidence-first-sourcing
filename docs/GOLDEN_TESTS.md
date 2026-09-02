# Golden dataset & edge-case tests

Two tiers: (A) the five fabricated vendors have **exact, deterministic ground truth** —
checked automatically; (B) freeform ugly files you generate have **behavioral goldens** —
checked by eye against the pass criteria.

## A. Built-in golden dataset (automated)

```bash
.venv/bin/python -m backend.pipeline all      # or process vendors in the UI
.venv/bin/python -m tests.golden_check        # 40+ assertions, exits non-zero on failure
```

Probe values the extraction must read **exactly** (as quoted, before any conversion):

| Line | Alpha ₹/pc | BoxCo ₹/pc | PackRight ₹/pc (ex-works) | Corrugated (as quoted) | GlobalPack (as quoted) |
|---|---|---|---|---|---|
| PKG-001 | 3.19 | 3.30 | 3.12 | Rs 320 / 100 pcs | Rs 3.21 /pc (csv) |
| PKG-007 | 5.45 | 5.64 | 5.33 | Rs 545 / 100 pcs | Rs 5.71 /pc (csv) |
| PKG-013 | 24.55 | *not quoted* | 23.48 | Rs 2,400 / case | Rs 25.16 /pc (csv) |
| PKG-015 | 42.30 | 42.83 | 40.62 | Rs 4,310 / case | Rs 43.53 /pc (csv) |
| PKG-022 | 74.96 | 73.31 | 71.22 | **BLURRED → must be null** | Rs 75.15 /pc (csv) |
| PKG-027 | 154.01 | 156.44 | 149.72 | Rs 15,890 / case | **USD 1.76 /pc** |
| PKG-030 | 288.20 | 297.32 | 284.00 | Rs 28,570 / case | **USD 3.26 /pc** |

Behavioral goldens per vendor (all asserted by `golden_check`):

- **Alpha** — 30/30 captured; no planted price exceptions (clean control).
- **BoxCo** — missing exactly PKG-006/-013/-023; `TERM_REFERENCE` (payment "same as last
  year", value never guessed); `QUESTIONNAIRE_GAP` on burst certs.
- **PackRight** — every normalized value = ex-works quote + ₹2.1/kg × box weight
  (`FREIGHT_BASIS`); 2.5% discount captured but **never applied**
  (`DISCOUNT_CONDITIONAL`); paper-index clause surfaced.
- **Corrugated** — per-100 rates read exactly; PKG-022 rate **null, never guessed**;
  pack factor undecided → ≥17 per-case lines gated + `PACK_FACTOR` exception; after the
  buyer records 102 → PKG-015 normalizes to 4,310 ÷ 102 = ₹42.25 and only the illegible
  line stays gated.
- **GlobalPack** — USD lines converted at exactly ₹83.60; email-vs-attachment freight
  contradiction surfaced (`FREIGHT_BASIS`/`SOURCE_CONFLICT`), never silently resolved.

## B. Freeform edge cases (behavioral goldens)

Generate with the prompts in the chat log (or your own), register via
`scripts/add_test_file.py <file>`, process "Test Supplier", judge against:

| # | Input | Golden behavior |
|---|---|---|
| 1 | Quote with no item codes, near-miss sizes | Low `match_confidence`, gates on doubtful matches — never a confident wrong attach |
| 2 | Mixed USD/INR + "₹42–46 depending on volume" | Ranges gated with a buyer question; currencies flagged; **never averaged** |
| 3 | Line totals ≠ rate×qty, inflated grand total | Arithmetic variance surfaced as an exception; unit rates trusted over broken totals, stated explicitly |
| 4 | Email body contradicts its own pasted table | Both values reported as a conflict; no winner picked |
| 5 | Prices clean, killer terms buried in prose | Discount/MOQ/advance/validity captured as **conditions**, none applied to prices |
| 6 | Wrong products entirely (plastic crates) | Everything lands in `unsolicited`/`unquoted`; zero forced matches |
| 7 | Photo of handwriting / photo of garbage | Honest low-confidence partial read, or "nothing extractable" — zero fabricated lines |

**Universal failure condition** (any case): a number in the output that does not appear in
the source document, or a match/conversion made without evidence and without a flag. That's
a bug — capture the file + line and fix the prompt, not the expectation.

## Cleanup before recording

```bash
.venv/bin/python -m backend.make_vendor_files && .venv/bin/python scripts/stage_demo.py
```
