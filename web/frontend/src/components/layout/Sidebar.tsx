import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  ClipboardList,
  Terminal,
  BarChart3,
  Zap,
  BellRing,
  Mail,
  ShieldCheck,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { usePermissionStore } from '../../store/permissionStore'
import { useAppearanceStore } from '../../store/useAppearanceStore'
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
          <stop offset="0%" style={{ stopColor: 'var(--accent-to-light)' }} />
          <stop offset="100%" style={{ stopColor: 'var(--accent-to)' }} />
        </linearGradient>
        <linearGradient id="logoWave" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style={{ stopColor: 'var(--accent-to-light)' }} />
          <stop offset="50%" style={{ stopColor: 'var(--accent-from-light)' }} />
          <stop offset="100%" style={{ stopColor: 'var(--accent-from)' }} />
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

interface NavItem {
  type?: 'item'
  name: string
  href: string
  icon: typeof LayoutDashboard
  permission: { resource: string; action: string } | null
}

interface NavGroup {
  type: 'group'
  name: string
  icon: typeof LayoutDashboard
  items: NavItem[]
}

type NavigationEntry = NavItem | NavGroup

function isNavGroup(entry: NavigationEntry): entry is NavGroup {
  return entry.type === 'group'
}

const navigation: NavigationEntry[] = [
  { name: 'nav.dashboard', href: '/', icon: LayoutDashboard, permission: null },
  { name: 'nav.users', href: '/users', icon: Users, permission: { resource: 'users', action: 'view' } },
  { name: 'nav.nodes', href: '/nodes', icon: Server, permission: { resource: 'nodes', action: 'view' } },
  { name: 'nav.fleet', href: '/fleet', icon: Activity, permission: { resource: 'fleet', action: 'view' } },
  { name: 'nav.hosts', href: '/hosts', icon: Globe, permission: { resource: 'hosts', action: 'view' } },
  { name: 'nav.violations', href: '/violations', icon: ShieldAlert, permission: { resource: 'violations', action: 'view' } },
  { name: 'nav.automations', href: '/automations', icon: Zap, permission: { resource: 'automation', action: 'view' } },
  { name: 'nav.notifications', href: '/notifications', icon: BellRing, permission: { resource: 'notifications', action: 'view' } },
  { name: 'nav.mailServer', href: '/mailserver', icon: Mail, permission: { resource: 'mailserver', action: 'view' } },
  { name: 'nav.analytics', href: '/analytics', icon: BarChart3, permission: { resource: 'analytics', action: 'view' } },
  {
    type: 'group',
    name: 'nav.administration',
    icon: ShieldCheck,
    items: [
      { name: 'nav.admins', href: '/admins', icon: UserCog, permission: { resource: 'admins', action: 'view' } },
      { name: 'nav.audit', href: '/audit', icon: ClipboardList, permission: { resource: 'audit', action: 'view' } },
      { name: 'nav.logs', href: '/logs', icon: Terminal, permission: { resource: 'logs', action: 'view' } },
    ],
  },
  { name: 'nav.settings', href: '/settings', icon: Settings, permission: { resource: 'settings', action: 'view' } },
]

interface SidebarProps {
  mobileOpen?: boolean
  onClose?: () => void
}

