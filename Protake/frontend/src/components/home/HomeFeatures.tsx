import {
  ScanLine,
  BarChart3,
  FileCheck2,
  Zap,
  Shield,
  Ruler,
} from "lucide-react";

const FEATURES = [
  {
    icon: ScanLine,
    title: "AI Blueprint Scanning",
    description:
      "Upload any PDF floor plan — raster, vector, or scanned — and our engine extracts walls, rooms, doors, and windows automatically.",
    color: "cyan",
  },
  {
    icon: Ruler,
    title: "Precise Measurements",
    description:
      "Every room's area, perimeter, and wall lengths are measured in real-world units calibrated to the drawing's own scale annotation.",
    color: "blue",
  },
  {
    icon: BarChart3,
    title: "Instant Cost Estimates",
    description:
      "Materials, labor, and waste factors are applied per trade the moment geometry is confirmed — no manual spreadsheet.",
    color: "violet",
  },
  {
    icon: FileCheck2,
    title: "Review & Approve",
    description:
      "Every detection is reviewable. Approve, reject, or edit individual walls, rooms, doors, and windows before finalizing the takeoff.",
    color: "emerald",
  },
  {
    icon: Zap,
    title: "Multi-Sheet Projects",
    description:
      "Manage entire building sets — multiple floors, elevations, and sections — all inside a single project with unified estimates.",
    color: "amber",
  },
  {
    icon: Shield,
    title: "Deterministic Engine",
    description:
      "The geometry engine is purely algorithmic: same input always produces the same output. No black-box AI guessing your dimensions.",
    color: "rose",
  },
];

const COLOR_MAP: Record<string, string> = {
  cyan:    "bg-cyan-500/10 text-cyan-400 ring-1 ring-cyan-500/20",
  blue:    "bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20",
  violet:  "bg-violet-500/10 text-violet-400 ring-1 ring-violet-500/20",
  emerald: "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20",
  amber:   "bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20",
  rose:    "bg-rose-500/10 text-rose-400 ring-1 ring-rose-500/20",
};

export default function HomeFeatures() {
  return (
    <section id="features" className="py-20 px-6 border-t border-[var(--color-border)]">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-bold tracking-tight mb-3">Everything a QTO needs</h2>
          <p className="text-[var(--color-text-secondary)] max-w-xl mx-auto text-sm">
            Built for quantity surveyors, estimators, and project managers who need accurate
            take-offs without hours of manual measurement.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="group relative p-5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] hover:border-[var(--color-primary)]/30 transition-all duration-300 hover:bg-[var(--color-panel-2)]"
              >
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-4 ${COLOR_MAP[f.color]}`}>
                  <Icon size={16} />
                </div>
                <h3 className="font-semibold text-sm mb-2">{f.title}</h3>
                <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{f.description}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
