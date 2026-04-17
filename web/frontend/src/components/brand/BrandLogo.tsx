import { cn } from '@/lib/utils'

interface BrandLogoProps {
  className?: string
  /**
   * When true, renders without hover transition (useful for static contexts like cards).
   */
  static?: boolean
}

export function BrandLogo({ className, static: isStatic = false }: BrandLogoProps) {
  return (
    <svg
      className={cn(
        !isStatic && 'transition-transform duration-300 ease-out hover:scale-105',
        className,
      )}
      viewBox="0 0 40 40"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Remnawave Admin"
    >
      <defs>
        <linearGradient id="brandLogoShell" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: 'var(--accent-from)' }} />
          <stop offset="100%" style={{ stopColor: 'var(--accent-to)' }} />
        </linearGradient>
        <linearGradient id="brandLogoShine" x1="50%" y1="0%" x2="50%" y2="100%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.28" />
          <stop offset="70%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
        <radialGradient id="brandLogoGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" style={{ stopColor: 'var(--accent-to-light)' }} stopOpacity="0.55" />
          <stop offset="100%" stopColor="#000000" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Outer soft glow aura */}
      <rect x="0" y="0" width="40" height="40" rx="12" fill="url(#brandLogoGlow)" />

      {/* Squircle shell with gradient */}
      <rect x="3" y="3" width="34" height="34" rx="10" fill="url(#brandLogoShell)" />

      {/* Top highlight shine */}
      <rect x="3" y="3" width="34" height="18" rx="10" fill="url(#brandLogoShine)" />

      {/* Inner hairline */}
      <rect
        x="3.5"
        y="3.5"
        width="33"
        height="33"
        rx="9.5"
        fill="none"
        stroke="#ffffff"
        strokeOpacity="0.22"
        strokeWidth="1"
      />

      {/* Ascending pulse line */}
      <path
        d="M10 25 L15 20 L20 23 L25 15 L30 18"
        fill="none"
        stroke="#ffffff"
        strokeOpacity="0.95"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Node dots — peak emphasised */}
      <circle cx="10" cy="25" r="1.4" fill="#ffffff" fillOpacity="0.7" />
      <circle cx="15" cy="20" r="1.4" fill="#ffffff" fillOpacity="0.85" />
      <circle cx="20" cy="23" r="1.4" fill="#ffffff" fillOpacity="0.85" />
      <circle cx="25" cy="15" r="2" fill="#ffffff" />
      <circle cx="30" cy="18" r="1.4" fill="#ffffff" fillOpacity="0.85" />
    </svg>
  )
}
