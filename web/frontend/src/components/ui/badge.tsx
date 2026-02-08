import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-cyan-500/30 bg-gradient-to-br from-cyan-500/15 to-cyan-500/10 text-cyan-400",
        success:
          "border-green-500/30 bg-gradient-to-br from-green-500/15 to-green-500/10 text-green-400",
        warning:
          "border-yellow-500/30 bg-gradient-to-br from-yellow-500/15 to-yellow-500/10 text-yellow-400",
        destructive:
          "border-red-500/30 bg-gradient-to-br from-red-500/15 to-red-500/10 text-red-400",
        outline: "text-foreground border-dark-400/30",
        secondary:
          "border-gray-500/30 bg-gradient-to-br from-gray-500/15 to-gray-500/10 text-gray-400",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
