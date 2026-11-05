import { useState } from "react";
import { ChevronDown, Search, Settings, Share2, Download, CheckCircle2, ClipboardCheck, PanelBottom, PanelBottomClose, Maximize2 } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";

export default function Toolbar() {
  const { state, dispatch, currentUserName } = useApp();
  const [sheetMenuOpen, setSheetMenuOpen] = useState(false);
  const activeSheet = state.sheets.find((s) => s.id === state.activeSheetId);

  const fileName = state.file?.name || "No file loaded";
  const sheetCode = activeSheet?.code || "Not available from source";
  const sheetName = activeSheet?.name || "Not available from source";

  return (
    <header className="h-12 shrink-0 border-b border-white/10 bg-[#0B0E14] flex items-center justify-between px-4 gap-4 relative z-50 select-none">
      {/* Left: Brand & File */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-blue-500 flex items-center justify-center font-bold text-xs text-white shadow-sm shadow-blue-500/50">
            P
          </div>
          <span className="text-sm font-bold text-white tracking-tight">Protake</span>
        </div>

        <div className="h-4 w-px bg-white/10" />

        <div className="text-xs font-mono text-gray-300 truncate max-w-[160px]">
          {fileName}
        </div>

        {/* Sheet indicator badge */}
        <div className="relative">
          <button
            onClick={() => setSheetMenuOpen((v) => !v)}
            onBlur={() => setTimeout(() => setSheetMenuOpen(false), 150)}
            className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-[#161B26] border border-white/10 text-xs hover:border-white/20 transition-all cursor-pointer"
          >
            <span className="font-semibold text-white">
              {sheetCode} - {sheetName}{" "}
              <span className="text-gray-400 font-normal">
                (Sheet {activeSheet?.pageNumber ?? "Not available from source"})
              </span>
            </span>
            {activeSheet && (
              <span
                className={`px-1.5 py-0.2 rounded text-[10px] font-semibold border flex items-center gap-1 ${activeSheet.isTakeoffEligible !== false
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                    : "bg-gray-500/15 text-gray-400 border-gray-500/30"
                  }`}
                title={activeSheet.isTakeoffEligible === false ? (activeSheet.skipReason ?? undefined) : undefined}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${activeSheet.isTakeoffEligible !== false ? "bg-emerald-400 animate-pulse" : "bg-gray-400"
                    }`}
                />
                {activeSheet.isTakeoffEligible !== false ? "Takeoff Eligible" : "Not Takeoff Eligible"}
              </span>
            )}
            <ChevronDown size={11} className="text-gray-400" />
          </button>

          {sheetMenuOpen && (
            <div className="absolute top-full mt-1 left-0 w-64 rounded-lg border border-white/15 bg-[#111622] shadow-2xl overflow-hidden z-50 animate-in fade-in zoom-in-95 duration-100">
              {state.sheets.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    dispatch({ type: "SET_ACTIVE_SHEET", sheetId: s.id });
                    setSheetMenuOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 text-xs text-left hover:bg-white/5 cursor-pointer transition-colors ${s.id === state.activeSheetId ? "bg-blue-600/15 text-blue-400 font-semibold" : "text-gray-300"
                    }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="font-mono text-cyan-400 font-bold w-10 shrink-0">{s.code}</span>
                    <span className="truncate">{s.name}</span>
                  </div>
                  {s.id === state.activeSheetId && <CheckCircle2 size={13} className="text-blue-400 shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Center: Search */}
      <div className="flex-1 flex justify-center max-w-md">
        <button
          onClick={() => dispatch({ type: "OPEN_COMMAND_PALETTE" })}
          className="flex items-center gap-2 w-full px-3 py-1.5 rounded-lg border border-white/10 bg-[#161B26] text-xs text-gray-400 hover:border-white/20 transition-all cursor-pointer shadow-inner"
        >
          <Search size={13} className="text-gray-400" />
          <span className="flex-1 text-left truncate">Search sheets, rooms, walls...</span>
          <kbd className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-black/40 border border-white/10 text-gray-400">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={() => dispatch({ type: "TOGGLE_FOCUS_MODE" })}
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium text-gray-300 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
          title="Focus Canvas — collapse panels for a maximized blueprint view (Esc to exit)"
        >
          <Maximize2 size={13} />
          <span>Focus Canvas</span>
        </button>

        <button
          onClick={() => dispatch({ type: "TOGGLE_SUMMARY_PANEL" })}
          className={`flex items-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            state.summaryPanelVisible
              ? "text-blue-400 bg-blue-600/10 border border-blue-500/30"
              : "text-gray-300 hover:text-white hover:bg-white/5"
          }`}
          title={state.summaryPanelVisible ? "Hide summary panel" : "Show summary panel"}
        >
          {state.summaryPanelVisible ? <PanelBottomClose size={13} /> : <PanelBottom size={13} />}
          <span>Summary</span>
        </button>

        <button
          onClick={() => dispatch({ type: "OPEN_ELIGIBILITY_DASHBOARD" })}
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium text-gray-300 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
        >
          <ClipboardCheck size={13} />
          <span>Eligibility</span>
        </button>

        <button
          onClick={() => dispatch({ type: "OPEN_SETTINGS" })}
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium text-gray-300 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
        >
          <Settings size={13} />
          <span>Settings</span>
        </button>

        <button
          onClick={() => {
            navigator.clipboard.writeText(window.location.href)
              .then(() => toast.success("Share link copied to clipboard"))
              .catch(() => toast.error("Failed to copy link"));
          }}
          className="flex items-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium text-gray-300 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
        >
          <Share2 size={13} />
          <span>Share</span>
        </button>

        <button
          onClick={() => dispatch({ type: "OPEN_REPORT" })}
          className="flex items-center gap-1.5 py-1.5 px-4 rounded-md text-xs font-semibold bg-blue-600 hover:bg-blue-500 text-white shadow-md shadow-blue-600/30 transition-all cursor-pointer"
        >
          <Download size={13} />
          <span>Export</span>
        </button>

        {/* User Avatar */}
        <div
          className="w-7 h-7 rounded-full bg-gradient-to-tr from-cyan-600 to-emerald-500 flex items-center justify-center text-xs font-bold text-white shadow-sm ring-1 ring-white/20 ml-1 cursor-pointer"
          title={currentUserName ? `Estimator Profile: ${currentUserName}` : "No user session"}
        >
          {currentUserName
            ? currentUserName
              .split(/\s+/)
              .map((part) => part[0])
              .slice(0, 2)
              .join("")
              .toUpperCase()
            : "?"}
        </div>
      </div>
    </header>
  );
}
