import { useState } from "react";
import { Group, Line, Text, Tag, Label, Rect } from "react-konva";
import type { CalloutAnnotation, StickyNoteAnnotation } from "@/types";

interface CalloutLayerProps {
  callouts: CalloutAnnotation[];
  stickyNotes: StickyNoteAnnotation[];
  activeSheetId: string | null;
}

export default function CalloutLayer({ callouts, stickyNotes, activeSheetId, stageW, stageH }: CalloutLayerProps & { stageW: number; stageH: number }) {
  const currentCallouts = callouts.filter((c) => c.sheetId === activeSheetId);
  const currentNotes = stickyNotes.filter((n) => n.sheetId === activeSheetId);

  return (
    <Group>
      {/* Kreo-style Leader Line Callouts */}
      {currentCallouts.map((c) => {
        const sx = c.startX * stageW;
        const sy = c.startY * stageH;
        const ex = c.endX * stageW;
        const ey = c.endY * stageH;

        return (
          <Group key={c.id}>
            {/* Pointer arrow line */}
            <Line
              points={[sx, sy, ex, ey]}
              stroke="#F59E0B"
              strokeWidth={2}
              dash={[4, 2]}
            />
            {/* Target point dot */}
            <Line
              points={[sx - 3, sy, sx + 3, sy]}
              stroke="#F59E0B"
              strokeWidth={4}
            />

            {/* Callout box */}
            <Label x={ex} y={ey - 14} listening={false}>
              <Tag fill="#1E293B" stroke="#F59E0B" strokeWidth={1.5} cornerRadius={6} shadowBlur={8} shadowColor="black" shadowOpacity={0.4} />
              <Text
                text={c.text}
                fontSize={12}
                fontFamily="Inter, sans-serif"
                fill="#F8FAFC"
                padding={8}
              />
            </Label>
          </Group>
        );
      })}

      {/* Kreo-style Sticky Notes */}
      {currentNotes.map((n) => {
        const nx = n.x * stageW;
        const ny = n.y * stageH;

        return (
          <Group key={n.id} x={nx} y={ny}>
            <Rect
              width={140}
              height={80}
              fill={n.color || "#FEF08A"}
              cornerRadius={4}
              shadowBlur={10}
              shadowColor="black"
              shadowOpacity={0.25}
            />
            <Text
              text={n.text}
              fontSize={11}
              fontFamily="Inter, sans-serif"
              fill="#1E293B"
              padding={10}
              width={140}
            />
          </Group>
        );
      })}
    </Group>
  );
}
