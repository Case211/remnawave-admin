/**
 * TerminalDialog — Dialog wrapper for the WebTerminal component.
 *
 * Provides a fullscreen-capable dialog with session info bar.
 * Uses React.lazy to avoid bundling xterm.js when terminal isn't used.
 */
import { useState, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Maximize2, Minimize2, X, Terminal as TerminalIcon } from 'lucide-react'

const WebTerminal = lazy(() => import('./WebTerminal'))

interface TerminalDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodeUuid: string
  nodeName: string
}

export default function TerminalDialog({
  open,
  onOpenChange,
  nodeUuid,
  nodeName,
}: TerminalDialogProps) {
  const { t } = useTranslation()
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isReady, setIsReady] = useState(false)

  const handleClose = () => {
    setIsReady(false)
    setIsFullscreen(false)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        className={
          isFullscreen
            ? 'fixed inset-0 max-w-none w-screen h-screen rounded-none p-0 translate-x-0 translate-y-0 left-0 top-0 [&>button:last-child]:hidden'
            : 'max-w-4xl w-[90vw] h-[70vh] p-0 [&>button:last-child]:hidden'
        }
      >
        {/* Header bar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-dark-700 bg-dark-900">
          <div className="flex items-center gap-2">
            <TerminalIcon className="w-4 h-4 text-accent-400" />
            <DialogHeader className="p-0 m-0 space-y-0">
              <DialogTitle className="text-sm font-medium text-white">
                {t('fleet.terminal.title')} — {nodeName}
              </DialogTitle>
            </DialogHeader>
            {isReady && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 ml-2">
                {t('fleet.terminal.connected')}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => setIsFullscreen(!isFullscreen)}
            >
              {isFullscreen ? (
                <Minimize2 className="w-3.5 h-3.5" />
              ) : (
                <Maximize2 className="w-3.5 h-3.5" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-red-400 hover:text-red-300"
              onClick={handleClose}
            >
              <X className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>

        {/* Terminal area */}
        <div className="flex-1 overflow-hidden" style={{ height: 'calc(100% - 44px)' }}>
          <Suspense
            fallback={
              <div className="flex items-center justify-center h-full bg-[#0a0a0f]">
                <div className="text-dark-300 text-sm">{t('fleet.terminal.connecting')}...</div>
              </div>
            }
          >
            {open && (
              <WebTerminal
                nodeUuid={nodeUuid}
                nodeName={nodeName}
                onReady={() => setIsReady(true)}
                onDisconnect={() => setIsReady(false)}
              />
            )}
          </Suspense>
        </div>
      </DialogContent>
    </Dialog>
  )
}
