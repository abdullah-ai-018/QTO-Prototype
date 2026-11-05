import { CheckCircle2, Building2 } from "lucide-react";

export default function HomeDetectionPreview() {
  return (
    <section className="py-20 px-6 border-t border-[var(--color-border)]">
      <div className="max-w-5xl mx-auto">
        <div className="grid md:grid-cols-2 gap-10 items-center">
          <div>
            <h2 className="text-3xl font-bold tracking-tight mb-4">
              Every element, measured precisely
            </h2>
            <p className="text-[var(--color-text-secondary)] text-sm leading-relaxed mb-6">
              QRO Engine extracts the full geometric model from your plans — not just bounding
              boxes. Each element carries its real-world dimensions, area, and connection to
              adjacent elements.
            </p>
            <ul className="space-y-3">
              {[
                ["Rooms", "Area, perimeter, wall contact ratio, room type"],
                ["Walls", "Length, thickness, structural vs partition"],
                ["Doors", "Grouped by schedule code (D1, D2…), count per type"],
                ["Windows", "Grouped by schedule code (W1, W2…), sill & head heights"],
                ["Exterior areas", "Covered porches, decks, balconies measured separately"],
              ].map(([name, detail]) => (
                <li key={name} className="flex gap-3 text-sm">
                  <CheckCircle2 size={15} className="text-[var(--color-success)] shrink-0 mt-0.5" />
                  <span>
                    <span className="font-medium text-[var(--color-text-primary)]">{name}</span>
                    <span className="text-[var(--color-text-secondary)]"> — {detail}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="relative rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] p-6 overflow-hidden">
            <div className="absolute top-0 right-0 w-40 h-40 bg-[var(--color-primary)]/5 rounded-full blur-2xl" />
            <Building2 size={18} className="text-[var(--color-primary)] mb-4" />
            <div className="space-y-2.5">
              {[
                { label: "Rooms detected", value: "18", color: "bg-blue-500" },
                { label: "Total floor area", value: "2,340 ft²", color: "bg-emerald-500" },
                { label: "Wall segments", value: "143", color: "bg-violet-500" },
                { label: "Door types", value: "D1 × 6, D2 × 4, D3 × 2", color: "bg-cyan-500" },
                { label: "Window types", value: "W1 × 8, W2 × 6", color: "bg-amber-500" },
                { label: "Estimate total", value: "$184,200", color: "bg-rose-500" },
              ].map((row) => (
                <div key={row.label} className="flex items-center justify-between py-2 border-b border-[var(--color-border)] last:border-0 text-sm">
                  <div className="flex items-center gap-2 text-[var(--color-text-secondary)]">
                    <span className={`w-1.5 h-1.5 rounded-full ${row.color}`} />
                    {row.label}
                  </div>
                  <span className="font-mono font-semibold text-[var(--color-text-primary)] text-xs">{row.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
