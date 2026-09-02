/* Live data layer — replaces the synthetic lib/procurement.ts entirely.
   Same backend as the original shell: FastAPI + real evidence/resolution/analyst agents. */

/* API base: explicit VITE_API wins; the Vite dev server talks to localhost:8014;
   a production build served by the backend itself uses same-origin relative URLs. */
export const API = (import.meta as any).env?.VITE_API
  ?? ((import.meta as any).env?.DEV ? "http://localhost:8014" : "");

async function j(path: string, opts?: RequestInit) {
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
}

export const money = (n: number) =>
  "₹" + new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(n);
export const fmtBig = (n: number) =>
  n >= 1e7 ? "₹" + (n / 1e7).toFixed(2) + " Cr" : n >= 1e5 ? "₹" + (n / 1e5).toFixed(1) + " L" : "₹" + Math.round(n).toLocaleString("en-IN");
export const percent = (n: number) => (n * 100).toFixed(1) + "%";
export const sum = (v: number[]) => v.reduce((a, b) => a + b, 0);

const VMETA: Record<string, { color: string; initials: string }> = {
  ALPHA: { color: "#6e9788", initials: "AP" },
  BOXCO: { color: "#72909d", initials: "BC" },
  PACKRT: { color: "#c5a025", initials: "PR" },
  CORRUG: { color: "#c7806b", initials: "CI" },
  GLOBAL: { color: "#263d4b", initials: "GP" },
};
const FMT: Record<string, string> = { xlsx: "Email + XLSX", pdf: "Email + PDF", docx: "Email + DOCX", jpg: "Email + photo scan", txt: "Plain email + CSV" };

export type Item = { id: string; name: string; category: string; qty: number; unit: string; spec: string };
export type Cell = {
  status: "ready" | "review" | "missing" | "unprocessed";
  raw: number | null; landed: number | null; state?: string;
  flags: string[]; asq: string; source?: { file: string; locator: string; excerpt: string };
  chain: string[]; note?: string | null; question?: string | null; confidence?: number;
};
export type Vendor = {
  vid: string; name: string; short: string; initials: string; color: string;
  format: string; docs: string[]; contact: string; processed: boolean;
  cleared: boolean; leadDays: number | null; quoted: number; held: number;
};
export type Exc = {
  vendor: string; id?: string; type?: string; severity?: string; title?: string;
  detail?: string; options?: string[]; affected_lines?: string[]; annual_impact_inr?: number | null;
  kind?: string; code?: string; question?: string;
};
export type Scenario = { cleared: boolean; maxLeadDays: number };
export type EventData = {
  title: string; buyer: string; basis: string; paymentDays: number; validityMonths: number;
  items: Item[]; vendors: Vendor[]; questions: { key: string; question: string }[];
  answers: Record<string, Record<string, { answer: string | null; evidence?: string | null }>>;
  cells: Record<string, Cell>; open: Exc[]; decisions: Record<string, any>;
  decisionLog: { ts: string; vendor: string; facts: Record<string, any>; note: string }[];
  rules: any[]; policy: any; clearanceRule: string;
};

function normKey(k: any) { return String(k ?? "").split(":")[0].trim(); }

export async function loadEvent(): Promise<EventData> {
  const [rfx, registry, cmp] = await Promise.all([j("/rfx"), j("/vendors"), j("/compare")]);
  const comparison = cmp.comparison ?? {};
  const items: Item[] = rfx.lines.map((l: any) => ({
    id: l.code, name: l.description, category: `${l.ply}-ply`, qty: l.qty_per_month,
    unit: "pc / month", spec: `${l.gsm_combined} gsm · ${l.length_mm}×${l.width_mm}×${l.height_mm} mm`,
  }));
  const answers: EventData["answers"] = {};
  const cells: EventData["cells"] = {};
  const vendors: Vendor[] = Object.entries(registry).map(([vid, v]: [string, any]) => {
    const q = comparison[vid];
    const ext = (v.files[0] || "").split(".").pop();
    let quoted = 0, held = 0;
    answers[vid] = {};
    (q?.questionnaire ?? []).forEach((a: any) => { answers[vid][normKey(a.key)] = { answer: a.answer ?? null, evidence: a.evidence }; });
    (q?.cells ?? []).forEach((c: any) => {
      const status = c.state === "missing" ? "missing" : c.state === "needs_review" ? "review" : "ready";
      if (status !== "missing") quoted++;
      if (status === "review") held++;
      cells[`${vid}:${c.code}`] = {
        status, raw: c.as_quoted?.amount ?? null, landed: c.normalized_inr_per_unit ?? null,
        state: c.state, flags: c.flags ?? [],
        asq: c.as_quoted ? `${c.as_quoted.amount ?? "illegible"} ${c.as_quoted.currency ?? ""} ${c.as_quoted.unit_raw ?? ""}`.trim() : "—",
        source: c.source, chain: (c.transform_chain ?? []).map((t: any) => t.text).filter(Boolean),
        note: c.note, question: c.buyer_question, confidence: c.confidence,
      };
    });
    const lead = parseInt(String(answers[vid]?.lead?.answer ?? ""), 10);
    return {
      vid, name: v.name, short: v.name.split(" ")[0], contact: v.contact ?? "",
      initials: VMETA[vid]?.initials ?? vid.slice(0, 2), color: VMETA[vid]?.color ?? "#666",
      format: FMT[ext] ?? ext?.toUpperCase() ?? "Email", docs: v.files,
      processed: !!q, cleared: !!cmp.qualification?.[vid]?.cleared,
      leadDays: Number.isFinite(lead) ? lead : null, quoted, held,
    };
  });
  return {
    title: rfx.title, buyer: rfx.buyer, basis: rfx.delivery_basis,
    paymentDays: rfx.payment_terms_days, validityMonths: rfx.validity_months,
    items, vendors, questions: rfx.questionnaire.map((q: any) => ({ key: q.key, question: q.question })),
    answers, cells, open: cmp.open_items ?? [], decisions: cmp.decisions ?? {},
    decisionLog: (cmp.decision_log ?? []).slice().reverse(),
    rules: cmp.rules ?? [], policy: cmp.policy ?? {}, clearanceRule: cmp.policy?.clearance_rule ?? "",
  };
}

