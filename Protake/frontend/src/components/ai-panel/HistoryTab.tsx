import { useEffect, useMemo, useState } from "react";
import { History, GitCompare, Plus, Minus, ArrowRightLeft, ShieldCheck } from "lucide-react";
import { useApp } from "@/state/AppContext";
import { formatRelativeTime } from "@/lib/time";
import { computeDiff } from "@/lib/diff";
import { BackendApiService, type AuditLogEntry } from "@/api/backendApi";

function formatAuditValue(v: Record<string, unknown> | null): string {
  if (v === null || v === undefined) return "—";
  const keys = Object.keys(v);
  if (keys.length === 0) return "—";
  if (keys.length === 1) return String(v[keys[0]]);
  return JSON.stringify(v);
}

/**
 * Real, persisted, cross-session change history from the backend
 * (app/models/audit_log.py) — every tracked field edit to a wall/room/
 * detection/estimate with real before/after values. Distinct from the
 * local session-only timeline below it, which only covers this browser
 * tab's ADD_HISTORY entries and is lost on refresh.
 */
export function BackendAuditLog() {
  const { state } = useApp();
  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!state.projectId) {
      setEntries(null);
      return;
    }
    let isMounted = true;
    BackendApiService.fetchAuditLog(state.projectId)
      .then((res) => {
        if (isMounted) setEntries(res.items);
      })
      .catch((err) => {
        if (isMounted) {
          setEntries(null);
          setError(err instanceof Error ? err.message : "Failed to load audit log");
        }
      });
    return () => {
      isMounted = false;
    };
  }, [state.projectId]);

  if (!state.projectId) return null;

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 space-y-2">
      <div className="flex items-center gap-1.5 text-[11px] font-medium">
        <ShieldCheck size={13} className="text-[var(--color-primary-hover)]" /> Backend Audit Log
      </div>

      {error && <p className="text-[11px] text-[var(--color-danger)]">{error}</p>}

      {entries === null && !error && (
        <p className="text-[11px] text-[var(--color-text-secondary)]">Loading…</p>
      )}

      {entries !== null && entries.length === 0 && (
        <p className="text-[11px] text-[var(--color-text-secondary)]">No tracked field changes yet.</p>
      )}

      {entries !== null && entries.length > 0 && (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {entries.map((e) => (
            <div key={e.id} className="text-[11px] border-b border-white/5 pb-1.5 last:border-0">
              <div className="flex items-center gap-2 text-[10px] text-[var(--color-text-secondary)]">
                <span>{formatRelativeTime(new Date(e.created_at).getTime())}</span>
                <span>•</span>
                <span className="font-mono">{e.entity_type} #{e.entity_id}</span>
                {e.is_undone && <span className="text-[var(--color-warning)]">(undone)</span>}
              </div>
              <div>
                <span className="font-medium capitalize">{e.action.toLowerCase()}</span>
                {e.field_name && <span className="text-[var(--color-text-secondary)]"> {e.field_name}</span>}
                {(e.previous_value || e.new_value) && (
                  <span className="text-[var(--color-text-secondary)]">
                    {" "}
                    {formatAuditValue(e.previous_value)} → {formatAuditValue(e.new_value)}
                  </span>
                )}
              </div>
              {e.reason && <div className="text-[10px] text-[var(--color-text-secondary)] italic">{e.reason}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DiffSection() {
  const { state } = useApp();
  const stepCount = state.past.length;
  const [stepsBack, setStepsBack] = useState(stepCount);

  const diff = useMemo(() => {
    if (stepCount === 0) return null;
    const clamped = Math.min(Math.max(stepsBack, 1), stepCount);
    const snapshot = state.past[stepCount - clamped];
    return computeDiff(snapshot, { detections: state.detections, measurements: state.measurements });
  }, [state.past, state.detections, state.measurements, stepsBack, stepCount]);

  if (stepCount === 0) {
    return (
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 text-[11px] text-[var(--color-text-secondary)] flex items-center gap-2">
        <GitCompare size={13} /> No tracked revisions yet — approve, reject, or measure something first.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-3 space-y-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-medium">
          <GitCompare size={13} className="text-[var(--color-primary-hover)]" /> Compare Revisions
        </div>
        <select
          value={stepsBack}
          onChange={(e) => setStepsBack(Number(e.target.value))}
          className="bg-[var(--color-panel)] border border-[var(--color-border)] rounded-md px-1.5 py-1 text-[10px] outline-none"
        >
          {Array.from({ length: stepCount }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n === stepCount ? `Since start (${n} actions)` : `${n} action${n === 1 ? "" : "s"} ago`}
            </option>
          ))}
        </select>
      </div>

      {diff && diff.unchanged && <p className="text-[11px] text-[var(--color-text-secondary)]">No changes in this range.</p>}

      {diff && !diff.unchanged && (
        <div className="space-y-1.5">
          {diff.addedDetections.map((d) => (
            <div key={`add-${d.id}`} className="flex items-center gap-1.5 text-[11px]">
              <Plus size={11} className="text-[var(--color-success)] shrink-0" />
              <span className="text-[var(--color-text-secondary)]">Detected</span> <span className="font-medium">{d.name}</span>
            </div>
          ))}
          {diff.removedDetections.map((d) => (
            <div key={`rem-${d.id}`} className="flex items-center gap-1.5 text-[11px]">
              <Minus size={11} className="text-[var(--color-danger)] shrink-0" />
              <span className="text-[var(--color-text-secondary)]">Removed</span> <span className="font-medium">{d.name}</span>
            </div>
          ))}
          {diff.changedDetections.map((c, i) => (
            <div key={`chg-${c.id}-${c.field}-${i}`} className="flex items-center gap-1.5 text-[11px]">
              <ArrowRightLeft size={11} className="text-[var(--color-warning)] shrink-0" />
              <span className="font-medium">{c.name}</span>
              <span className="text-[var(--color-text-secondary)]">
                {c.field}: {c.before} → {c.after}
              </span>
            </div>
          ))}
          {diff.addedMeasurements.map((m) => (
            <div key={`meas-${m.id}`} className="flex items-center gap-1.5 text-[11px]">
              <Plus size={11} className="text-[var(--color-success)] shrink-0" />
              <span className="text-[var(--color-text-secondary)]">Measured</span> <span className="font-medium">{m.label}</span>
              <span className="text-[var(--color-text-secondary)]">({m.valueLabel})</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function HistoryTab() {
  const { state } = useApp();

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-4">
      <DiffSection />
      <BackendAuditLog />

      {state.history.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 text-center px-6 py-8 text-[var(--color-text-secondary)]">
          <History size={22} className="opacity-50" />
          <p className="text-xs">No activity yet.</p>
        </div>
      ) : (
        <div className="relative pl-4 space-y-4">
          <div className="absolute left-[5px] top-1 bottom-1 w-px bg-[var(--color-border)]" />
          {state.history.map((h) => (
            <div key={h.id} className="relative">
              <span className="absolute -left-4 top-1 w-2.5 h-2.5 rounded-full bg-[var(--color-primary)] ring-4 ring-[var(--color-panel)]" />
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[10px] font-mono-num text-[var(--color-primary-hover)]">{h.version}</span>
                <span className="text-[10px] text-[var(--color-text-secondary)]">{formatRelativeTime(h.timestamp)}</span>
              </div>
              <p className="text-xs">
                <span className="font-medium">{h.actor}</span>{" "}
                <span className="text-[var(--color-text-secondary)]">{h.action}</span>
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
