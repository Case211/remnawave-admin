import { useEffect, useState } from "react"
import { Toaster as Sonner } from "sonner"
import { useResolvedColorMode } from "@/store/useAppearanceStore"

type ToasterProps = React.ComponentProps<typeof Sonner>

// Стопку тостов sonner раскрывает наведением мыши. Где наводить нечем
// (телефон, планшет), тосты так и лежали бы друг на друге — там их кладём списком.
const NO_HOVER_QUERY = "(hover: none)"

function useNoHover(): boolean {
  const [noHover, setNoHover] = useState(() => window.matchMedia(NO_HOVER_QUERY).matches)

  useEffect(() => {
    const mq = window.matchMedia(NO_HOVER_QUERY)
    const handler = (e: MediaQueryListEvent) => setNoHover(e.matches)
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [])

  return noHover
}

const Toaster = ({ ...props }: ToasterProps) => {
  const colorMode = useResolvedColorMode()
  const noHover = useNoHover()

  return (
    <Sonner
      theme={colorMode}
      className="toaster group"
      position="bottom-right"
      closeButton
      duration={4000}
      expand={noHover}
      toastOptions={{
        classNames: {
          // Фон непрозрачный, как у меню и поповеров: сквозь стеклянный
          // читались страница и тост, лежащий ниже
          toast:
            "group toast group-[.toaster]:bg-[var(--glass-bg-solid)] group-[.toaster]:text-dark-50 group-[.toaster]:border-[var(--glass-border)] group-[.toaster]:shadow-deep",
          description: "group-[.toast]:text-dark-200 group-[.toast]:text-xs group-[.toast]:mt-0.5",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-[var(--glass-bg-hover)] group-[.toast]:text-dark-100",
          closeButton:
            "group-[.toast]:bg-[var(--glass-bg-hover)] group-[.toast]:border-[var(--glass-border)] group-[.toast]:text-dark-200 group-[.toast]:hover:text-white group-[.toast]:hover:bg-[var(--glass-bg-hover)]",
          success:
            "group-[.toaster]:!border-green-500/30 group-[.toaster]:!text-green-400",
          error:
            "group-[.toaster]:!border-red-500/30 group-[.toaster]:!text-red-400",
          warning:
            "group-[.toaster]:!border-yellow-500/30 group-[.toaster]:!text-yellow-400",
          info:
            "group-[.toaster]:!border-cyan-500/30 group-[.toaster]:!text-cyan-400",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
