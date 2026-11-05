import Logo from "@/components/common/Logo";

export default function HomeFooter() {
  return (
    <footer className="border-t border-[var(--color-border)] px-6 py-6">
      <div className="max-w-6xl mx-auto flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 relative">
            <Logo />
          </div>
          <span className="font-medium text-[var(--color-text-primary)]">Protake</span>
          <span className="opacity-50">·</span>
          <span>A project by Contractorslist</span>
        </div>
        <span>Quantity Take-Off, Automated.</span>
      </div>
    </footer>
  );
}
