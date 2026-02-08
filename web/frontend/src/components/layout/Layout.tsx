import { ReactNode, useState } from 'react'
import Sidebar from './Sidebar'
import Header from './Header'
import { useRealtimeUpdates } from '../../store/useWebSocket'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Connect WebSocket for real-time updates (nodes, users, violations)
  useRealtimeUpdates()

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
        <Header onMenuToggle={() => setSidebarOpen(true)} />

        {/* Page content - diagonal gradient background */}
        <main
          className="flex-1 overflow-y-auto p-4 md:p-6"
          style={{
            background: 'linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%)',
          }}
        >
          {children}
        </main>
      </div>
    </div>
  )
}
