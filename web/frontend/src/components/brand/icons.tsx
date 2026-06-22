/**
 * Halo Icon Set — the custom brand icon family for remnawave-admin.
 *
 * Drop-in replacement for `lucide-react`: every icon is exported under the
 * same name lucide uses, so call sites only swap the import path. Icons are
 * duotone (a translucent currentColor fill under a crisp currentColor stroke)
 * so they inherit the active theme accent — cyan under Halo, pink under
 * sakura, etc. — and the sidebar active-state highlight keeps working.
 *
 * Every icon is built by `createIcon` and normalised to the same `LucideIcon`
 * type, so mixed icon arrays across the app stay homogeneous. This is a full
 * custom replacement — lucide-react is no longer a runtime dependency.
 */
import { forwardRef } from 'react'
import type { SVGProps, ReactNode, ComponentType } from 'react'
import { cn } from '@/lib/utils'

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'ref'> {
  size?: number | string
}

/**
 * Icon component type kept under the name call sites imported before the
 * migration. `ComponentType` keeps icon props loosely typed across the app.
 */
export type LucideIcon = ComponentType<IconProps>

const S = 1.7 // base stroke width

/**
 * Shared SVG shell. Mirrors lucide's contract: 24x24 viewBox, currentColor,
 * default 24px sizing that any w/h utility class overrides, plus size/color
 * props and a forwardable ref.
 */
function createIcon(name: string, paths: ReactNode): LucideIcon {
  const C = forwardRef<SVGSVGElement, IconProps>(({ size = 24, className, color, style, ...props }, ref) => (
    <svg
      ref={ref}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      aria-hidden="true"
      className={cn(className)}
      style={color ? { color, ...style } : style}
      {...props}
    >
      {paths}
    </svg>
  ))
  C.displayName = name
  return C
}

// ─────────────────────────────────────────────────────────────────────────
// Custom Halo icons
// ─────────────────────────────────────────────────────────────────────────

export const LayoutDashboard = createIcon('LayoutDashboard', (
  <>
    <rect x="3.4" y="3.4" width="7" height="8.4" rx="1.7" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} />
    <rect x="13.6" y="3.4" width="7" height="5" rx="1.7" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} />
    <rect x="13.6" y="11.4" width="7" height="9.2" rx="1.7" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} />
    <rect x="3.4" y="14.6" width="7" height="6" rx="1.7" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} />
  </>
))

export const Users = createIcon('Users', (
  <>
    <circle cx="9.3" cy="8.1" r="3.3" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} />
    <path d="M3.6 19.4a5.7 5.7 0 0 1 11.4 0" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
    <path d="M16.2 5.1a3.3 3.3 0 0 1 0 6.1" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
    <path d="M17.4 14.2a5.7 5.7 0 0 1 3 5.2" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
  </>
))

export const Server = createIcon('Server', (
  <>
    <rect x="3.3" y="3.8" width="17.4" height="7" rx="2.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} />
    <rect x="3.3" y="13.2" width="17.4" height="7" rx="2.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth={S} />
    <circle cx="7.2" cy="7.3" r="1.05" fill="currentColor" />
    <circle cx="7.2" cy="16.7" r="1.05" fill="currentColor" />
    <path d="M11.4 7.3h5.6M11.4 16.7h5.6" stroke="currentColor" strokeWidth={S} strokeLinecap="round" opacity="0.55" />
  </>
))

export const Activity = createIcon('Activity', (
  <>
    <path d="M2.8 12.2h3.4l2.3-6.4 4 12.2 2.3-5.8h2" stroke="currentColor" strokeWidth={S} strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="19.6" cy="12.2" r="3.4" fill="currentColor" fillOpacity="0.18" />
    <circle cx="19.6" cy="12.2" r="1.7" fill="currentColor" />
  </>
))

export const Globe = createIcon('Globe', (
  <>
    <circle cx="12" cy="12" r="8.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth={S} />
    <path d="M3.4 12h17.2" stroke="currentColor" strokeWidth={S} />
    <ellipse cx="12" cy="12" rx="3.7" ry="8.6" stroke="currentColor" strokeWidth={S} />
  </>
))

export const Wallet = createIcon('Wallet', (
  <>
    <rect x="3.2" y="5.8" width="17.6" height="13" rx="3.2" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth={S} />
    <path d="M3.6 9.2h11.2a2 2 0 0 1 2 2v1.4" stroke="currentColor" strokeWidth={S} strokeLinecap="round" opacity="0.55" />
    <path d="M15.4 11.6h5.6v4.2h-5.6a2.1 2.1 0 0 1 0-4.2Z" fill="currentColor" fillOpacity="0.22" stroke="currentColor" strokeWidth={S} />
    <circle cx="17.4" cy="13.7" r="1.05" fill="currentColor" />
  </>
))

export const ShieldAlert = createIcon('ShieldAlert', (
  <>
    <path d="M12 2.8 19 5.3v5.7c0 4.6-3 7.4-7 9.2-4-1.8-7-4.6-7-9.2V5.3z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth={S} strokeLinejoin="round" />
    <path d="M12 8.2v4.1" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    <circle cx="12" cy="15.6" r="1.05" fill="currentColor" />
  </>
))

export const Bot = createIcon('Bot', (
  <>
    <rect x="4.4" y="8" width="15.2" height="11.4" rx="3.6" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth={S} />
    <path d="M12 8V4.4" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
    <circle cx="12" cy="3.5" r="1.5" fill="currentColor" />
    <circle cx="9.2" cy="13.5" r="1.25" fill="currentColor" />
    <circle cx="14.8" cy="13.5" r="1.25" fill="currentColor" />
    <path d="M2.8 12.4v3M21.2 12.4v3" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
  </>
))

export const Bell = createIcon('Bell', (
  <>
    <path d="M6 17.2c1.4-1.4 1.7-3 1.7-5.8a4.3 4.3 0 0 1 8.6 0c0 2.8.3 4.4 1.7 5.8z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth={S} strokeLinejoin="round" />
    <path d="M10 20.2a2.2 2.2 0 0 0 4 0" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
    <path d="M12 4.3V2.8" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
  </>
))

