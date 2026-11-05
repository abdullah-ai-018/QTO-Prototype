export default function Logo({ className = "w-full h-full" }: { className?: string }) {
  return (
    <svg viewBox="0 0 512 512" fill="none" className={className}>
      <defs>
        <linearGradient id="pGradLogo" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#3B82F6" />
          <stop offset="50%" stopColor="#8B5CF6" />
          <stop offset="100%" stopColor="#EC4899" />
        </linearGradient>
      </defs>
      <rect x="110" y="70" width="60" height="372" rx="30" fill="url(#pGradLogo)" />
      <path d="M140 70 C280 70, 390 130, 390 230 C390 330, 280 390, 140 390" stroke="url(#pGradLogo)" strokeWidth="60" strokeLinecap="round" fill="none" />
      <circle cx="390" cy="230" r="28" fill="#ffffff" stroke="#8B5CF6" strokeWidth="8" />
    </svg>
  );
}

