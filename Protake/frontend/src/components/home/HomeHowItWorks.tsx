const STEPS = [
  { n: "01", title: "Upload Plans", body: "Drop a PDF or image. We support multi-page sets and both raster and CAD exports." },
  { n: "02", title: "AI Detects Geometry", body: "Walls, rooms, doors, and windows are located and measured in seconds." },
  { n: "03", title: "Review Detections", body: "Step through each detection, approve what's right, edit or reject what isn't." },
  { n: "04", title: "Export Estimate", body: "Download a detailed QTO report with quantities, rates, and totals by trade." },
];

export default function HomeHowItWorks() {
  return (
    <section id="how-it-works" className="py-20 px-6 border-t border-[var(--color-border)]">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-bold tracking-tight mb-3">From upload to estimate in 4 steps</h2>
          <p className="text-[var(--color-text-secondary)] text-sm max-w-xl mx-auto">
            No configuration. No training. Just drop your plans and the engine handles the rest.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {STEPS.map((step, i) => (
            <div key={step.n} className="relative">
              {i < STEPS.length - 1 && (
                <div className="hidden lg:block absolute top-6 left-[calc(100%+12px)] w-6 h-px bg-gradient-to-r from-[var(--color-border)] to-transparent" />
              )}
              <div className="p-5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-panel)] h-full">
                <div className="text-3xl font-black text-[var(--color-primary)]/20 mb-3 font-mono">{step.n}</div>
                <h3 className="font-semibold text-sm mb-2">{step.title}</h3>
                <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{step.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