export default function Sidebar({ mobileOpen, onClose }: SidebarProps) {
  const { t } = useTranslation()
  const location = useLocation()
  const { logout, user } = useAuthStore()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const role = usePermissionStore((s) => s.role)
  const collapsed = useAppearanceStore((s) => s.sidebarCollapsed)
  const toggleSidebar = useAppearanceStore((s) => s.toggleSidebar)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())

  const handleNavClick = () => {
    if (onClose) onClose()
  }

  const toggleGroup = (name: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  // Check if a nav item is visible based on permissions
  const isItemVisible = (item: NavItem) => {
    if (!item.permission) return true
    return hasPermission(item.permission.resource, item.permission.action)
  }

  // Filter navigation entries based on permissions
  const visibleNavigation = navigation.filter((entry) => {
    if (isNavGroup(entry)) {
      return entry.items.some(isItemVisible)
    }
    return isItemVisible(entry)
  })

  // Check if group has active child
  const isGroupActive = (group: NavGroup) =>
    group.items.some((item) => location.pathname === item.href)

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className={cn(
        "sidebar-logo-area flex items-center justify-between h-16 px-6 border-b border-sidebar-border",
        collapsed && "px-0 justify-center"
      )}>
        <Link to="/" onClick={handleNavClick} className={cn(
          "flex items-center gap-2.5 hover:opacity-90 transition-opacity duration-200",
          collapsed && "gap-0"
        )}>
          <RemnawaveLogo className="w-8 h-8 flex-shrink-0" />
          {!collapsed && (
            <span className="sidebar-brand-text text-lg font-display font-bold text-white">Remnawave</span>
          )}
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
        <nav className={cn("px-3 space-y-1", collapsed && "px-2")}>
          {visibleNavigation.map((entry) => {
            if (isNavGroup(entry)) {
              const groupActive = isGroupActive(entry)
              const isExpanded = expandedGroups.has(entry.name) || groupActive
              const visibleItems = entry.items.filter(isItemVisible)

              // When collapsed, show group items as flat icons
              if (collapsed) {
                return (
                  <div key={entry.name} className="space-y-0.5">
                    {visibleItems.map((item) => {
                      const isActive = location.pathname === item.href
                      return (
                        <Tooltip key={item.name} delayDuration={0}>
                          <TooltipTrigger asChild>
                            <Link
                              to={item.href}
                              onClick={handleNavClick}
                              className={cn(
                                "sidebar-nav-item group flex items-center justify-center px-0 py-2.5 text-sm font-medium rounded-lg transition-all duration-200",
                                isActive
                                  ? "text-white bg-primary/15"
                                  : "text-dark-200 hover:text-white"
                              )}
                            >
                              <item.icon
                                className={cn(
                                  "w-5 h-5 flex-shrink-0 transition-transform duration-200",
                                  isActive ? "text-primary-400" : "group-hover:scale-110"
                                )}
                              />
                            </Link>
                          </TooltipTrigger>
                          <TooltipContent side="right">
                            {t(item.name)}
                          </TooltipContent>
                        </Tooltip>
                      )
                    })}
                  </div>
                )
              }

              return (
                <div key={entry.name} className="space-y-0.5">
                  {/* Group header */}
                  <button
                    onClick={() => toggleGroup(entry.name)}
                    className={cn(
                      "sidebar-nav-item group flex items-center w-full px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200",
                      groupActive
                        ? "text-white bg-dark-700/50"
                        : "text-dark-200 hover:text-white"
                    )}
                  >
                    <entry.icon
                      className={cn(
                        "w-5 h-5 mr-3 flex-shrink-0 transition-transform duration-200",
                        groupActive ? "text-primary-400" : "group-hover:scale-110"
                      )}
                    />
                    <span className="sidebar-nav-text flex-1 text-left">{t(entry.name)}</span>
                    <ChevronDown
                      className={cn(
                        "sidebar-group-chevron w-4 h-4 text-dark-300 transition-transform duration-200",
                        isExpanded && "rotate-180"
                      )}
                    />
                  </button>

                  {/* Group items */}
                  <div
                    className={cn(
                      "overflow-hidden transition-all duration-200",
                      isExpanded ? "max-h-96 opacity-100" : "max-h-0 opacity-0"
                    )}
                  >
                    <div className="sidebar-group-items ml-3 pl-3 border-l border-dark-500/30 space-y-0.5">
                      {visibleItems.map((item) => {
                        const isActive = location.pathname === item.href
                        return (
                          <Tooltip key={item.name} delayDuration={0}>
                            <TooltipTrigger asChild>
                              <Link
                                to={item.href}
                                onClick={handleNavClick}
                                className={cn(
                                  "group flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-all duration-200",
                                  isActive
                                    ? "text-white bg-primary/15 border-l-[3px] border-l-primary border-r-[3px] border-r-primary/50"
                                    : "text-dark-200 hover:text-white hover:translate-x-1"
                                )}
                              >
                                <item.icon
                                  className={cn(
                                    "w-4 h-4 mr-2.5 flex-shrink-0 transition-transform duration-200",
                                    isActive ? "text-primary-400" : "group-hover:scale-110"
                                  )}
                                />
                                <span className="sidebar-nav-text">{t(item.name)}</span>
                              </Link>
                            </TooltipTrigger>
                            <TooltipContent side="right">
                              {t(item.name)}
                            </TooltipContent>
                          </Tooltip>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )
            }

            const item = entry as NavItem
            const isActive = location.pathname === item.href
            return (
              <Tooltip key={item.name} delayDuration={0}>
                <TooltipTrigger asChild>
                  <Link
                    to={item.href}
                    onClick={handleNavClick}
                    className={cn(
                      "sidebar-nav-item group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200",
                      isActive
                        ? "text-white bg-primary/15 border-l-[3px] border-l-primary border-r-[3px] border-r-primary/50"
                        : "text-dark-200 hover:text-white hover:translate-x-1",
                      collapsed && "justify-center px-0"
                    )}
                  >
                    <item.icon
                      className={cn(
                        "w-5 h-5 flex-shrink-0 transition-transform duration-200",
                        !collapsed && "mr-3",
                        isActive ? "text-primary-400" : "group-hover:scale-110"
                      )}
                    />
                    {!collapsed && <span className="sidebar-nav-text">{t(item.name)}</span>}
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right" className={cn(!collapsed && "md:hidden")}>
                  {t(item.name)}
                </TooltipContent>
              </Tooltip>
            )
          })}
        </nav>
      </ScrollArea>

      {/* Collapse toggle — desktop only */}
      <div className="hidden md:flex justify-center py-2 border-t border-sidebar-border">
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="h-8 w-8 text-dark-300 hover:text-white"
            >
              {collapsed ? <ChevronsRight className="w-4 h-4" /> : <ChevronsLeft className="w-4 h-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* User info */}
      <Separator className="bg-sidebar-border" />
      <div className={cn("p-4", collapsed && "p-2")}>
        <div className={cn("sidebar-user-section flex items-center", collapsed && "justify-center")}>
          <Tooltip delayDuration={0}>
            <TooltipTrigger asChild>
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center bg-primary/20 flex-shrink-0"
              >
                <span className="text-sm font-medium text-primary-400">
                  {user?.username?.charAt(0).toUpperCase() || 'A'}
                </span>
              </div>
            </TooltipTrigger>
            {collapsed && (
              <TooltipContent side="right">
                {user?.username || 'Admin'}
              </TooltipContent>
            )}
          </Tooltip>
          {!collapsed && (
            <>
              <div className="sidebar-user-info ml-3 flex-1 min-w-0">
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
            </>
          )}
          {collapsed && (
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={logout}
                  className="h-8 w-8 text-dark-200 hover:text-red-400 mt-2"
                >
                  <LogOut className="w-4 h-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Logout</TooltipContent>
            </Tooltip>
          )}
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
          "fixed inset-y-0 left-0 z-50 flex flex-col",
          "bg-sidebar border-r border-sidebar-border animate-fade-in",
          "transform transition-all duration-300 ease-in-out",
          "md:relative md:translate-x-0",
          collapsed ? "w-[4.5rem]" : "w-64",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
      >
        {sidebarContent}
      </div>
    </>
  )
}