export const Settings = createIcon('Settings', (
  <path
    fillRule="evenodd"
    fill="currentColor"
    fillOpacity="0.15"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinejoin="round"
    d="M 18.51 10.44 L 21.24 10.91 L 21.24 13.09 L 18.51 13.56 L 17.71 15.50 L 19.30 17.76 L 17.76 19.30 L 15.50 17.71 L 13.56 18.51 L 13.09 21.24 L 10.91 21.24 L 10.44 18.51 L 8.50 17.71 L 6.24 19.30 L 4.70 17.76 L 6.29 15.50 L 5.49 13.56 L 2.76 13.09 L 2.76 10.91 L 5.49 10.44 L 6.29 8.50 L 4.70 6.24 L 6.24 4.70 L 8.50 6.29 L 10.44 5.49 L 10.91 2.76 L 13.09 2.76 L 13.56 5.49 L 15.50 6.29 L 17.76 4.70 L 19.30 6.24 L 17.71 8.50 Z M 14.70 12 a 2.7 2.7 0 1 0 -5.40 0 a 2.7 2.7 0 1 0 5.40 0 Z"
  />
))

export const Search = createIcon('Search', (
  <>
    <circle cx="10.5" cy="10.5" r="6.7" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth={S} />
    <path d="m15.6 15.6 4.6 4.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
  </>
))

export const Trash2 = createIcon('Trash2', (
  <>
    <path d="M6 7.5 7 19a2 2 0 0 0 2 1.9h6a2 2 0 0 0 2-1.9l1-11.5z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth={S} strokeLinejoin="round" />
    <path d="M3.8 7.5h16.4" stroke="currentColor" strokeWidth={S} strokeLinecap="round" />
    <path d="M9.4 7.5V6a1.8 1.8 0 0 1 1.8-1.8h1.6A1.8 1.8 0 0 1 14.6 6v1.5" stroke="currentColor" strokeWidth={S} strokeLinejoin="round" />
    <path d="M10.2 11v5.4M13.8 11v5.4" stroke="currentColor" strokeWidth={S} strokeLinecap="round" opacity="0.6" />
  </>
))

export const Plus = createIcon('Plus', (
  <>
    <circle cx="12" cy="12" r="9" fill="currentColor" fillOpacity="0.12" />
    <path d="M12 6.4v11.2M6.4 12h11.2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </>
))

export const RefreshCw = createIcon('RefreshCw', (
  <>
    <path d="M4 12a8 8 0 0 1 8-8 8.5 8.5 0 0 1 6 2.4L20 8" stroke="currentColor" strokeWidth={S} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M20 3.5V8h-4.5" stroke="currentColor" strokeWidth={S} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M20 12a8 8 0 0 1-8 8 8.5 8.5 0 0 1-6-2.4L4 16" stroke="currentColor" strokeWidth={S} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 20.5V16h4.5" stroke="currentColor" strokeWidth={S} strokeLinecap="round" strokeLinejoin="round" />
  </>
))

// ─────────────────────────────────────────────────────────────────────────
// More custom Halo icons
// ─────────────────────────────────────────────────────────────────────────

