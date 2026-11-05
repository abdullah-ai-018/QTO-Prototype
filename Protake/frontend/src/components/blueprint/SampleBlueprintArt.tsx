import { Group, Line, Rect, Text, Circle, Arc } from "react-konva";
import { BASE_W, BASE_H } from "@/lib/geometry";

const STROKE = "#2c3b52";
const STROKE_STRONG = "#3a4d6b";

function W(nx: number) {
  return nx * BASE_W;
}
function H(ny: number) {
  return ny * BASE_H;
}

// A stylized commercial office floor plan drawn procedurally to align
// roughly with the sample AI detections.
export default function SampleBlueprintArt() {
  return (
    <Group listening={false}>
      {/* outer shell */}
      <Rect x={W(0.04)} y={H(0.05)} width={W(0.92)} height={H(0.9)} stroke={STROKE_STRONG} strokeWidth={3} cornerRadius={2} />

      {/* corridor spine */}
      <Line points={[W(0.06), H(0.5), W(0.94), H(0.5)]} stroke={STROKE} strokeWidth={1.5} dash={[6, 4]} />

      {/* lobby (0.22,0.28,0.28,0.32) */}
      <Rect x={W(0.08)} y={H(0.12)} width={W(0.28)} height={H(0.32)} stroke={STROKE} strokeWidth={2} />
      <Text x={W(0.1)} y={H(0.14)} text="LOBBY" fontSize={13} fill="#3d4f6b" fontFamily="JetBrains Mono" />
      <Arc x={W(0.08)} y={H(0.44)} innerRadius={0} outerRadius={26} angle={90} rotation={0} stroke={STROKE} strokeWidth={1} />

      {/* conference room (0.62,0.24,0.24,0.22) */}
      <Rect x={W(0.5)} y={H(0.13)} width={W(0.24)} height={H(0.22)} stroke={STROKE} strokeWidth={2} />
      <Text x={W(0.52)} y={H(0.15)} text="CONFERENCE" fontSize={12} fill="#3d4f6b" fontFamily="JetBrains Mono" />

      {/* office 104 (0.78,0.58,0.18,0.24) */}
      <Rect x={W(0.69)} y={H(0.46)} width={W(0.18)} height={H(0.24)} stroke={STROKE} strokeWidth={2} />
      <Text x={W(0.71)} y={H(0.48)} text="OFFICE 104" fontSize={11} fill="#3d4f6b" fontFamily="JetBrains Mono" />

      {/* restroom (0.34,0.72,0.14,0.16) */}
      <Rect x={W(0.27)} y={H(0.64)} width={W(0.14)} height={H(0.16)} stroke={STROKE} strokeWidth={2} />
      <Text x={W(0.285)} y={H(0.665)} text="RR" fontSize={11} fill="#3d4f6b" fontFamily="JetBrains Mono" />
      <Circle x={W(0.3)} y={H(0.68)} radius={2.5} stroke={STROKE} strokeWidth={1} />
      <Circle x={W(0.33)} y={H(0.68)} radius={2.5} stroke={STROKE} strokeWidth={1} />

      {/* misc partitions */}
      <Line points={[W(0.4), H(0.05), W(0.4), H(0.46)]} stroke={STROKE} strokeWidth={1.5} />
      <Line points={[W(0.6), H(0.54), W(0.6), H(0.95)]} stroke={STROKE} strokeWidth={1.5} />
      <Line points={[W(0.08), H(0.58), W(0.5), H(0.58)]} stroke={STROKE} strokeWidth={1.5} />

      {/* grid of columns */}
      {[0.1, 0.3, 0.5, 0.7, 0.9].map((cx) =>
        [0.1, 0.5, 0.9].map((cy) => (
          <Rect key={`${cx}-${cy}`} x={W(cx) - 4} y={H(cy) - 4} width={8} height={8} fill="#1a2432" stroke={STROKE} strokeWidth={1} />
        ))
      )}

      {/* title block */}
      <Rect x={W(0.78)} y={H(0.86)} width={W(0.18)} height={H(0.09)} stroke={STROKE_STRONG} strokeWidth={1.5} />
      <Text x={W(0.795)} y={H(0.875)} text="A101 — LEVEL 01" fontSize={11} fill="#4a5f80" fontFamily="JetBrains Mono" />
      <Text x={W(0.795)} y={H(0.895)} text="SCALE 1/8&quot; = 1'-0&quot;" fontSize={9} fill="#3d4f6b" fontFamily="JetBrains Mono" />
      <Text x={W(0.795)} y={H(0.91)} text="PROTAKE DEMO SET" fontSize={9} fill="#3d4f6b" fontFamily="JetBrains Mono" />

      {/* north arrow */}
      <Group x={W(0.9)} y={H(0.1)}>
        <Circle radius={16} stroke={STROKE_STRONG} strokeWidth={1.5} />
        <Line points={[0, 10, 0, -10]} stroke={STROKE_STRONG} strokeWidth={1.5} />
        <Line points={[0, -10, -5, -2]} stroke={STROKE_STRONG} strokeWidth={1.5} />
        <Line points={[0, -10, 5, -2]} stroke={STROKE_STRONG} strokeWidth={1.5} />
        <Text x={-4} y={16} text="N" fontSize={11} fill="#4a5f80" fontFamily="JetBrains Mono" />
      </Group>
    </Group>
  );
}
