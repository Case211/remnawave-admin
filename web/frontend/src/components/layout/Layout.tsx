import { ReactNode, useState, useEffect, useCallback } from 'react'
import Sidebar from './Sidebar'
import Header from './Header'
import PageBreadcrumbs from './PageBreadcrumbs'
import { CommandPalette } from '../CommandPalette'
import { useRealtimeUpdates } from '../../store/useWebSocket'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)

  // Connect WebSocket for real-time updates (nodes, users, violations)
  useRealtimeUpdates()

  // Global keyboard shortcut: Cmd/Ctrl + K → open command palette
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setCommandOpen((prev) => !prev)
      }
    },
    [],
  )

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div className="flex h-screen overflow-hidden bg-dark-800">
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
          className="flex-1 overflow-y-auto"
          style={{
            background: 'linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%)',
          }}
        >
          <PageBreadcrumbs />
          <div className="page-content-area p-4 md:p-6">
            {children}
          </div>
        </main>
      </div>

      {/* Command Palette (Cmd+K) */}
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  )
}