export const AlertCircle = createIcon('AlertCircle', (
  <>
    <circle cx="12" cy="12" r="8.8" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 7.6v5.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    <circle cx="12" cy="16.2" r="1.05" fill="currentColor"/>
  </>
))
export const AlertTriangle = createIcon('AlertTriangle', (
  <>
    <path d="M12 3.6 21.4 19.6a1.2 1.2 0 0 1-1 1.8H3.6a1.2 1.2 0 0 1-1-1.8z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M12 9.5v4.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"/>
    <circle cx="12" cy="17.3" r="1.05" fill="currentColor"/>
  </>
))
export const Archive = createIcon('Archive', (
  <>
    <rect x="3.5" y="4" width="17" height="4.5" rx="1.3" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M5 8.5v9.5A1.5 1.5 0 0 0 6.5 19.5h11A1.5 1.5 0 0 0 19 18V8.5" fill="currentColor" fillOpacity="0.1" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M10 12.5h4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const ArrowDown = createIcon('ArrowDown', (
  <>
    <path d="M12 4v14.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><path d="M6.4 12.8 12 18.6l5.6-5.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowDownRight = createIcon('ArrowDownRight', (
  <>
    <path d="M7 7 16.8 16.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><path d="M17 8v9h-9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowLeft = createIcon('ArrowLeft', (
  <>
    <path d="M20 12H5.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><path d="M11.2 6.4 5.4 12l5.8 5.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowLeftRight = createIcon('ArrowLeftRight', (
  <>
    <path d="M4 9h13.5M14.5 5.5 18 9l-3.5 3.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M20 15H6.5M9.5 11.5 6 15l3.5 3.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowRight = createIcon('ArrowRight', (
  <>
    <path d="M4 12h14.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><path d="M12.8 6.4 18.6 12l-5.8 5.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowRightLeft = createIcon('ArrowRightLeft', (
  <>
    <path d="M4 9h13.5M14.5 5.5 18 9l-3.5 3.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M20 15H6.5M9.5 11.5 6 15l3.5 3.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowUp = createIcon('ArrowUp', (
  <>
    <path d="M12 20V5.4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><path d="M6.4 11.2 12 5.4l5.6 5.8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowUpDown = createIcon('ArrowUpDown', (
  <>
    <path d="M8 20V4.5M4.5 8 8 4.5 11.5 8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/><path d="M16 4v15.5M12.5 16 16 19.5 19.5 16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ArrowUpRight = createIcon('ArrowUpRight', (
  <>
    <path d="M7 17 16.8 7.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/><path d="M8.6 7h9v9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const AtSign = createIcon('AtSign', (
  <>
    <circle cx="12" cy="12" r="3.7" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M15.7 8.3v4.6a2.5 2.5 0 0 0 5 0V12A8.6 8.6 0 1 0 17 19" fill="currentColor" fillOpacity="0.08" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Ban = createIcon('Ban', (
  <>
    <circle cx="12" cy="12" r="8.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M6 6 18 18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const BarChart3 = createIcon('BarChart3', (
  <>
    <path d="M4.5 3.5v15.5a1 1 0 0 0 1 1H20" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <rect x="7.3" y="12" width="2.9" height="5.5" rx="0.7" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="11.6" y="8.8" width="2.9" height="8.7" rx="0.7" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="15.9" y="5.6" width="2.9" height="11.9" rx="0.7" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const BellRing = createIcon('BellRing', (
  <>
    <path d="M6.5 16.8c1.3-1.3 1.6-2.8 1.6-5.4a3.9 3.9 0 0 1 7.8 0c0 2.6.3 4.1 1.6 5.4z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M10.2 19.8a2.1 2.1 0 0 0 3.6 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M12 5V3.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M3.4 8.4a5.5 5.5 0 0 1 1.8-3.6M20.6 8.4a5.5 5.5 0 0 0-1.8-3.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
  </>
))
export const Bookmark = createIcon('Bookmark', (
  <>
    <path d="M6 4.5h12a1 1 0 0 1 1 1v15l-7-4-7 4v-15a1 1 0 0 1 1-1z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const BotOff = createIcon('BotOff', (
  <>
    <path d="M9 8h8.6a2 2 0 0 1 2 2v6.6M17 19.4H6.4a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 8V4.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="12" cy="3.5" r="1.5" fill="currentColor"/>
    <path d="M2.8 12.4v3M21.2 12.4v3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M3.5 3.5 20.5 20.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Boxes = createIcon('Boxes', (
  <>
    <rect x="8.5" y="12.6" width="7" height="6.9" rx="1.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="3.4" y="4.5" width="7" height="6.9" rx="1.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="13.6" y="4.5" width="7" height="6.9" rx="1.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const Bug = createIcon('Bug', (
  <>
    <rect x="7.5" y="7.5" width="9" height="11.5" rx="4.5" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M9.6 7.6 8.2 5.2M14.4 7.6 15.8 5.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M7.5 11H4.4M7.5 14.4H3.9M7.6 17.8l-3 1.6M16.5 11h3.1M16.5 14.4h3.6M16.4 17.8l3 1.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.75"/>
    <path d="M12 10.5v6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
  </>
))
export const Building2 = createIcon('Building2', (
  <>
    <path d="M4 20.5V5.5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v15" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M12 10h6.5a1 1 0 0 1 1 1v9.5" fill="currentColor" fillOpacity="0.1" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M2.5 20.5h19" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M7 8.5h2M7 12h2M7 15.5h2M15 13.5h1.5M15 17h1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
  </>
))
export const Calendar = createIcon('Calendar', (
  <>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2.6" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3.5 9.5h17" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M8 3.4v3M16 3.4v3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const CalendarClock = createIcon('CalendarClock', (
  <>
    <path d="M20.5 11.4V7.6A2.6 2.6 0 0 0 17.9 5H6.1A2.6 2.6 0 0 0 3.5 7.6v9.8A2.6 2.6 0 0 0 6.1 20h5" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M3.5 9.5h17M8 3.4v3M16 3.4v3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="16.8" cy="16.8" r="4.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.6"/>
    <path d="M16.8 15v1.8l1.3.9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const CalendarDays = createIcon('CalendarDays', (
  <>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2.6" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3.5 9.5h17" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M8 3.4v3M16 3.4v3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="8.2" cy="13.5" r="1" fill="currentColor"/><circle cx="12" cy="13.5" r="1" fill="currentColor"/><circle cx="15.8" cy="13.5" r="1" fill="currentColor"/><circle cx="8.2" cy="17" r="1" fill="currentColor"/><circle cx="12" cy="17" r="1" fill="currentColor"/>
  </>
))
export const Check = createIcon('Check', (
  <>
    <path d="M4.8 12.5 9.5 17.2 19.2 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const CheckCircle = createIcon('CheckCircle', (
  <>
    <circle cx="12" cy="12" r="8.8" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M8.4 12.2 11 14.8l4.6-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const CheckCircle2 = createIcon('CheckCircle2', (
  <>
    <circle cx="12" cy="12" r="8.8" fill="currentColor" fillOpacity="0.2" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M8.4 12.2 11 14.8l4.6-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ChevronDown = createIcon('ChevronDown', (
  <>
    <path d="M5.5 9 12 15.2 18.5 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ChevronLeft = createIcon('ChevronLeft', (
  <>
    <path d="M14.5 6 8.5 12l6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ChevronRight = createIcon('ChevronRight', (
  <>
    <path d="M9.5 6 15.5 12l-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ChevronUp = createIcon('ChevronUp', (
  <>
    <path d="M6 14.5 12 8.5l6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ChevronsLeft = createIcon('ChevronsLeft', (
  <>
    <path d="M12.5 6.5 7 12l5.5 5.5M19 6.5 13.5 12l5.5 5.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ChevronsRight = createIcon('ChevronsRight', (
  <>
    <path d="M11.5 6.5 17 12l-5.5 5.5M5 6.5 10.5 12 5 17.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Circle = createIcon('Circle', (
  <>
    <circle cx="12" cy="12" r="8.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const ClipboardList = createIcon('ClipboardList', (
  <>
    <path d="M6 5h2.2M15.8 5H18a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h0" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <rect x="8.2" y="3.2" width="7.6" height="3.6" rx="1.2" fill="currentColor" fillOpacity="0.2" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M9 11.5h6.5M9 15h6.5M9 18h3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.65"/>
  </>
))
export const Clock = createIcon('Clock', (
  <>
    <circle cx="12" cy="12" r="8.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 7.4V12l3.1 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Code = createIcon('Code', (
  <>
    <path d="M8.5 8 4 12l4.5 4M15.5 8 20 12l-4.5 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M13.6 6 10.4 18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.7"/>
  </>
))
export const Copy = createIcon('Copy', (
  <>
    <rect x="8" y="8" width="12" height="12" rx="2.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Cpu = createIcon('Cpu', (
  <>
    <rect x="6.5" y="6.5" width="11" height="11" rx="2.2" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="9.8" y="9.8" width="4.4" height="4.4" rx="1" stroke="currentColor" strokeWidth="1.6"/>
    <path d="M9.5 6.5V3.6M14.5 6.5V3.6M9.5 20.4v-2.9M14.5 20.4v-2.9M6.5 9.5H3.6M6.5 14.5H3.6M20.4 9.5h-2.9M20.4 14.5h-2.9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
  </>
))
export const CreditCard = createIcon('CreditCard', (
  <>
    <rect x="3" y="5.5" width="18" height="13" rx="2.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3 9.5h18" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M6.5 14.5h3.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.6"/>
  </>
))
export const Crosshair = createIcon('Crosshair', (
  <>
    <circle cx="12" cy="12" r="8.6" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 2.4v4.2M12 17.4v4.2M2.4 12h4.2M17.4 12h4.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Crown = createIcon('Crown', (
  <>
    <path d="M3.5 8 7 12l5-6.2 5 6.2 3.5-4-1.6 11.2H5.1z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M5.1 17.2h13.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Database = createIcon('Database', (
  <>
    <ellipse cx="12" cy="6" rx="7.5" ry="2.9" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M4.5 6v12c0 1.6 3.4 2.9 7.5 2.9s7.5-1.3 7.5-2.9V6" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M4.5 12c0 1.6 3.4 2.9 7.5 2.9s7.5-1.3 7.5-2.9" stroke="currentColor" strokeWidth="1.7" opacity="0.6"/>
  </>
))
export const Download = createIcon('Download', (
  <>
    <path d="M12 3.5v11.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M7.4 10.4 12 15l4.6-4.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M4.5 18.5a1.6 1.6 0 0 0 1.6 1.6h11.8a1.6 1.6 0 0 0 1.6-1.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const ExternalLink = createIcon('ExternalLink', (
  <>
    <path d="M13.5 5H19v5.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M19 5 11 13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M17.5 13.8v3.7A2 2 0 0 1 15.5 19.5h-9A2 2 0 0 1 4.5 17.5v-9A2 2 0 0 1 6.5 6.5H10" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Eye = createIcon('Eye', (
  <>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <circle cx="12" cy="12" r="2.8" fill="currentColor" fillOpacity="0.25" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const EyeOff = createIcon('EyeOff', (
  <>
    <path d="M10.4 6.2A9.7 9.7 0 0 1 12 6c6 0 9.5 6 9.5 6a15 15 0 0 1-2.7 3.1M6.4 7.5A14.6 14.6 0 0 0 2.5 12s3.5 6 9.5 6a9.6 9.6 0 0 0 3.4-.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M9.9 10a2.8 2.8 0 0 0 3.8 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M3.5 3.5 20.5 20.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const FileCode = createIcon('FileCode', (
  <>
    <path d="M6 3.5h7l5 5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M13 3.5v5h5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M9.8 12.8 8 14.5l1.8 1.7M14.2 12.8 16 14.5l-1.8 1.7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const FileJson = createIcon('FileJson', (
  <>
    <path d="M6 3.5h7l5 5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M13 3.5v5h5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M10.2 12.6c-.9 0-1 .5-1 1.3 0 .7-.2 1.1-.8 1.1.6 0 .8.4.8 1.1 0 .8.1 1.3 1 1.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M13.8 12.6c.9 0 1 .5 1 1.3 0 .7.2 1.1.8 1.1-.6 0-.8.4-.8 1.1 0 .8-.1 1.3-1 1.3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const FileSearch = createIcon('FileSearch', (
  <>
    <path d="M6 3.5h7l5 5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M13 3.5v5h5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <circle cx="10.8" cy="14" r="2.3" stroke="currentColor" strokeWidth="1.5"/>
    <path d="m12.6 15.8 1.7 1.7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </>
))
export const FileText = createIcon('FileText', (
  <>
    <path d="M6 3.5h7l5 5V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M13 3.5v5h5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M8.5 12.5h7M8.5 15.5h7M8.5 18.3h4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.6"/>
  </>
))
export const Filter = createIcon('Filter', (
  <>
    <path d="M4 5.5h16l-6.2 7.3v5.4l-3.6-1.8v-3.6z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Fingerprint = createIcon('Fingerprint', (
  <>
    <path d="M12 11a2 2 0 0 0-2 2v1.5a3.5 3.5 0 0 0 .5 1.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
    <path d="M8 13a4 4 0 0 1 8 0v1.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
    <path d="M5.6 13a6.4 6.4 0 0 1 12.8 0v2a13 13 0 0 1-.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
    <path d="M6.4 18.5A12 12 0 0 0 7.5 14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
    <path d="M4.5 8.5a9 9 0 0 1 15 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.7"/>
    <path d="M12 19.5V13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.5"/>
  </>
))
export const FolderGit2 = createIcon('FolderGit2', (
  <>
    <path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2.4h8A1.5 1.5 0 0 1 20.5 9.9V17A1.5 1.5 0 0 1 19 18.5H5A1.5 1.5 0 0 1 3.5 17z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <circle cx="9" cy="13.5" r="1.6" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="15" cy="13.5" r="1.6" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M10.6 13.5h2.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </>
))
export const Gauge = createIcon('Gauge', (
  <>
    <path d="M4.2 17a8.6 8.6 0 1 1 15.6 0" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 13.5 16 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="12" cy="14" r="1.4" fill="currentColor"/>
  </>
))
export const Gift = createIcon('Gift', (
  <>
    <rect x="4" y="9.5" width="16" height="10.5" rx="1.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3 9.5h18M12 9.5V20" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 9.5C12 7 10.6 5.4 8.8 6.1 7.3 6.7 8 9.3 10.2 9.5M12 9.5C12 7 13.4 5.4 15.2 6.1 16.7 6.7 16 9.3 13.8 9.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const GitCompare = createIcon('GitCompare', (
  <>
    <circle cx="6" cy="18" r="2.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="18" cy="6" r="2.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M11 6H15.4M14 4 16 6l-2 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M13 18H8.6M10 16 8 18l2 2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M18 8.6V14M6 15.4V10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.6"/>
  </>
))
export const Github = createIcon('Github', (
  <>
    <path d="M12 2.2a9.8 9.8 0 0 0-3.1 19.1c.5.1.7-.2.7-.5v-1.7c-2.7.6-3.3-1.3-3.3-1.3-.5-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.3 1.1 2.9.8.1-.6.3-1.1.6-1.4-2.2-.2-4.5-1.1-4.5-4.9a3.8 3.8 0 0 1 1-2.6 3.6 3.6 0 0 1 .1-2.6s.8-.3 2.7 1a9.3 9.3 0 0 1 4.8 0c1.9-1.3 2.7-1 2.7-1a3.6 3.6 0 0 1 .1 2.6 3.8 3.8 0 0 1 1 2.6c0 3.8-2.3 4.7-4.5 4.9.3.3.6.9.6 1.9v2.8c0 .3.2.6.7.5A9.8 9.8 0 0 0 12 2.2z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
  </>
))
export const Globe2 = createIcon('Globe2', (
  <>
    <circle cx="12" cy="12" r="8.6" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3.6 10.5h6.5l1.5 3-2 3 1 4M16 4.5l-1 3 2.5 2-1 2.5 3.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" opacity="0.85"/>
  </>
))
export const GripVertical = createIcon('GripVertical', (
  <>
    <circle cx="9" cy="6" r="1.35" fill="currentColor"/><circle cx="9" cy="12" r="1.35" fill="currentColor"/><circle cx="9" cy="18" r="1.35" fill="currentColor"/>
    <circle cx="15" cy="6" r="1.35" fill="currentColor"/><circle cx="15" cy="12" r="1.35" fill="currentColor"/><circle cx="15" cy="18" r="1.35" fill="currentColor"/>
  </>
))
export const HardDrive = createIcon('HardDrive', (
  <>
    <rect x="3" y="8.6" width="18" height="6.8" rx="2.2" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M6.5 8.6 8.4 5.6a1.2 1.2 0 0 1 1-.6h5.2a1.2 1.2 0 0 1 1 .6l1.9 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="16.8" cy="12" r="1.05" fill="currentColor"/>
    <path d="M6.5 12h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.5"/>
  </>
))
export const Hash = createIcon('Hash', (
  <>
    <path d="M4.5 9h15M4.5 15h15M10 4l-1.6 16M16 4l-1.6 16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Heart = createIcon('Heart', (
  <>
    <path d="M12 20.4 4.5 12.9a4.7 4.7 0 0 1 6.6-6.6l.9.9.9-.9a4.7 4.7 0 0 1 6.6 6.6z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const HeartPulse = createIcon('HeartPulse', (
  <>
    <path d="M12 20.4 4.5 12.9a4.7 4.7 0 0 1 6.6-6.6l.9.9.9-.9a4.7 4.7 0 0 1 6.6 6.6z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M3.8 13h3.4l1.3-2.6 2.1 5 1.4-2.9h3.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const HelpCircle = createIcon('HelpCircle', (
  <>
    <circle cx="12" cy="12" r="8.8" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M9.6 9.4a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1.3 1-1.3 1.9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="11.7" cy="16.4" r="1.05" fill="currentColor"/>
  </>
))
export const History = createIcon('History', (
  <>
    <path d="M3.4 12a8.6 8.6 0 1 0 2.6-6.1L3 8.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M3 4.5V9h4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 7.8V12l3.2 1.9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Home = createIcon('Home', (
  <>
    <path d="M4 11 12 4.5 20 11" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M5.6 9.6V19a1 1 0 0 0 1 1H17.4a1 1 0 0 0 1-1V9.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M9.8 20v-4.5a1 1 0 0 1 1-1h2.4a1 1 0 0 1 1 1V20" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Inbox = createIcon('Inbox', (
  <>
    <path d="M3.5 12.5 5.9 6.7A1.5 1.5 0 0 1 7.3 5.8h9.4a1.5 1.5 0 0 1 1.4.9l2.4 5.8V18A1.5 1.5 0 0 1 19 19.5H5A1.5 1.5 0 0 1 3.5 18z" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M3.5 12.5h4.2l1.4 2.4h5.8l1.4-2.4h4.2" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Infinity = createIcon('Infinity', (
  <>
    <path d="M11.5 12c-1.6 2.2-3.3 3.3-5 3.3a3.5 3.5 0 1 1 0-7c1.7 0 3.4 1.1 5 3.3m1 0c1.6 2.2 3.3 3.3 5 3.3a3.5 3.5 0 0 0 0-7c-1.7 0-3.4 1.1-5 3.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Info = createIcon('Info', (
  <>
    <circle cx="12" cy="12" r="8.8" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 11v5.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
    <circle cx="12" cy="7.8" r="1.05" fill="currentColor"/>
  </>
))
export const Key = createIcon('Key', (
  <>
    <circle cx="8.5" cy="8.5" r="4.3" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="8.5" cy="8.5" r="1.3" fill="currentColor"/>
    <path d="M11.6 11.6 19 19" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M16.4 16.4l2-2M18.2 18.2l1.6-1.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const KeyRound = createIcon('KeyRound', (
  <>
    <circle cx="14.8" cy="9.2" r="4" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="14.8" cy="9.2" r="1.2" fill="currentColor"/>
    <path d="M12 12 4.5 19.5v2.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M4.5 21.7h2.3v-2M7 17.2h2.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Laptop = createIcon('Laptop', (
  <>
    <rect x="5" y="5" width="14" height="10" rx="1.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M2.5 18.5h19l-1-2.2a1 1 0 0 0-.9-.6H4.4a1 1 0 0 0-.9.6z" fill="currentColor" fillOpacity="0.1" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Lightbulb = createIcon('Lightbulb', (
  <>
    <path d="M9 16.2a5.6 5.6 0 1 1 6 0c-.7.6-1 1.3-1 2.3h-4c0-1-.3-1.7-1-2.3z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M9.5 20h5M10.2 22h3.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Link = createIcon('Link', (
  <>
    <path d="M9.5 14.5 14.5 9.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M8.5 11 6.8 12.7a3.6 3.6 0 0 0 5.1 5.1l1.6-1.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M15.5 13 17.2 11.3a3.6 3.6 0 0 0-5.1-5.1L10.5 7.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const List = createIcon('List', (
  <>
    <path d="M8.5 6.5h11.5M8.5 12h11.5M8.5 17.5h11.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="4.5" cy="6.5" r="1.15" fill="currentColor"/><circle cx="4.5" cy="12" r="1.15" fill="currentColor"/><circle cx="4.5" cy="17.5" r="1.15" fill="currentColor"/>
  </>
))
export const ListOrdered = createIcon('ListOrdered', (
  <>
    <path d="M9.5 6.5h10.5M9.5 12h10.5M9.5 17.5h10.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M4 5.2 5.2 4.6V8.6M4 8.6h2.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M4.2 14.5a1.1 1.1 0 0 1 2 .7c0 .9-2 1.5-2 2.8h2.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Loader2 = createIcon('Loader2', (
  <>
    <path d="M21 12a9 9 0 1 1-6.2-8.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
  </>
))
export const Lock = createIcon('Lock', (
  <>
    <rect x="4.5" y="10.5" width="15" height="9.5" rx="2.4" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M8 10.5V7.8a4 4 0 0 1 8 0v2.7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="12" cy="15.2" r="1.2" fill="currentColor"/>
  </>
))
export const LogOut = createIcon('LogOut', (
  <>
    <path d="M9.5 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h3" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M15.5 8.2 19.5 12l-4 3.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M19 12H9.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Mail = createIcon('Mail', (
  <>
    <rect x="3" y="5.5" width="18" height="13" rx="2.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M4.2 7.8 12 13l7.8-5.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const MailOpen = createIcon('MailOpen', (
  <>
    <path d="M3.5 10.3 12 5l8.5 5.3V18A1.5 1.5 0 0 1 19 19.5H5A1.5 1.5 0 0 1 3.5 18z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M3.6 10.5 12 15.5l8.4-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const MapPin = createIcon('MapPin', (
  <>
    <path d="M12 21.5s7-5.9 7-11.5a7 7 0 1 0-14 0c0 5.6 7 11.5 7 11.5z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <circle cx="12" cy="10" r="2.6" fill="currentColor" fillOpacity="0.3" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const Maximize2 = createIcon('Maximize2', (
  <>
    <path d="M15 4.5h4.5V9M9 19.5H4.5V15M19.5 4.5 14 10M4.5 19.5 10 14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Megaphone = createIcon('Megaphone', (
  <>
    <path d="M4 10.2 16.5 6v12L4 13.8z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M6.5 14.2v3.4a1.6 1.6 0 0 0 3.2 0v-2.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M19 9.5a3.2 3.2 0 0 1 0 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.7"/>
  </>
))
export const MemoryStick = createIcon('MemoryStick', (
  <>
    <path d="M4 9h16v6.5l-2.2 2.2H6.2L4 15.5z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M7.5 9V5.8M12 9V5.8M16.5 9V5.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
    <path d="M8 18.5v2M12 18.5v2M16 18.5v2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.6"/>
  </>
))
export const Menu = createIcon('Menu', (
  <>
    <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
  </>
))
export const MessageCircle = createIcon('MessageCircle', (
  <>
    <path d="M20.5 11.6a8 8 0 0 1-11.5 7.2L4 20.5l1.7-4.8A8 8 0 1 1 20.5 11.6Z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <circle cx="8.8" cy="12" r="1.05" fill="currentColor"/>
    <circle cx="12.3" cy="12" r="1.05" fill="currentColor"/>
    <circle cx="15.8" cy="12" r="1.05" fill="currentColor"/>
  </>
))
export const MessageSquare = createIcon('MessageSquare', (
  <>
    <path d="M4 6.5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9.5L5 19.5V6.5z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Minimize2 = createIcon('Minimize2', (
  <>
    <path d="M4.5 10H9V5.5M19.5 14H15v4.5M9 10 4.5 5.5M15 14l4.5 4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Minus = createIcon('Minus', (
  <>
    <path d="M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
  </>
))
export const Monitor = createIcon('Monitor', (
  <>
    <rect x="3" y="4.5" width="18" height="12" rx="2" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M8.5 20h7M12 16.5V20" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const MonitorSmartphone = createIcon('MonitorSmartphone', (
  <>
    <path d="M18 8.5V7a1.5 1.5 0 0 0-1.5-1.5H4.5A1.5 1.5 0 0 0 3 7v7a1.5 1.5 0 0 0 1.5 1.5H10" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7 19.5h3.5M9 15.5v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <rect x="13.5" y="10.5" width="7.5" height="10" rx="1.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M16.6 17.8h1.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </>
))
export const Moon = createIcon('Moon', (
  <>
    <path d="M20.5 14.3A8.5 8.5 0 1 1 9.7 3.5a6.6 6.6 0 0 0 10.8 10.8z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const MoreHorizontal = createIcon('MoreHorizontal', (
  <>
    <circle cx="5.5" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="18.5" cy="12" r="1.5" fill="currentColor"/>
  </>
))
export const MoreVertical = createIcon('MoreVertical', (
  <>
    <circle cx="12" cy="5.5" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="18.5" r="1.5" fill="currentColor"/>
  </>
))
export const Network = createIcon('Network', (
  <>
    <rect x="9" y="3" width="6" height="5" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="3" y="16" width="6" height="5" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="15" y="16" width="6" height="5" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 8v4M12 12H6v4M12 12h6v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Package = createIcon('Package', (
  <>
    <path d="M12 3 20 7.3v9.4L12 21 4 16.7V7.3z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M4.3 7.5 12 11.8l7.7-4.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12 11.8V21" stroke="currentColor" strokeWidth="1.7" opacity="0.6"/>
    <path d="m8 5.2 7.7 4.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.5"/>
  </>
))
export const PackagePlus = createIcon('PackagePlus', (
  <>
    <path d="M20 12V7.3L12 3 4 7.3v9.4L12 21l3-1.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="currentColor" fillOpacity="0.13"/>
    <path d="M4.3 7.5 12 11.8l7.7-4.3M12 11.8v5.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" opacity="0.6"/>
    <path d="M18.5 16v5M16 18.5h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Paintbrush = createIcon('Paintbrush', (
  <>
    <path d="M19.5 4.5a1.8 1.8 0 0 0-2.6 0l-6 6 2.6 2.6 6-6a1.8 1.8 0 0 0 0-2.6z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M10.9 10.5a4 4 0 0 0-5.4 3.8c0 1-.9 1.9-2 1.9 1.2 1.6 3.5 2.4 5.4 1.6a4 4 0 0 0 2.4-4.7z" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Pause = createIcon('Pause', (
  <>
    <rect x="6.5" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/><rect x="13.9" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const Pencil = createIcon('Pencil', (
  <>
    <path d="M16.4 4.4a1.9 1.9 0 0 1 2.7 2.7L7.9 18.3 4 19.5l1.2-3.9z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M14.6 6.2 17.8 9.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Play = createIcon('Play', (
  <>
    <path d="M7 5.6a1 1 0 0 1 1.5-.86l9.5 5.5a1 1 0 0 1 0 1.73l-9.5 5.5A1 1 0 0 1 7 16.7z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Power = createIcon('Power', (
  <>
    <path d="M12 3.5V11" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M7.3 6.8a7.5 7.5 0 1 0 9.4 0" fill="currentColor" fillOpacity="0.12" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const PowerOff = createIcon('PowerOff', (
  <>
    <path d="M12 3.5V9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M16.4 7.6a7.5 7.5 0 1 1-8.9.1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M4 4 20 20" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const QrCode = createIcon('QrCode', (
  <>
    <rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="14" y="3.5" width="6.5" height="6.5" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <rect x="3.5" y="14" width="6.5" height="6.5" rx="1.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M14 14h3v3M20.5 14v6.5M14 20.5h3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Recycle = createIcon('Recycle', (
  <>
    <path d="M8.5 6.5 11 3l2.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M11 3.5v6.5l-4.8 8.2a1.5 1.5 0 0 1-1.3.8H4M19 14l1.8 3a1.5 1.5 0 0 1 .1 1.5l-.5 1M7 20.5h8.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" opacity="0.85"/>
    <path d="M17.5 21 19 18.5 16.3 17M5.5 16 4 18.5l2.7 1.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const RotateCcw = createIcon('RotateCcw', (
  <>
    <path d="M4 9.5A8 8 0 1 1 4 14.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M4 4.5V10h5.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const RotateCw = createIcon('RotateCw', (
  <>
    <path d="M20 9.5A8 8 0 1 0 20 14.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M20 4.5V10h-5.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Save = createIcon('Save', (
  <>
    <path d="M5 4.5h11l3.5 3.5V18.5A1.5 1.5 0 0 1 18 20H6a1.5 1.5 0 0 1-1.5-1.5V6A1.5 1.5 0 0 1 5 4.5Z" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M7.5 4.5v4.5h7V4.5" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <rect x="7.5" y="12.5" width="9" height="7.5" rx="0.6" stroke="currentColor" strokeWidth="1.5" opacity="0.7"/>
  </>
))
export const Scan = createIcon('Scan', (
  <>
    <path d="M4 8.5V6.5A2.5 2.5 0 0 1 6.5 4h2M15.5 4h2A2.5 2.5 0 0 1 20 6.5v2M20 15.5v2a2.5 2.5 0 0 1-2.5 2.5h-2M8.5 20h-2A2.5 2.5 0 0 1 4 17.5v-2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M4 12h16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const SearchX = createIcon('SearchX', (
  <>
    <circle cx="10.5" cy="10.5" r="6.5" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/><path d="m15.5 15.5 4.5 4.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round"/><path d="M8.6 8.6 12.4 12.4M12.4 8.6 8.6 12.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </>
))
export const Send = createIcon('Send', (
  <>
    <path d="M20.5 3.5 3.5 10.3l7 2.6 2.6 7z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M20.5 3.5 10.5 12.9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const ServerCrash = createIcon('ServerCrash', (
  <>
    <path d="M4 9.5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v.5a2 2 0 0 1-2 2h-3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M9 12H6a2 2 0 0 0-2 2v.5a2 2 0 0 0 2 2h2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="7" cy="9.7" r="1" fill="currentColor"/>
    <path d="M13.5 11 11 15h3l-2.5 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Settings2 = createIcon('Settings2', (
  <>
    <path d="M11 7H4M20 7h-3M8 17H4M20 17h-7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="14" cy="7" r="2.4" fill="currentColor" fillOpacity="0.18" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="10.5" cy="17" r="2.4" fill="currentColor" fillOpacity="0.18" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const Share2 = createIcon('Share2', (
  <>
    <circle cx="6" cy="12" r="2.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="17.5" cy="6" r="2.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="17.5" cy="18" r="2.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="m8.3 10.8 6.9-3.6M8.3 13.2l6.9 3.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.7"/>
  </>
))
export const Shield = createIcon('Shield', (
  <>
    <path d="M12 2.8 19 5.3v5.7c0 4.6-3 7.4-7 9.2-4-1.8-7-4.6-7-9.2V5.3z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const ShieldBan = createIcon('ShieldBan', (
  <>
    <path d="M12 2.8 19 5.3v5.7c0 4.6-3 7.4-7 9.2-4-1.8-7-4.6-7-9.2V5.3z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <circle cx="12" cy="11.3" r="3.5" stroke="currentColor" strokeWidth="1.6"/>
    <path d="M9.5 8.8l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
  </>
))
export const ShieldCheck = createIcon('ShieldCheck', (
  <>
    <path d="M12 2.8 19 5.3v5.7c0 4.6-3 7.4-7 9.2-4-1.8-7-4.6-7-9.2V5.3z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M8.8 11.6 11 13.8l4.2-4.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const ShieldOff = createIcon('ShieldOff', (
  <>
    <path d="M8.2 4.4 12 2.8 19 5.3v5.7a10.6 10.6 0 0 1-1 4.5M16.8 18.2c-1.4 1-3 1.8-4.8 2.6-4-1.8-7-4.6-7-9.2V7.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M3.5 3.5 20.5 20.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Ship = createIcon('Ship', (
  <>
    <path d="M4 14.5h16l-1.6 4.6a1.5 1.5 0 0 1-1.4 1H7a1.5 1.5 0 0 1-1.4-1z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M6.5 14.5v-4h11v4M12 10.5V5M8.5 7.5h7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Sliders = createIcon('Sliders', (
  <>
    <path d="M4 8h8M16 8h4M4 16h4M12 16h8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="14" cy="8" r="2.2" fill="currentColor" fillOpacity="0.18" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="9" cy="16" r="2.2" fill="currentColor" fillOpacity="0.18" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const Smartphone = createIcon('Smartphone', (
  <>
    <rect x="6.5" y="3" width="11" height="18" rx="2.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M10.5 17.8h3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Sparkles = createIcon('Sparkles', (
  <>
    <path d="M12 3.5 13.7 9 19 10.7 13.7 12.4 12 17.9 10.3 12.4 5 10.7 10.3 9z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/>
    <path d="M18.4 4.3 19 6.1 20.8 6.7 19 7.3 18.4 9.1 17.8 7.3 16 6.7 17.8 6.1z" fill="currentColor"/>
    <path d="M5.6 15.4 6 16.7 7.3 17.1 6 17.5 5.6 18.8 5.2 17.5 3.9 17.1 5.2 16.7z" fill="currentColor"/>
  </>
))
export const Square = createIcon('Square', (
  <>
    <rect x="4" y="4" width="16" height="16" rx="2.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const Star = createIcon('Star', (
  <>
    <path d="M12 3.4 14.7 9.1 21 9.9 16.5 14.2 17.6 20.4 12 17.4 6.4 20.4 7.5 14.2 3 9.9 9.3 9.1z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const Stethoscope = createIcon('Stethoscope', (
  <>
    <path d="M5 4v4.2a4 4 0 0 0 8 0V4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="5" cy="3.8" r="1.3" fill="currentColor" fillOpacity="0.25" stroke="currentColor" strokeWidth="1.4"/>
    <circle cx="13" cy="3.8" r="1.3" fill="currentColor" fillOpacity="0.25" stroke="currentColor" strokeWidth="1.4"/>
    <path d="M9 12.4v2.1a5.5 5.5 0 0 0 5.5 5.5 3.8 3.8 0 0 0 3.8-3.8V14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="18.3" cy="12.3" r="2.3" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
  </>
))
export const Sun = createIcon('Sun', (
  <>
    <circle cx="12" cy="12" r="4.2" fill="currentColor" fillOpacity="0.2" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 2.5v2.4M12 19.1v2.4M4.2 12H1.8M22.2 12h-2.4M5.8 5.8 7.5 7.5M16.5 16.5l1.7 1.7M18.2 5.8 16.5 7.5M7.5 16.5 5.8 18.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Tag = createIcon('Tag', (
  <>
    <path d="M11 3.5H5.5a2 2 0 0 0-2 2V11l8.6 8.6a2 2 0 0 0 2.8 0l4.7-4.7a2 2 0 0 0 0-2.8L11 3.5z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <circle cx="8.2" cy="8.2" r="1.3" fill="currentColor"/>
  </>
))
export const Terminal = createIcon('Terminal', (
  <>
    <rect x="3" y="4.5" width="18" height="15" rx="2.6" fill="currentColor" fillOpacity="0.13" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M7.5 9.5 10.5 12l-3 2.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M12.5 14.5h4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Ticket = createIcon('Ticket', (
  <>
    <path d="M4 7h16a1 1 0 0 1 1 1v2.3a1.7 1.7 0 0 0 0 3.4V16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-2.3a1.7 1.7 0 0 0 0-3.4V8a1 1 0 0 1 1-1Z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
    <path d="M14.5 8.2v7.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeDasharray="1.4 2" opacity="0.7"/>
  </>
))
export const Timer = createIcon('Timer', (
  <>
    <circle cx="12" cy="13.5" r="7.4" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M12 9.8v3.7h2.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M9.6 3.3h4.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const TrendingDown = createIcon('TrendingDown', (
  <>
    <path d="M3.5 7.5 9.5 13.5l3.5-3.5L20.5 17.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M15.5 17.5h5v-5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const TrendingUp = createIcon('TrendingUp', (
  <>
    <path d="M3.5 16.5 9.5 10.5l3.5 3.5L20.5 6.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M15.5 6.5h5v5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const Upload = createIcon('Upload', (
  <>
    <path d="M12 15.5V4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M7.4 9 12 4.4 16.6 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M4.5 18.5a1.6 1.6 0 0 0 1.6 1.6h11.8a1.6 1.6 0 0 0 1.6-1.6" fill="currentColor" fillOpacity="0.14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const User = createIcon('User', (
  <>
    <circle cx="12" cy="8" r="3.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M5 19.6a7 7 0 0 1 14 0" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const UserCheck = createIcon('UserCheck', (
  <>
    <circle cx="9.5" cy="8" r="3.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3.5 19.6a6.4 6.4 0 0 1 12 -2.9" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M16 12.2 18 14.2l3.5-3.7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
  </>
))
export const UserCog = createIcon('UserCog', (
  <>
    <circle cx="10" cy="7.5" r="3.3" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M4 19.2a6 6 0 0 1 9.4-3.3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="17.5" cy="16.5" r="2.2" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M17.5 13.4v-.9M17.5 20.5v-.9M20.2 18l-.8-.5M15.6 15l-.8-.5M20.2 15l-.8.5M15.6 18l-.8.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
  </>
))
export const UserMinus = createIcon('UserMinus', (
  <>
    <circle cx="9.5" cy="8" r="3.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3.5 19.6a6.4 6.4 0 0 1 12 -2.9" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M15.5 12h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const UserPlus = createIcon('UserPlus', (
  <>
    <circle cx="9.5" cy="8" r="3.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3.5 19.6a6.4 6.4 0 0 1 12 -2.9" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M18.5 9v6M15.5 12h6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const UserX = createIcon('UserX', (
  <>
    <circle cx="9.5" cy="8" r="3.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M3.5 19.6a6.4 6.4 0 0 1 12 -2.9" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M16 10 21 15M21 10 16 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const UsersRound = createIcon('UsersRound', (
  <>
    <circle cx="12" cy="8" r="3.4" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M5.8 19.6a6.4 6.4 0 0 1 12.4 0" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M4 17.5a3.7 3.7 0 0 1 2-3.1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.6"/>
    <path d="M20 17.5a3.7 3.7 0 0 0-2-3.1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" opacity="0.6"/>
  </>
))
export const Webhook = createIcon('Webhook', (
  <>
    <path d="M14.5 8.5a3.7 3.7 0 1 0-5 3.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M12 10.5 8.4 16.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="7" cy="18" r="2.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <circle cx="17" cy="18" r="2.6" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M9.6 18h4.8M14.5 10.5 17 15.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Wifi = createIcon('Wifi', (
  <>
    <path d="M4.5 9.2a11.5 11.5 0 0 1 15 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M7.6 12.8a7 7 0 0 1 8.8 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M10.4 16.2a3 3 0 0 1 3.2 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="12" cy="19" r="1.2" fill="currentColor"/>
  </>
))
export const WifiOff = createIcon('WifiOff', (
  <>
    <path d="M4.5 9.2a11.5 11.5 0 0 1 4-2.6M14 6.5a11.5 11.5 0 0 1 5.5 2.7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M7.6 12.8a7 7 0 0 1 2.4-1.5M16.4 12.8a7 7 0 0 0-1.4-1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M10.4 16.2a3 3 0 0 1 3.2 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
    <circle cx="12" cy="19" r="1.2" fill="currentColor"/>
    <path d="M3.5 3.5 20.5 20.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Wrench = createIcon('Wrench', (
  <>
    <path d="M15.6 4.4a4.6 4.6 0 0 0-6 5.9l-5.7 5.7a1.9 1.9 0 0 0 2.7 2.7l5.7-5.7a4.6 4.6 0 0 0 5.9-6l-2.7 2.7-2.6-.7-.7-2.6z" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
export const X = createIcon('X', (
  <>
    <path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
  </>
))
export const XCircle = createIcon('XCircle', (
  <>
    <circle cx="12" cy="12" r="8.8" fill="currentColor" fillOpacity="0.15" stroke="currentColor" strokeWidth="1.7"/>
    <path d="M9.2 9.2 14.8 14.8M14.8 9.2 9.2 14.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
  </>
))
export const Zap = createIcon('Zap', (
  <>
    <path d="M12.8 2.5 5 13.2a.6.6 0 0 0 .5 1H10l-1 7.3 7.8-10.7a.6.6 0 0 0-.5-1H11z" fill="currentColor" fillOpacity="0.16" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round"/>
  </>
))
