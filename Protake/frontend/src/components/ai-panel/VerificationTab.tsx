import { useMemo, useState } from "react";
import { ShieldCheck, ShieldAlert, AlertTriangle, Calculator, ChevronDown, Check, Undo2 } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { computeCoverage, computeVarianceFlags } from "@/lib/coverage";
import { RULES, getRule } from "@/lib/ruleEngine";
import { TRADES } from "@/lib/sampleData";
import type { TradeId } from "@/types";

function ReadinessRing({ pct }: { pct: number }) {
  const color = pct >= 90 ? "var(--color-success)" : pct >= 50 ? "var(--color-warning)" : "var(--color-danger)";
  const r = 26;
  const circumference = 2 * Math.PI * r;
  return (
    <div className="relative w-16 h-16 shrink-0">
      <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} fill="none" stroke="#1E293B" strokeWidth="5" />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - pct / 100)}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center text-xs font-mono-num font-semibold" style={{ color }}>
        {pct}%
      </div>
    </div>
  );
}

function CalculatorWidget() {
  const [ruleName, setRuleName] = useState(RULES[0].name);
  const rule = getRule(ruleName)!;
  const [inputs, setInputs] = useState<Record<string, string>>(() =>
    Object.fromEntries(rule.params.map((p) => [p.key, String(p.default ?? "")]))
  );
  const [result, setResult] = useState<{ value: number; error?: string } | null>(null);

  function selectRule(name: string) {
    const next = getRule(name)!;
    setRuleName(name);
    setInputs(Object.fromEntries(next.params.map((p) => [p.key, String(p.default ?? "")])));
    setResult(null);
  }

  function calculate() {
    const numeric = Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, Number(v)]));
    try {
      const value = rule.evaluate(numeric);
      setResult({ value });
    } catch (err) {
      setResult({ value: NaN, error: err instanceof Error ? err.message : "Invalid inputs" });
    }
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 space-y-3">
      <div className="flex items-center gap-2 text-xs font-medium text-[var(--color-text-primary)]">
        <Calculator size={13} className="text-[var(--color-primary-hover)]" />
        Formula Calculator
      </div>
      <p className="text-[10px] text-[var(--color-text-secondary)] -mt-1.5">
        Runs the exact formula this app uses internally — verify any quantity by hand.
      </p>

      <div className="relative">
        <select
          value={ruleName}
          onChange={(e) => selectRule(e.target.value)}
          className="w-full appearance-none bg-[var(--color-panel)] border border-[var(--color-border)] rounded-md px-2.5 py-1.5 pr-7 text-xs outline-none focus:border-[var(--color-primary)]/50"
        >
          {RULES.map((r) => (
            <option key={r.name} value={r.name}>
              {r.label}
            </option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--color-text-secondary)]" />
      </div>
      <p className="text-[10px] text-[var(--color-text-secondary)] font-mono-num">{rule.description}</p>

      <div className="grid grid-cols-2 gap-2">
        {rule.params.map((p) => (
          <label key={p.key} className="text-[10px] text-[var(--color-text-secondary)]">
            {p.label} {p.unit && <span className="opacity-60">({p.unit})</span>}
            <input
              type="number"
              value={inputs[p.key] ?? ""}
              onChange={(e) => setInputs((prev) => ({ ...prev, [p.key]: e.target.value }))}
              className="mt-0.5 w-full bg-[var(--color-panel)] border border-[var(--color-border)] rounded-md px-2 py-1 text-xs font-mono-num outline-none focus:border-[var(--color-primary)]/50"
            />
          </label>
        ))}
      </div>

      <button
        onClick={calculate}
        className="w-full py-1.5 rounded-md text-xs bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] transition-colors"
      >
        Calculate
      </button>

      {result && (
        <div
          className={`rounded-md px-3 py-2 text-xs font-mono-num ${
            result.error ? "bg-[var(--color-danger)]/10 text-[var(--color-danger)]" : "bg-[var(--color-success)]/10 text-[var(--color-success)]"
          }`}
        >
          {result.error ? result.error : `= ${result.value.toLocaleString()} ${rule.unit}`}
        </div>
      )}
    </div>
  );
}

