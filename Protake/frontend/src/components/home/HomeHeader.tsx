import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import Logo from "@/components/common/Logo";

export default function HomeHeader() {
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)]/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate("/")}>
          <div className="w-7 h-7 relative">
            <Logo />
          </div>
          <span className="font-semibold tracking-tight text-sm text-white">Protake</span>
        </div>

        <nav className="hidden md:flex items-center gap-6 text-sm text-[var(--color-text-secondary)]">
          <a href="#features" className="hover:text-[var(--color-text-primary)] transition-colors">Features</a>
          <a href="#how-it-works" className="hover:text-[var(--color-text-primary)] transition-colors">How it works</a>
        </nav>

        <button
          onClick={() => navigate("/upload")}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white text-black text-xs font-semibold hover:opacity-90 active:scale-95 transition-all cursor-pointer"
        >
          Start Takeoff
          <ArrowRight size={14} />
        </button>
      </div>
    </header>
  );
}
