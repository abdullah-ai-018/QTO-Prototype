import { useMemo, useState } from "react";
import { ArrowUpDown, Check, X, Download, Search, Pencil } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { formatArea, formatLength } from "@/lib/units";
import type { Detection } from "@/types";

type SortKey = "name" | "kind" | "trade" | "areaSqFt" | "perimeterFt" | "confidence" | "status" | "sheet";
type SortDir = "asc" | "desc";

const STATUS_STYLE: Record<Detection["status"], string> = {
  pending: "text-[var(--color-warning)] bg-[var(--color-warning)]/10",
  approved: "text-[var(--color-success)] bg-[var(--color-success)]/10",
  rejected: "text-[var(--color-danger)] bg-[var(--color-danger)]/10",
};

function EditableName({ detection }: { detection: Detection }) {
  const { dispatch } = useApp();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(detection.name);

  if (editing) {
    return (
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          setEditing(false);
          if (value.trim() && value !== detection.name) {
            dispatch({ type: "RENAME_DETECTION", id: detection.id, name: value.trim() });
            toast.success("Renamed", { description: `${detection.name} → ${value.trim()}` });
          } else {
            setValue(detection.name);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") {
            setValue(detection.name);
            setEditing(false);
          }
        }}
        className="w-full bg-[var(--color-panel)] border border-[var(--color-primary)]/50 rounded px-1.5 py-0.5 text-xs outline-none"
      />
    );
  }

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        setEditing(true);
      }}
      className="group flex items-center gap-1.5 text-left w-full"
    >
      <span>{detection.name}</span>
      <Pencil size={10} className="opacity-0 group-hover:opacity-50 shrink-0" />
    </button>
  );
}

import EstimateWarningBanner from "../common/EstimateWarningBanner";

