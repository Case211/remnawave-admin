import { ReactNode, useState, useEffect, useCallback } from 'react'
import Sidebar from './Sidebar'
import Header from './Header'
import PageBreadcrumbs from './PageBreadcrumbs'
import { CommandPalette } from '../CommandPalette'
import { ShortcutsDialog } from '../ShortcutsDialog'
import { useRealtimeUpdates } from '../../store/useWebSocket'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  // Connect WebSocket for real-time updates (nodes, users, violations)
  useRealtimeUpdates()

  // Global keyboard shortcuts
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Cmd/Ctrl+K — always works, even from inputs
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setCommandOpen((prev) => !prev)
        return
      }

      // Skip "/" and "?" if user is typing in an input/textarea/contenteditable
      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase()
      const isEditable =
        tag === 'input' || tag === 'textarea' || tag === 'select' ||
        target?.isContentEditable === true

      if (isEditable) return
      // Ignore when any modifier is pressed (don't hijack browser shortcuts)
      if (e.metaKey || e.ctrlKey || e.altKey) return

      if (e.key === '/') {
        e.preventDefault()
        setCommandOpen(true)
        return
      }
      if (e.key === '?') {
        e.preventDefault()
        setShortcutsOpen(true)
        return
      }
    },
    [],
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div className="layout-root flex h-screen overflow-hidden bg-[var(--glass-bg)] relative">
      {/* Mesh gradient background */}
      <div className="mesh-bg">
        <div className="mesh-layer mesh-layer--1" />
        <div className="mesh-layer mesh-layer--2" />
        <div className="mesh-layer mesh-layer--3" />
        <div className="mesh-layer mesh-layer--4" />
        <div className="mesh-layer mesh-layer--5" />
      </div>

      {/* Sidebar */}
      <Sidebar
        mobileOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Header */}
        <Header
          onMenuToggle={() => setSidebarOpen(true)}
          onSearchClick={() => setCommandOpen(true)}
        />

        {/* Page content - diagonal gradient background */}
        <main
          className="layout-main-bg flex-1 overflow-y-auto"
          style={{
            background: 'linear-gradient(135deg, var(--surface-body) 0%, var(--surface-card) 50%, var(--surface-body) 100%)',
          }}
        >
          <PageBreadcrumbs />
          <div className="page-content-area p-4 md:p-6">
            {children}
          </div>
        </main>
      </div>

      {/* Command Palette (Cmd+K or /) */}
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />

      {/* Shortcuts cheatsheet (?) */}
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  )
}
