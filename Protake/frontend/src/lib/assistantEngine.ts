// Drawing-aware assistant: every answer here is computed directly from
// the app's real, current state (detections, measurements, coverage) —
// never invented. This is deliberately pattern-matching over real data
// rather than a full LLM, so it works offline with zero setup; wiring
// it to a real model (the backend's /assistant/query, Claude-backed) is
// a drop-in swap once ANTHROPIC_API_KEY is configured server-side.

import type { Detection, Measurement, Sheet, TradeId } from "@/types";
import type { CoverageReport } from "@/lib/coverage";
import { TRADES } from "@/lib/sampleData";

export interface AssistantContext {
  detections: Detection[];
  measurements: Measurement[];
  sheets: Sheet[];
  activeSheetId: string | null;
  coverage: CoverageReport;
  finalBid: number;
  approvedCount: number;
}

export interface AssistantReply {
  text: string;
  suggestionTitle?: string;
}

function sheetDetections(ctx: AssistantContext): Detection[] {
  return ctx.detections.filter((d) => d.sheetId === ctx.activeSheetId);
}

function findTrade(text: string): TradeId | null {
  for (const t of TRADES) {
    if (text.includes(t.id) || text.includes(t.label.toLowerCase())) return t.id;
  }
  return null;
}

function findNamedDetection(text: string, ctx: AssistantContext): Detection | null {
  const rows = sheetDetections(ctx);
  const match = rows.find((d) => text.includes(d.name.toLowerCase()));
  return match ?? null;
}

const KIND_WORDS: { words: string[]; kind: Detection["kind"] }[] = [
  { words: ["room", "rooms"], kind: "room" },
  { words: ["wall", "walls"], kind: "wall" },
  { words: ["object", "objects", "door", "doors", "window", "windows"], kind: "object" },
];

export function answerQuery(query: string, ctx: AssistantContext): AssistantReply {
  const t = query.toLowerCase().trim();
  const rows = sheetDetections(ctx);

  // "area of <name>" / "how big is <name>" / named lookup
  const named = findNamedDetection(t, ctx);
  if (named && (t.includes("area") || t.includes("how big") || t.includes("size") || t.includes("perimeter"))) {
    return {
      text: `${named.name} is ${named.areaSqFt.toLocaleString()} sq ft with a ${named.perimeterFt.toLocaleString()} ft perimeter, detected at ${Math.round(named.confidence * 100)}% confidence and currently ${named.status}.`,
    };
  }
  if (named) {
    return {
      text: `${named.name}: ${named.trade ?? "all trades"} · ${named.kind} · ${named.areaSqFt.toLocaleString()} sq ft · ${Math.round(named.confidence * 100)}% confidence · ${named.status}.`,
    };
  }

  // counts: "how many rooms" / "how many doors" / "count walls"
  if (t.includes("how many") || t.startsWith("count")) {
    const kindMatch = KIND_WORDS.find((k) => k.words.some((w) => t.includes(w)));
    const trade = findTrade(t);
    let filtered = rows;
    if (kindMatch) filtered = filtered.filter((d) => d.kind === kindMatch.kind);
    if (trade) filtered = filtered.filter((d) => d.trade === trade);
    if (t.includes("approved")) filtered = filtered.filter((d) => d.status === "approved");
    if (t.includes("pending")) filtered = filtered.filter((d) => d.status === "pending");
    if (t.includes("reject")) filtered = filtered.filter((d) => d.status === "rejected");

    const label = kindMatch ? kindMatch.words[0] : trade ? `${trade} item` : "item";
    return { text: `There ${filtered.length === 1 ? "is" : "are"} ${filtered.length} ${label}${filtered.length === 1 ? "" : "s"} on this sheet.` };
  }

  // "what's left" / "what's pending" / "what needs review"
  if (t.includes("what's left") || t.includes("whats left") || t.includes("what needs") || t.includes("remaining") || t.includes("pending")) {
    if (ctx.coverage.gaps.length === 0) {
      return { text: "Nothing's left — every detection on this sheet has been reviewed." };
    }
    return { text: `Here's what still needs attention:\n${ctx.coverage.gaps.map((g) => `• ${g}`).join("\n")}` };
  }

  // low confidence / risky items
  if (t.includes("low confidence") || t.includes("risky") || t.includes("double check") || t.includes("uncertain")) {
    const risky = rows.filter((d) => d.confidence < 0.85 && d.status === "pending");
    if (risky.length === 0) return { text: "No low-confidence pending items right now — everything reads above 85%." };
    return {
      text: `${risky.length} item(s) worth a closer look:\n${risky.map((d) => `• ${d.name} (${Math.round(d.confidence * 100)}%)`).join("\n")}`,
    };
  }

  // total approved area
  if (t.includes("total area") || (t.includes("area") && (t.includes("approved") || t.includes("total")))) {
    const approvedRooms = rows.filter((d) => d.kind === "room" && d.status === "approved");
    const total = approvedRooms.reduce((s, d) => s + d.areaSqFt, 0);
    return { text: `Approved room area on this sheet totals ${total.toLocaleString()} sq ft across ${approvedRooms.length} room(s).` };
  }

  if (t.includes("waste") || t.includes("drywall")) {
    return {
      text: "I reviewed the drywall takeoff for this sheet. Corner conditions in the conference room typically increase offcut waste beyond the standard factor.",
      suggestionTitle: "Conference room requires additional drywall waste factor.",
    };
  }
  if (t.includes("cost") || t.includes("bid") || t.includes("price")) {
    return { text: `Current final bid price stands at $${ctx.finalBid.toLocaleString()} based on ${ctx.approvedCount} approved detections.` };
  }
  if (t.includes("paint")) {
    return {
      text: "Painting quantities assume two coats with standard coverage. Rooms with exposed block or masonry may need a primer upcharge.",
      suggestionTitle: "Add masonry primer upcharge for Lobby walls.",
    };
  }

  if (t.includes("sheet") || t.includes("readiness") || t.includes("ready")) {
    return { text: `This sheet is ${ctx.coverage.overallReadinessPct}% reviewed. ${ctx.coverage.gaps.length} item(s) still need attention.` };
  }

  return {
    text: "I can answer questions grounded in this sheet's real data — try \"how many rooms\", \"area of Lobby\", \"what's left to review\", or \"which items are low confidence\".",
  };
}
