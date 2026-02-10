import { Info } from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface InfoTooltipProps {
  text: string
  className?: string
  iconClassName?: string
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'start' | 'center' | 'end'
}

export function InfoTooltip({
  text,
  className,
  iconClassName,
  side = 'top',
  align = 'center',
}: InfoTooltipProps) {
  return (
    <Tooltip delayDuration={200}>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex items-center justify-center rounded-full p-0.5 text-dark-300 hover:text-dark-100 transition-colors focus:outline-none',
            className,
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <Info className={cn('w-4 h-4', iconClassName)} />
        </button>
      </TooltipTrigger>
      <TooltipContent
        side={side}
        align={align}
        className="max-w-xs text-xs leading-relaxed whitespace-pre-line"
      >
        {text}
      </TooltipContent>
    </Tooltip>
  )
}
