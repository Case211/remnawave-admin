import { Toaster as Sonner } from "sonner"

type ToasterProps = React.ComponentProps<typeof Sonner>

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      position="bottom-right"
      closeButton
      duration={4000}
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-dark-700 group-[.toaster]:text-dark-50 group-[.toaster]:border-dark-400/20 group-[.toaster]:shadow-deep",
          description: "group-[.toast]:text-dark-200 group-[.toast]:text-xs group-[.toast]:mt-0.5",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-dark-600 group-[.toast]:text-dark-100",
          closeButton:
            "group-[.toast]:bg-dark-600 group-[.toast]:border-dark-400/30 group-[.toast]:text-dark-200 group-[.toast]:hover:text-white group-[.toast]:hover:bg-dark-500",
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
