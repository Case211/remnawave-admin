import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-md bg-dark-600",
        "after:absolute after:inset-0 after:bg-gradient-to-r after:from-transparent after:via-primary-500/[0.04] after:to-transparent after:animate-shimmer",
        className
      )}
      {...props}
    />
  )
}

export { Skeleton }
