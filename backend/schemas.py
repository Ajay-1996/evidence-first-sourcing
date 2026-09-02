"""Provenance-first data contracts. Every price that reaches a screen traces back
through these types to a locator + snippet in the vendor's own document."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------- RFx ----------

class LineItem(BaseModel):
    code: str
    description: str
    length_mm: int
    width_mm: int
    height_mm: int
    ply: int
    gsm_combined: int
    print: str = ""              # "" | "1c" | "2c"
    qty_per_month: int
    unit: str = "piece"
    is_new: bool = False


class QuestionnaireItem(BaseModel):
    key: str
    question: str
    answer_type: Literal["boolean", "number", "text", "attachment"] = "text"


class RFx(BaseModel):
    event_id: str
    title: str
    buyer: str
    delivery_basis: str = "Delivered (FOR Bhiwandi DC)"
    payment_terms_days: int = 45
    validity_months: int = 12
    currency: str = "INR"
    lines: list[LineItem]
    questionnaire: list[QuestionnaireItem]


# ---------- extraction (as-quoted; no conversions here) ----------

class SourceRef(BaseModel):
    locator: str                 # "sheet Rates · row 6" / "p.2 export table" / "image region ..."
    snippet: str                 # verbatim-ish evidence


class AsQuoted(BaseModel):
    amount: Optional[float] = None   # None = stated but unreadable, or reference to elsewhere
    currency: str = "INR"
    unit_raw: str                    # "per 100 pcs" / "per piece" / "per kg" / "unstated"


class ExtractedLine(BaseModel):
    code: str
    match_confidence: float
    match_basis: str
    as_quoted: AsQuoted
    confidence: float
    source_ref: SourceRef
    conditions: list[str] = []
    flags: list[str] = []
    note: Optional[str] = None


class QuestionnaireAnswer(BaseModel):
    key: str
    answer_raw: Optional[str] = None
    evidence: Optional[str] = None
    confidence: float = 0.0


class QuoteExtract(BaseModel):
    vendor_id: str
    lines: list[ExtractedLine]
    unquoted: list[dict[str, str]] = []          # {code, reason}
    unsolicited: list[str] = []
    questionnaire: list[QuestionnaireAnswer] = []
    vendor_terms: dict[str, Any] = {}
    reading_notes: str = ""


# ---------- normalization ----------

class CellState(str, Enum):
    confirmed = "confirmed"
    assumed = "assumed"
    needs_review = "needs_review"
    missing = "missing"
    excluded = "excluded"


class TransformStep(BaseModel):
    tool: str
    inputs: dict[str, Any]
    output: Any
    text: str                    # buyer-readable sentence


class NormalizedCell(BaseModel):
    vendor_id: str
    code: str
    normalized_inr_per_unit: Optional[float] = None
    state: CellState
    flags: list[str] = []
    transform_chain: list[TransformStep] = []
    as_quoted: Optional[AsQuoted] = None
    source_ref: Optional[SourceRef] = None
    confidence: float = 0.0
    buyer_question: Optional[str] = None


class PolicyDecision(BaseModel):
    id: str
    vendor_id: str
    title: str
    detail: str
    default: str
    decided: Optional[str] = None
    decided_by: Optional[str] = None


class NormalizedQuote(BaseModel):
    vendor_id: str
    cells: list[NormalizedCell]
    policy_decisions: list[PolicyDecision] = []


# ---------- analyst ----------

class ChartSpec(BaseModel):
    type: Literal["bars", "stack"]
    rows: list[dict[str, Any]]


class AnalystAnswer(BaseModel):
    prose: str
    tables: list[dict[str, Any]] = []
    chart: Optional[ChartSpec] = None
    citations: list[dict[str, str]] = []         # {vendor, line}
    basis: str


# ---------- agent runner plumbing ----------

class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentTrace(BaseModel):
    """The 'show your working' record kept alongside every agent output."""
    agent: str
    provider: str
    model: str
    steps: list[dict[str, Any]] = []
