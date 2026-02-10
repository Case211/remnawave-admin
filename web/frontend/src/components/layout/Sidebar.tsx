import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Users,
  Server,
  Activity,
  Globe,
  ShieldAlert,
  Settings,
  LogOut,
  X,
  UserCog,
} from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { usePermissionStore } from '../../store/permissionStore'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

function RemnawaveLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="logoBg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0a1628" />
          <stop offset="100%" stopColor="#0d1f3c" />
        </linearGradient>
        <linearGradient id="logoRing" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#67e8f9" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
        <linearGradient id="logoWave" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="50%" stopColor="#67e8f9" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="31" fill="url(#logoBg)" />
      <circle cx="32" cy="32" r="26" fill="none" stroke="url(#logoRing)" strokeWidth="1.5" opacity="0.8" />
      <path
        d="M12,32 L19,32 L23,22 L28,44 L32,16 L36,46 L40,22 L44,32 L52,32"
        fill="none"
        stroke="url(#logoWave)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard, permission: null },
  { name: 'Users', href: '/users', icon: Users, permission: { resource: 'users', action: 'view' } },
  { name: 'Nodes', href: '/nodes', icon: Server, permission: { resource: 'nodes', action: 'view' } },
  { name: 'Fleet', href: '/fleet', icon: Activity, permission: { resource: 'fleet', action: 'view' } },
  { name: 'Hosts', href: '/hosts', icon: Globe, permission: { resource: 'hosts', action: 'view' } },
  { name: 'Violations', href: '/violations', icon: ShieldAlert, permission: { resource: 'violations', action: 'view' } },
  { name: 'Admins', href: '/admins', icon: UserCog, permission: { resource: 'admins', action: 'view' } },
  { name: 'Settings', href: '/settings', icon: Settings, permission: { resource: 'settings', action: 'view' } },
]

interface SidebarProps {
  mobileOpen?: boolean
  onClose?: () => void
}

export default function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  const location = useLocation()
  const { logout, user } = useAuthStore()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const role = usePermissionStore((s) => s.role)

  const handleNavClick = () => {
    if (onClose) onClose()
  }

  // Filter nav items based on permissions
  const visibleNavigation = navigation.filter((item) => {
    if (!item.permission) return true
    return hasPermission(item.permission.resource, item.permission.action)
  })

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="flex items-center justify-between h-16 px-6 border-b border-sidebar-border">
        <Link to="/" onClick={handleNavClick} className="flex items-center gap-2.5 hover:opacity-90 transition-opacity duration-200">
          <RemnawaveLogo className="w-8 h-8 flex-shrink-0" />
          <span className="text-lg font-display font-bold text-white">Remnawave</span>
        </Link>
        {/* Mobile close button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="md:hidden h-8 w-8"
        >
          <X className="w-5 h-5" />
        </Button>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 py-4">
        <nav className="px-3 space-y-1">
          {visibleNavigation.map((item) => {
            const isActive = location.pathname === item.href
            return (
              <Tooltip key={item.name}>
                <TooltipTrigger asChild>
                  <Link
                    to={item.href}
                    onClick={handleNavClick}
                    className={cn(
                      "group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200",
                      isActive
                        ? "text-white bg-gradient-to-r from-accent-teal/20 to-accent-cyan/10 border-l-[3px] border-l-accent-teal border-r-[3px] border-r-accent-cyan"
                        : "text-dark-200 hover:text-white hover:translate-x-1"
                    )}
                  >
                    <item.icon
                      className={cn(
                        "w-5 h-5 mr-3 flex-shrink-0 transition-transform duration-200",
                        isActive ? "text-primary-400" : "group-hover:scale-110"
                      )}
                    />
                    {item.name}
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right" className="md:hidden">
                  {item.name}
                </TooltipContent>
              </Tooltip>
            )
          })}
        </nav>
      </ScrollArea>

      {/* User info */}
      <Separator className="bg-sidebar-border" />
      <div className="p-4">
        <div className="flex items-center">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center bg-gradient-to-br from-accent-teal/30 to-accent-cyan/20"
          >
            <span className="text-sm font-medium text-primary-400">
              {user?.username?.charAt(0).toUpperCase() || 'A'}
            </span>
          </div>
          <div className="ml-3 flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">
              {user?.username || 'Admin'}
            </p>
            <p className="text-xs text-muted-foreground capitalize">{role || 'Administrator'}</p>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={logout}
                className="h-9 w-9 text-dark-200 hover:text-red-400"
              >
                <LogOut className="w-5 h-5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Logout</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  )

  return (
    <>
      {/* Mobile overlay backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col w-64",
          "bg-sidebar border-r border-sidebar-border animate-fade-in",
          "transform transition-transform duration-300 ease-in-out",
          "md:relative md:translate-x-0 md:transition-none",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {sidebarContent}
      </div>
    </>
  )
}
