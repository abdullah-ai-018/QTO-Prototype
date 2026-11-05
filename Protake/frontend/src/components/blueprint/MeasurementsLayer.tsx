import { Group, Line, Circle, Text, Tag, Label } from "react-konva";
import type { Measurement } from "@/types";
import { toPixelPoints, centroid } from "@/lib/geometry";

const TOOL_COLOR: Record<Measurement["tool"], string> = {
  area: "#2563EB",
  linear: "#22C55E",
  polygon: "#F59E0B",
  count: "#EF4444",
};

export default function MeasurementsLayer({ measurements, stageW, stageH }: { measurements: Measurement[]; stageW: number; stageH: number }) {
  return (
    <Group>
      {measurements.map((m) => {
        const color = TOOL_COLOR[m.tool];
        const pts = toPixelPoints(m.points, stageW, stageH);
        const c = centroid(m.points);

        if (m.tool === "count") {
          const p = m.points[0];
          return (
            <Group key={m.id}>
              <Circle x={p.x * stageW} y={p.y * stageH} radius={10} fill={color} opacity={0.3} stroke={color} strokeWidth={2} />
              <Circle x={p.x * stageW} y={p.y * stageH} radius={3} fill="#FFFFFF" />
              {m.valueLabel && (
                <Label x={p.x * stageW + 12} y={p.y * stageH - 8} listening={false}>
                  <Tag fill="rgba(11,14,20,0.9)" stroke={color} strokeWidth={1} cornerRadius={3} />
                  <Text text={m.valueLabel} fontSize={10} fontFamily="JetBrains Mono" fill={color} padding={3} fontStyle="bold" />
                </Label>
              )}
            </Group>
          );
        }

        const closed = m.tool === "area" || m.tool === "polygon";
        if (pts.length < 4) return null;
        return (
          <Group key={m.id}>
            <Line
              points={pts}
              closed={closed}
              fill={closed ? (m.tool === "polygon" ? "rgba(245,158,11,0.15)" : "rgba(37,99,235,0.15)") : undefined}
              stroke={color}
              strokeWidth={2.5}
              lineCap="round"
              lineJoin="round"
            />
            {m.points.map((p, i) => (
              <Group key={i}>
                <Circle x={p.x * stageW} y={p.y * stageH} radius={4} fill="#FFFFFF" stroke={color} strokeWidth={1.5} />
              </Group>
            ))}
            {m.valueLabel && (
              <Label x={c.x * stageW} y={c.y * stageH - 10} listening={false}>
                <Tag fill="rgba(11,14,20,0.92)" stroke={color} strokeWidth={1} cornerRadius={4} shadowBlur={4} shadowColor="black" shadowOpacity={0.5} />
                <Text text={m.valueLabel} fontSize={10} fontFamily="JetBrains Mono" fill="#FFFFFF" padding={4} fontStyle="bold" />
              </Label>
            )}
          </Group>
        );
      })}
    </Group>
  );
}
