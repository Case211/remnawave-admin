import * as React from "react"

import { cn } from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-dark-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 focus-visible:border-primary-500/50 disabled:cursor-not-allowed disabled:opacity-50 transition-colors hover:border-dark-400/30",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
