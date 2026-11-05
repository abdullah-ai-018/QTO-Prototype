import { Line } from "react-konva";

export default function GridLayer({ visible, stageW, stageH }: { visible: boolean; stageW: number; stageH: number }) {
  if (!visible) return null;
  const step = 0.05;
  const lines: React.ReactNode[] = [];
  for (let x = 0; x <= 1; x += step) {
    lines.push(
      <Line key={`v${x}`} points={[x * stageW, 0, x * stageW, stageH]} stroke="#1b2534" strokeWidth={1} listening={false} />
    );
  }
  for (let y = 0; y <= 1; y += step) {
    lines.push(
      <Line key={`h${y}`} points={[0, y * stageH, stageW, y * stageH]} stroke="#1b2534" strokeWidth={1} listening={false} />
    );
  }
  return <>{lines}</>;
}
