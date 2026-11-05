import { useNavigate } from "react-router-dom";
import { Zap, ArrowRight, ChevronRight } from "lucide-react";

export default function HomeHero() {
  const navigate = useNavigate();
  return (
    <section className="relative pt-24 pb-28 px-6 overflow-hidden">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage: `linear-gradient(var(--color-text-secondary) 1px, transparent 1px),
                            linear-gradient(90deg, var(--color-text-secondary) 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
        }}
      />
      {/* Glow blob */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-[var(--color-primary)]/10 rounded-full blur-3xl pointer-events-none" />

      <div className="relative max-w-4xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[var(--color-primary)]/30 bg-[var(--color-primary)]/5 text-xs text-[var(--color-primary)] font-medium mb-6">
          <Zap size={11} />
          Automated Quantity Take-Off
        </div>

        <h1 className="text-5xl md:text-6xl font-bold tracking-tight leading-tight mb-6">
          From Blueprint to{" "}
          <span className="bg-gradient-to-r from-[var(--color-primary)] to-cyan-400 bg-clip-text text-transparent">
            Bill of Quantities
          </span>
          <br />in Minutes
        </h1>

        <p className="text-lg text-[var(--color-text-secondary)] max-w-2xl mx-auto mb-10 leading-relaxed">
          QRO Engine scans your architectural floor plans with computer vision and AI, extracts
          every room, wall, door, and window, then calculates material quantities and cost
          estimates — automatically.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            onClick={() => navigate("/upload")}
            className="flex items-center justify-center gap-2.5 px-6 py-3 rounded-xl bg-white text-black font-semibold text-sm hover:opacity-90 active:scale-95 transition-all cursor-pointer shadow-lg shadow-white/10"
          >
            Start Your Takeoff
            <ArrowRight size={16} />
          </button>
          <a
            href="#how-it-works"
            className="flex items-center gap-2 px-6 py-3 rounded-xl border border-[var(--color-border)] text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-text-secondary)]/40 transition-colors"
          >
            See how it works
            <ChevronRight size={14} />
          </a>
        </div>
      </div>

      {/* Stat strip */}
      <div className="relative max-w-3xl mx-auto mt-16 grid grid-cols-3 gap-px rounded-2xl overflow-hidden border border-[var(--color-border)] bg-[var(--color-border)]">
        {[
          { value: "95%", label: "Detection Accuracy" },
          { value: "<30s", label: "Per Floor Plan" },
          { value: "100%", label: "Deterministic" },
        ].map((s) => (
          <div key={s.label} className="bg-[var(--color-panel)] px-6 py-5 text-center">
            <div className="text-3xl font-bold text-[var(--color-text-primary)]">{s.value}</div>
            <div className="text-xs text-[var(--color-text-secondary)] mt-1">{s.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