export default function GridReportView() {
  const { state, dispatch } = useApp();
  const [scope, setScope] = useState<"sheet" | "all">("sheet");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("sheet");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const sheetByI = useMemo(() => Object.fromEntries(state.sheets.map((s) => [s.id, s])), [state.sheets]);

  const rows = useMemo(() => {
    let list = scope === "sheet" ? state.detections.filter((d) => d.sheetId === state.activeSheetId) : state.detections;
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((d) => d.name.toLowerCase().includes(q) || (d.trade ?? "").includes(q) || d.kind.includes(q));
    }
    const sorted = [...list].sort((a, b) => {
      let av: string | number;
      let bv: string | number;
      if (sortKey === "sheet") {
        av = sheetByI[a.sheetId]?.code ?? "";
        bv = sheetByI[b.sheetId]?.code ?? "";
      } else {
        // `trade` is nullable (a room isn't attributable to one trade);
        // sort those together rather than crashing the comparator.
        av = a[sortKey] ?? "";
        bv = b[sortKey] ?? "";
      }
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [state.detections, state.activeSheetId, scope, search, sortKey, sortDir, sheetByI]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function selectRow(d: Detection) {
    if (d.sheetId !== state.activeSheetId) {
      dispatch({ type: "SET_ACTIVE_SHEET", sheetId: d.sheetId });
    }
    dispatch({ type: "SELECT_DETECTION", id: d.id });
  }

  function exportCsv() {
    const header = ["Sheet", "Name", "Kind", "Trade", "Area (sf)", "Perimeter (ft)", "Confidence", "Status"];
    const csvRows = rows.map((d) => [
      sheetByI[d.sheetId]?.code ?? "",
      d.name,
      d.kind,
      d.trade ?? "all trades",
      d.areaSqFt,
      d.perimeterFt,
      `${Math.round(d.confidence * 100)}%`,
      d.status,
    ]);
    const csv = [header, ...csvRows].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "protake-grid.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Grid exported", { description: "protake-grid.csv downloaded" });
  }

  const Th = ({ label, sortKeyName }: { label: string; sortKeyName: SortKey }) => (
    <th
      onClick={() => toggleSort(sortKeyName)}
      className="px-3 py-2 text-left font-medium cursor-pointer select-none hover:text-[var(--color-text-primary)] whitespace-nowrap"
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown size={10} className={sortKey === sortKeyName ? "opacity-100" : "opacity-30"} />
      </span>
    </th>
  );

  return (
    <div className="h-full flex flex-col">
      <EstimateWarningBanner />
      <div className="flex items-center gap-2 mb-3">
        <div className="flex items-center gap-1 rounded-md border border-[var(--color-border)] p-0.5">
          {(["sheet", "all"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`px-2.5 py-1 rounded text-[11px] transition-colors ${
                scope === s ? "bg-[var(--color-primary)] text-white" : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
              }`}
            >
              {s === "sheet" ? "This Sheet" : "All Sheets"}
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by name, trade, kind…"
            className="w-full bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md pl-7 pr-2 py-1.5 text-[11px] outline-none focus:border-[var(--color-primary)]/50"
          />
        </div>
        <span className="text-[11px] text-[var(--color-text-secondary)] font-mono-num">{rows.length} rows</span>
        <button
          onClick={exportCsv}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[11px] border border-[var(--color-border)] hover:bg-white/5 transition-colors ml-auto"
        >
          <Download size={12} /> Export CSV
        </button>
      </div>

      <div className="flex-1 overflow-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[var(--color-panel-2)] text-[var(--color-text-secondary)] border-b border-[var(--color-border)]">
            <tr>
              <Th label="Sheet" sortKeyName="sheet" />
              <Th label="Name" sortKeyName="name" />
              <Th label="Kind" sortKeyName="kind" />
              <Th label="Trade" sortKeyName="trade" />
              <Th label="Area" sortKeyName="areaSqFt" />
              <Th label="Perim" sortKeyName="perimeterFt" />
              <Th label="Conf." sortKeyName="confidence" />
              <Th label="Status" sortKeyName="status" />
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr
                key={d.id}
                onClick={() => selectRow(d)}
                className={`border-b border-[var(--color-border)] last:border-0 cursor-pointer transition-colors ${
                  d.id === state.selectedDetectionId ? "bg-[var(--color-primary)]/10" : "hover:bg-white/[0.03]"
                }`}
              >
                <td className="px-3 py-2 font-mono-num text-[var(--color-primary-hover)]">{sheetByI[d.sheetId]?.code}</td>
                <td className="px-3 py-2 max-w-[160px]" onClick={(e) => e.stopPropagation()}>
                  <EditableName detection={d} />
                </td>
                <td className="px-3 py-2 capitalize text-[var(--color-text-secondary)]">{d.kind}</td>
                <td className="px-3 py-2 capitalize text-[var(--color-text-secondary)]">{d.trade ?? "all trades"}</td>
                <td className="px-3 py-2 font-mono-num text-right">{formatArea(d.areaSqFt, state.unitSystem)}</td>
                <td className="px-3 py-2 font-mono-num text-right">{formatLength(d.perimeterFt, state.unitSystem)}</td>
                <td className="px-3 py-2 font-mono-num text-right">{Math.round(d.confidence * 100)}%</td>
                <td className="px-3 py-2">
                  <span className={`inline-block px-1.5 py-0.5 rounded-full text-[10px] capitalize ${STATUS_STYLE[d.status]}`}>{d.status}</span>
                </td>
                <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                  {d.status === "pending" && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => dispatch({ type: "APPROVE_DETECTION", id: d.id })}
                        className="w-6 h-6 flex items-center justify-center rounded bg-[var(--color-success)]/10 text-[var(--color-success)] hover:bg-[var(--color-success)]/20"
                      >
                        <Check size={11} />
                      </button>
                      <button
                        onClick={() => dispatch({ type: "REJECT_DETECTION", id: d.id })}
                        className="w-6 h-6 flex items-center justify-center rounded bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20"
                      >
                        <X size={11} />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-[var(--color-text-secondary)]">
                  No detections match this view yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
