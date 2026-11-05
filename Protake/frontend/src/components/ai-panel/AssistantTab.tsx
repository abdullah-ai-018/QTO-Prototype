import { useEffect, useRef, useState, useMemo } from "react";
import { 
  Sparkles, 
  Send, 
  Check, 
  X, 
  Layers, 
  FileText, 
  Search, 
  ExternalLink, 
  CheckCircle2, 
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  Building2,
  RefreshCw
} from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import type { AssistantProposedAction, ChatMessage, Detection } from "@/types";
import { answerQuery } from "@/lib/assistantEngine";
import { computeCoverage } from "@/lib/coverage";
import { buildWallInspectionData } from "@/lib/wallInspectorModel";
import { BackendApiService, type WallContextAction } from "@/api/backendApi";

interface ExtendedChatMessage extends ChatMessage {
  wallId?: string;
  actions?: WallContextAction[];
}

const SUGGESTED_WALL_PROMPTS = [
  "Why did you detect this wall?",
  "Show my blueprint evidence",
  "Why is this Interior Partition?",
  "Where did dimensions come from?",
  "Is the assembly verified?",
  "Which sheet/detail supports this?",
  "Do you agree this is a wall?",
  "Why is this QTO eligible?",
];

export default function AssistantTab() {
  const { state, dispatch, costSummary } = useApp();
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Selected detection (Wall / Room / Symbol)
  const selectedDetection = state.detections.find((d) => d.id === state.selectedDetectionId);
  const isWall = selectedDetection?.kind === "wall";

  // Authoritative inspection model for the selected wall
  const wallData = useMemo(() => {
    if (!selectedDetection || !isWall) return null;
    return buildWallInspectionData(selectedDetection, state);
  }, [selectedDetection, isWall, state]);

  // Messages filtered/stored
  const [messages, setMessages] = useState<ExtendedChatMessage[]>([
    {
      id: "seed-1",
      role: "assistant",
      text: "Hi, I'm Caddie — your AI Takeoff Operator. Select any wall on the blueprint, and I'll analyze its geometry, partition schedule, and height provenance directly from the drawing set.",
      timestamp: Date.now() - 60000,
    },
  ]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function handleSend(customText?: string) {
    const text = (customText || input).trim();
    if (!text || sending) return;

    const userMsg: ExtendedChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text,
      wallId: selectedDetection?.id,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!customText) setInput("");
    setSending(true);

    try {
      if (wallData && selectedDetection) {
        // Real Wall-Context AI Investigation API
        const historyTurns = messages.slice(-8).map((m) => ({
          role: m.role,
          content: m.text,
        }));

        const res = await BackendApiService.queryWallContext(
          state.projectId || 1,
          selectedDetection.id,
          text,
          historyTurns,
          wallData,
          typeof state.blueprintId === "number" ? state.blueprintId : undefined
        );

        const aiMsg: ExtendedChatMessage = {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: res.answer,
          wallId: selectedDetection.id,
          actions: res.actions,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, aiMsg]);
      } else {
        // General project query
        const historyTurns = messages.slice(-8).map((m) => ({
          role: m.role,
          content: m.text,
        }));

        const selectedCtx = selectedDetection ? {
          source: (selectedDetection.kind === "wall" ? "wall" : (selectedDetection.kind === "room" ? "room" : "detection")) as "room" | "wall" | "detection" | "archwall",
          backend_id: selectedDetection.id,
          name: selectedDetection.name || `Wall ${selectedDetection.id}`,
          kind: selectedDetection.kind || "wall",
          area_sqft: selectedDetection.grossSf || selectedDetection.areaSqFt || 0,
          perimeter_ft: selectedDetection.perimeterFt || 0,
          confidence: selectedDetection.confidence || 0.95,
          status: selectedDetection.status || "approved",
        } : (state.selectedDetectionId ? {
          source: "wall" as const,
          backend_id: state.selectedDetectionId,
          name: `Wall ${state.selectedDetectionId}`,
          kind: "wall",
          confidence: 0.95,
          status: "approved",
        } : undefined);

        const res = await BackendApiService.queryAssistant(
          state.projectId || 1,
          text,
          historyTurns,
          selectedCtx,
          state.activeTool
        );

        const aiMsg: ExtendedChatMessage = {
          id: `a-${Date.now()}`,
          role: "assistant",
          text: res.reply,
          suggestion: res.suggestions[0] ? { title: res.suggestions[0].title } : undefined,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, aiMsg]);
      }
    } catch (err) {
      // Deterministic client fallback if offline
      if (wallData && selectedDetection) {
        let fallbackAnswer = `### Analysis for ${wallData.displayCode} (${wallData.categoryLabel})\n\n`;
        fallbackAnswer += `• **Geometry Source**: ${wallData.sheetCode ? `Sheet **\`${wallData.sheetCode}\`** (Page ${wallData.pageNumber})` : "Not available from source"}\n`;
        fallbackAnswer += `• **Dimensions**: **${wallData.lengthFt.toFixed(1)} LF × ${wallData.heightFt.toFixed(1)} ft**${wallData.thicknessIn != null ? ` × ${wallData.thicknessIn.toFixed(1)}"` : ""}\n`;
        fallbackAnswer += `• **Height Status**: **${wallData.heightVerificationState}** (${wallData.heightProvenance})\n`;
        fallbackAnswer += `• **Net Hang Area**: **${wallData.netHangAreaSf != null ? `${wallData.netHangAreaSf.toFixed(1)} SF` : "Not available from source"}** (Status: **${wallData.qtoEligible ? "✓ QTO Eligible" : "Excluded"}**)\n`;
        const hasSchedule = !!(wallData.scheduleSheet && wallData.scheduleSheet !== "Not available from source" && wallData.scheduleSheet.trim() !== "");
        fallbackAnswer += hasSchedule
          ? `• **Schedule Link**: Sheet **\`${wallData.scheduleSheet}\`** | Tag: **${wallData.wallTagDisplay}**\n\n`
          : `• **Schedule Link**: Not available on drawing set\n\n`;
        fallbackAnswer += `*Shown from verified drawing geometry — AI analysis ready.*`;

        const fallbackActions: WallContextAction[] = [
          ...(wallData.sheetCode && wallData.sheetCode !== "Not available from source"
            ? [{ type: "FOCUS_SOURCE" as const, sheet_code: wallData.sheetCode, label: `View on ${wallData.sheetCode}` }]
            : []),
          ...(hasSchedule
            ? [{ type: "OPEN_SCHEDULE" as const, sheet_code: wallData.scheduleSheet, label: `Open ${wallData.scheduleSheet} Schedule` }]
            : []),
        ];

        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            text: fallbackAnswer,
            wallId: selectedDetection.id,
            actions: fallbackActions,
            timestamp: Date.now(),
          },
        ]);
      } else {
        const approvedCount = state.detections.filter((d) => d.status === "approved").length;
        const coverage = computeCoverage(state.detections, state.activeSheetId);
        const r = answerQuery(text, {
          detections: state.detections,
          measurements: state.measurements,
          sheets: state.sheets,
          activeSheetId: state.activeSheetId,
          coverage,
          finalBid: costSummary.finalBid,
          approvedCount,
        });
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: "assistant",
            text: r.text,
            suggestion: r.suggestionTitle ? { title: r.suggestionTitle } : undefined,
            timestamp: Date.now(),
          },
        ]);
      }
    } finally {
      setSending(false);
    }
  }

  // Execute two-way action from Assistant to Canvas / Sheet Navigator
  function handleActionClick(action: WallContextAction) {
    if (action.type === "FOCUS_SOURCE" || action.type === "OPEN_SCHEDULE" || action.type === "VIEW_DETAIL") {
      const targetSheetCode = action.sheet_code;
      if (targetSheetCode) {
        const targetSheet = state.sheets.find(
          (s) => s.code.toLowerCase() === targetSheetCode.toLowerCase() || s.name.toLowerCase().includes(targetSheetCode.toLowerCase())
        );

        if (targetSheet) {
          dispatch({ type: "SET_ACTIVE_SHEET", sheetId: targetSheet.id });
          toast.success(`Navigated to Sheet ${targetSheet.code}`, {
            description: targetSheet.name
          });
        } else {
          toast.info(`Sheet ${targetSheetCode} not found in current set`);
        }
      }
    } else if (action.type === "HIGHLIGHT_WALL" && action.detection_id) {
      dispatch({ type: "SELECT_DETECTION", id: action.detection_id });
      toast.success("Wall highlighted on canvas");
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0B0E14] select-none font-sans overflow-hidden">
      {/* 1. STICKY WALL CONTEXT HEADER */}
      {wallData ? (
        <div className="p-3 bg-gradient-to-r from-blue-950/40 via-indigo-950/30 to-[#0B0E14] border-b border-blue-500/20 shrink-0">
          <div className="flex items-center justify-between gap-1 mb-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="w-2 h-2 rounded-full animate-pulse shrink-0" style={{ backgroundColor: wallData.categoryColor }} />
              <span className="text-[9px] font-mono text-blue-400 font-bold uppercase tracking-wider">
                SELECTED WALL CONTEXT
              </span>
            </div>
            <span className="text-[9px] font-mono text-gray-400">
              {wallData.sheetCode} (p.{wallData.pageNumber})
            </span>
          </div>

          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="text-sm font-bold text-white font-mono truncate">
                {wallData.displayCode}
              </div>
              <div className="text-[11px] text-gray-300 flex items-center gap-1.5 flex-wrap">
                <span className="font-semibold" style={{ color: wallData.categoryColor }}>
                  {wallData.categoryLabel}
                </span>
                <span className="text-gray-500">•</span>
                <span className="font-mono text-cyan-400">
                  {wallData.lengthFt.toFixed(1)} LF × {wallData.heightFt.toFixed(1)} ft × {wallData.thicknessIn.toFixed(1)}"
                </span>
              </div>
            </div>

            <div className="text-right shrink-0">
              <span
                className={`px-2 py-0.5 rounded text-[9px] font-bold border inline-block ${
                  wallData.qtoEligible
                    ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                    : "bg-amber-500/20 text-amber-400 border-amber-500/30"
                }`}
              >
                {wallData.qtoEligible ? `✓ ${wallData.netHangAreaSf.toFixed(0)} SF` : "⚠ Excluded"}
              </span>
              <div className="text-[8px] font-mono text-gray-400 mt-0.5">
                Conf: {wallData.confidencePct}%
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-2.5 bg-white/[0.02] border-b border-white/10 text-[10px] text-gray-400 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-1.5">
            <Building2 size={13} className="text-blue-400" />
            <span>Click any wall on canvas to investigate source evidence</span>
          </div>
        </div>
      )}

      {/* 2. CHAT HISTORY & EVIDENCE CHAIN */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-custom">
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[92%] ${m.role === "user" ? "" : "flex gap-2"}`}>
              {m.role === "assistant" && (
                <div className="w-6 h-6 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles size={12} className="text-blue-400" />
                </div>
              )}
              <div className="space-y-1.5">
                <div
                  className={`rounded-xl px-3.5 py-2.5 text-xs leading-relaxed ${
                    m.role === "user"
                      ? "bg-blue-600 text-white font-medium shadow-md"
                      : "bg-[#111622] border border-white/10 text-gray-200 shadow-sm"
                  }`}
                >
                  <div className="prose prose-invert prose-xs max-w-none font-sans whitespace-pre-wrap">
                    {m.text}
                  </div>
                </div>

                {/* Interactive Two-Way Canvas Action Badges */}
                {m.actions && m.actions.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {m.actions.map((act, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleActionClick(act)}
                        className="px-2.5 py-1 rounded-lg bg-blue-600/15 hover:bg-blue-600/25 border border-blue-500/30 text-blue-300 hover:text-white text-[10px] font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-sm"
                        title={act.description || act.label}
                      >
                        <ExternalLink size={11} className="text-blue-400" />
                        <span>{act.label}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex items-center gap-2 text-[11px] text-blue-400 font-mono py-1 px-2">
            <RefreshCw size={12} className="animate-spin" />
            <span>Analyzing blueprint evidence & schedule cross-references…</span>
          </div>
        )}
      </div>

      {/* 3. SUGGESTED PROMPT CHIPS */}
      {wallData && (
        <div className="p-2 border-t border-white/10 bg-[#0E131F]/95">
          <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider px-1 mb-1.5">
            Suggested Investigation Prompts:
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
            {SUGGESTED_WALL_PROMPTS.map((prompt, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(prompt)}
                disabled={sending}
                className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-blue-600/20 border border-white/10 hover:border-blue-500/40 text-gray-300 hover:text-white text-[10px] whitespace-nowrap transition-colors cursor-pointer shrink-0"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 4. INPUT COMPOSER */}
      <div className="p-3 border-t border-white/10 bg-[#111622] flex items-center gap-2 shrink-0">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={wallData ? `Ask about ${wallData.displayCode}…` : "Ask about blueprint takeoff…"}
          disabled={sending}
          className="flex-1 px-3 py-2 rounded-xl bg-black/40 border border-white/10 text-white text-xs placeholder:text-gray-500 focus:outline-none focus:border-blue-500 transition-colors font-sans"
        />
        <button
          onClick={() => handleSend()}
          disabled={!input.trim() || sending}
          className="h-9 w-9 flex items-center justify-center rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white transition-all cursor-pointer shrink-0 shadow-md"
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  );
}
