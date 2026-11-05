import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";

export default function HomeCTA() {
  const navigate = useNavigate();
  return (
    <section className="py-20 px-6 border-t border-[var(--color-border)]">
      <div className="max-w-3xl mx-auto text-center">
        <div className="relative rounded-3xl border border-[var(--color-primary)]/20 bg-gradient-to-br from-[var(--color-panel)] to-[var(--color-panel-2)] p-12 overflow-hidden">
          <div className="absolute inset-0 bg-[var(--color-primary)]/5 rounded-3xl" />
          <div className="relative">
            <h2 className="text-3xl font-bold mb-4">Ready to take off?</h2>
            <p className="text-[var(--color-text-secondary)] text-sm mb-8 max-w-md mx-auto">
              Upload your first floor plan now. No account required, no credit card, no setup.
            </p>
            <button
              onClick={() => navigate("/upload")}
              className="inline-flex items-center justify-center gap-2.5 px-8 py-3.5 rounded-xl bg-white text-black font-semibold transition-all hover:opacity-90 active:scale-95 cursor-pointer shadow-xl shadow-white/10"
            >
              Start Takeoff
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