function SignoffRow({ trade, label }: { trade: TradeId; label: string }) {
  const { state, dispatch } = useApp();
  const existing = state.signoffs[trade];
  const [reviewer, setReviewer] = useState("");
  const [notes, setNotes] = useState("");

  if (existing?.signedOff) {
    return (
      <div className="flex items-center justify-between rounded-md border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-success)]">
            <ShieldCheck size={13} /> {label} signed off
          </div>
          <div className="text-[10px] text-[var(--color-text-secondary)] truncate">
            {existing.reviewer || "Reviewer"} · {new Date(existing.timestamp).toLocaleTimeString()}
            {existing.notes ? ` · "${existing.notes}"` : ""}
          </div>
        </div>
        <button
          onClick={() => dispatch({ type: "REVOKE_SIGNOFF", trade })}
          title="Revoke sign-off"
          className="shrink-0 w-6 h-6 flex items-center justify-center rounded-md text-[var(--color-text-secondary)] hover:bg-white/5"
        >
          <Undo2 size={12} />
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-[var(--color-border)] px-3 py-2 space-y-1.5">
      <div className="flex items-center gap-1.5 text-xs font-medium">
        <ShieldAlert size={13} className="text-[var(--color-warning)]" /> {label}
      </div>
      <input
        value={reviewer}
        onChange={(e) => setReviewer(e.target.value)}
        placeholder="Reviewer name"
        className="w-full bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md px-2 py-1 text-[11px] outline-none focus:border-[var(--color-primary)]/50"
      />
      <input
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Notes (optional)"
        className="w-full bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md px-2 py-1 text-[11px] outline-none focus:border-[var(--color-primary)]/50"
      />
      <button
        onClick={() => {
          if (!reviewer.trim()) {
            toast.error("Enter a reviewer name before signing off");
            return;
          }
          dispatch({ type: "SIGNOFF_TRADE", trade, reviewer: reviewer.trim(), notes: notes.trim() });
          toast.success(`${label} signed off`, { description: `by ${reviewer.trim()}` });
        }}
        className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-md text-[11px] bg-[var(--color-primary)]/10 text-[var(--color-primary-hover)] hover:bg-[var(--color-primary)]/20 transition-colors"
      >
        <Check size={12} /> Sign Off {label}
      </button>
    </div>
  );
}

export default function VerificationTab() {
  const { state } = useApp();

  const coverage = useMemo(() => computeCoverage(state.detections, state.activeSheetId), [state.detections, state.activeSheetId]);
  const varianceFlags = useMemo(
    () => computeVarianceFlags(state.detections, state.measurements, state.activeSheetId),
    [state.detections, state.measurements, state.activeSheetId]
  );

  const signedCount = TRADES.filter((t) => state.signoffs[t.id]?.signedOff).length;

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-4">
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 flex items-center gap-3">
        <ReadinessRing pct={coverage.overallReadinessPct} />
        <div className="min-w-0">
          <div className="text-xs font-medium">Sheet Readiness</div>
          <div className="text-[10px] text-[var(--color-text-secondary)]">
            {coverage.gaps.length === 0 ? "Everything on this sheet has been reviewed" : `${coverage.gaps.length} item(s) need attention`}
          </div>
          <div className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">
            QC sign-off: <span className="font-mono-num text-[var(--color-text-primary)]">{signedCount}/{TRADES.length}</span> trades
          </div>
        </div>
      </section>

      {coverage.gaps.length > 0 && (
        <section className="space-y-1.5">
          <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)]">What's Left</div>
          {coverage.gaps.map((gap, i) => (
            <div key={i} className="flex items-start gap-2 text-[11px] text-[var(--color-text-secondary)] rounded-md bg-[var(--color-warning)]/5 border border-[var(--color-warning)]/20 px-2.5 py-1.5">
              <AlertTriangle size={12} className="text-[var(--color-warning)] shrink-0 mt-0.5" />
              {gap}
            </div>
          ))}
        </section>
      )}

      {varianceFlags.length > 0 && (
        <section className="space-y-1.5">
          <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)]">AI vs Manual Variance</div>
          {varianceFlags.map((flag) => (
            <div key={flag.detectionId + flag.manualMeasurementId} className="rounded-md bg-[var(--color-danger)]/5 border border-[var(--color-danger)]/25 px-2.5 py-2 text-[11px]">
              <div className="flex items-center gap-1.5 text-[var(--color-danger)] font-medium mb-1">
                <AlertTriangle size={12} /> {flag.detectionName}: {flag.deviationPct}% deviation
              </div>
              <div className="text-[var(--color-text-secondary)] font-mono-num">
                AI: {flag.aiAreaSqFt.toLocaleString()} sf · Manual: {flag.manualAreaSqFt.toLocaleString()} sf
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="space-y-1.5">
        <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)]">Trade Coverage</div>
        {coverage.perTrade.map((t) => (
          <div key={t.trade} className="text-[11px]">
            <div className="flex items-center justify-between mb-1">
              <span>{t.label}</span>
              <span className="font-mono-num text-[var(--color-text-secondary)]">
                {t.approved}/{t.total} approved
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-white/5 overflow-hidden flex">
              {t.total > 0 && (
                <>
                  <div className="h-full bg-[var(--color-success)]" style={{ width: `${(t.approved / t.total) * 100}%` }} />
                  <div className="h-full bg-[var(--color-warning)]" style={{ width: `${(t.pending / t.total) * 100}%` }} />
                  <div className="h-full bg-[var(--color-danger)]" style={{ width: `${(t.rejected / t.total) * 100}%` }} />
                </>
              )}
            </div>
          </div>
        ))}
      </section>

      <section className="space-y-1.5">
        <div className="text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)]">QC Sign-off</div>
        {TRADES.map((t) => (
          <SignoffRow key={t.id} trade={t.id} label={t.label} />
        ))}
      </section>

      <section>
        <CalculatorWidget />
      </section>
    </div>
  );
}