export function quoteOf(E: EventData, itemId: string, vid: string): Cell {
  const v = E.vendors.find(x => x.vid === vid);
  if (v && !v.processed) return { status: "unprocessed", raw: null, landed: null, flags: [], asq: "—", chain: [] };
  return E.cells[`${vid}:${itemId}`] ?? { status: "missing", raw: null, landed: null, flags: [], asq: "—", chain: [] };
}

export function eligible(v: Vendor, s: Scenario) {
  if (!v.processed) return false;
  if (s.cleared && !v.cleared) return false;
  if (s.maxLeadDays && (v.leadDays == null || v.leadDays > s.maxLeadDays)) return false;
  return true;
}

/* deterministic greedy split — same semantics as the backend's compute_split */
export function calculate(E: EventData, s: Scenario) {
  const allocations: { itemId: string; vid: string; unit: number; total: number }[] = [];
  const suppliers: Record<string, { count: number; total: number }> = {};
  E.vendors.forEach(v => (suppliers[v.vid] = { count: 0, total: 0 }));
  E.items.forEach(item => {
    let best: { vid: string; unit: number } | null = null;
    E.vendors.forEach(v => {
      if (!eligible(v, s)) return;
      const q = quoteOf(E, item.id, v.vid);
      if (q.status === "ready" && q.landed != null && (best == null || q.landed < best.unit))
        best = { vid: v.vid, unit: q.landed };
    });
    if (best) {
      const total = Math.round(best.unit * item.qty * 12 * 100) / 100; // annualised
      allocations.push({ itemId: item.id, vid: best.vid, unit: best.unit, total });
      suppliers[best.vid].count++; suppliers[best.vid].total += total;
    }
  });
  return { allocations, suppliers, total: sum(allocations.map(a => a.total)) };
}

export function readiness(E: EventData) {
  const unproc = E.vendors.filter(v => !v.processed).length;
  const open = E.open.filter(e => ["HIGH", "AWARD_BLOCKING"].includes(e.severity ?? "") && e.type !== "MISSING_LINE");
  const awaiting = E.open.filter(e => (E.decisions[e.vendor ?? ""] ?? {})[(e.type ?? e.id ?? "") + "_status"] === "asked_supplier");
  const atStake = sum(open.map(e => e.annual_impact_inr ?? 0));
  const waived = !!(E.decisions.EVENT ?? {}).award_waiver;
  return { unproc, decisions: open.filter(e => !awaiting.includes(e)), awaiting: awaiting.length, atStake, waived };
}

/* ---- live actions (each hits the real pipeline) ---- */
export const processVendor = (vid: string) => j(`/ingest/${vid}`, { method: "POST" });
export const progressOf = (vid: string): Promise<{ stage?: string; ts?: number; run_ts?: number }> => j(`/progress/${vid}`);
export const decide = (vid: string, facts: Record<string, any>, note: string) =>
  j(`/decide/${vid}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ facts, note, rerun: true }) });
export const recordOnly = (vid: string, facts: Record<string, any>, note: string) =>
  j(`/decide/${vid}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ facts, note, rerun: false }) });
export const askAnalyst = (question: string) =>
  j("/analyst/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
export const draftChat = (message: string) =>
  j("/draft/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
export const createRule = (rtype: string, action: string, label: string, created_from: any) =>
  j("/rules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ op: "create", rtype, action, label, created_from }) });
export const ruleOp = (op: string, rule_id: string) =>
  j("/rules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ op, rule_id }) });
