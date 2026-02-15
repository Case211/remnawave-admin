import { cn } from '@/lib/utils'

interface CircularGaugeProps {
  /** Value 0-100 */
  value: number | null
  /** Outer size in pixels */
  size?: number
  /** Stroke width in pixels */
  strokeWidth?: number
  /** Optional class for the container */
  className?: string
}

function getGaugeColor(value: number): string {
  if (value >= 95) return '#ef4444' // red-500
  if (value >= 80) return '#eab308' // yellow-500
  return '#22c55e' // green-500
}

function getGaugeTrackColor(value: number): string {
  if (value >= 95) return 'rgba(239,68,68,0.15)'
  if (value >= 80) return 'rgba(234,179,8,0.15)'
  return 'rgba(34,197,94,0.15)'
}

export default function CircularGauge({
  value,
  size = 56,
  strokeWidth = 5,
  className,
}: CircularGaugeProps) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const normalizedValue = value != null ? Math.min(Math.max(value, 0), 100) : 0
  const strokeDashoffset = circumference - (normalizedValue / 100) * circumference
  const color = value != null ? getGaugeColor(normalizedValue) : '#374151'
  const trackColor = value != null ? getGaugeTrackColor(normalizedValue) : 'rgba(55,65,81,0.3)'

  return (
    <div className={cn('relative inline-flex items-center justify-center', className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={trackColor}
          strokeWidth={strokeWidth}
        />
        {/* Value arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      {/* Center text */}
      <span
        className="absolute text-[11px] font-mono font-semibold"
        style={{ color }}
      >
        {value != null ? `${Math.round(value)}%` : '-'}
      </span>
    </div>
  )
}
