import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import {
  LogOut,
  X,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  Github,
  MessageCircle,
  Heart,
  ListOrdered,
} from '@/components/brand/icons'
import { useAuthStore } from '../../store/authStore'
import { usePermissionStore } from '../../store/permissionStore'
import { useAppearanceStore } from '../../store/useAppearanceStore'
import { useActivePlugins, resolvePluginIcon, type PluginInfo } from '@/lib/plugins'
import { Button } from '@/components/ui/button'
// Separator removed — using gradient dividers instead
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { BrandLogo } from '@/components/brand/BrandLogo'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { applySidebarOrder, useSidebarOrder } from '@/lib/sidebarOrder'
import { SidebarCustomizeDialog } from './SidebarCustomizeDialog'
import {
  filterVisible,
  isNavGroup,
  isNavSection,
  navigation,
  type NavGroup,
  type NavItem,
  type NavSection,
  type NavigationEntry,
} from './navigation'

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
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false)
  const [customizeOpen, setCustomizeOpen] = useState(false)
  const { data: activePlugins } = useActivePlugins()
  const { order, moveTop, moveInGroup, reset: resetOrder, isCustomized } = useSidebarOrder()

  // Build the navigation merged with plugin-contributed entries. Plugins
  // are grouped by ``section_i18n`` (or fall back to a generic "Plugins"
  // section). Entries appear in the order the backend returned them.
  const mergedNavigation = useMemo<NavigationEntry[]>(() => {
    if (!activePlugins || activePlugins.length === 0) return navigation
    const bySection = new Map<string, NavItem[]>()
    for (const p of activePlugins as PluginInfo[]) {
      for (const nav of p.navigation) {
        const section = nav.section_i18n || 'nav.sections.plugins'
        const item: NavItem = {
          name: nav.label_i18n,
          href: nav.path,
          icon: resolvePluginIcon(nav.icon),
          permission: nav.permission ? { resource: nav.permission[0], action: nav.permission[1] } : null,
        }
        const list = bySection.get(section) ?? []
        list.push(item)
        bySection.set(section, list)
      }
    }
    if (bySection.size === 0) return navigation
    const extras: NavigationEntry[] = []
    for (const [section, items] of bySection) {
      extras.push({ type: 'section', name: section } as NavSection)
      extras.push(...items)
    }
    return [...navigation, ...extras]
  }, [activePlugins])

  const { data: panelNameData } = useQuery({
    queryKey: ['panel-name'],
    queryFn: async () => {
      const { data } = await client.get('/settings/panel-name')
      return data as { panel_name: string }
    },
    staleTime: 60_000,
    retry: 1,
  })
  const panelName = panelNameData?.panel_name || 'Remnawave Admin'

  useEffect(() => {
    document.title = panelName
  }, [panelName])

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

  // Пользовательская расстановка ложится на полное меню — до отсева по
  // правам: так пункт, которого этот админ не видит, всё равно держит своё
  // место для тех, кто видит.
  const orderedNavigation = useMemo(
    () => applySidebarOrder(mergedNavigation, order),
    [mergedNavigation, order],
  )

  const visibleNavigation = useMemo(
    () => filterVisible(orderedNavigation, hasPermission),
    [orderedNavigation, hasPermission],
  )

  // Check if group has active child
  const isGroupActive = (group: NavGroup) =>
    group.items.some((item) => location.pathname === item.href)

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className={cn(
        "sidebar-logo-area flex items-center justify-between h-16 px-6 relative",
        "[&::after]:content-[''] [&::after]:absolute [&::after]:bottom-0 [&::after]:inset-x-4 [&::after]:h-px [&::after]:bg-gradient-to-r [&::after]:from-transparent [&::after]:via-[rgba(var(--glow-rgb),0.15)] [&::after]:to-transparent",
        collapsed && "px-0 justify-center"
      )}>
        <Link to="/" onClick={handleNavClick} className={cn(
          "flex items-center gap-2.5 hover:opacity-90 transition-opacity duration-200",
          collapsed && "gap-0"
        )}>
          <BrandLogo className="w-8 h-8 flex-shrink-0" />
          {!collapsed && panelName && (
            <span className="text-sm font-semibold text-white truncate max-w-[140px]">
              {panelName}
            </span>
          )}
        </Link>
        {/* Mobile close button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="md:hidden h-8 w-8"
          aria-label={t('common.close')}
        >
          <X className="w-5 h-5" />
        </Button>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 py-4">
        <nav className={cn("px-3 space-y-0.5", collapsed && "px-2")}>
          {visibleNavigation.map((entry) => {
            // Section header
            if (isNavSection(entry)) {
              if (collapsed) {
                // Thin separator in collapsed mode
                return <div key={entry.name} className="my-2 mx-1 border-t border-[var(--glass-border)]" />
              }
              return (
                <div
                  key={entry.name}
                  role="presentation"
                  aria-hidden="true"
                  className="sidebar-section-title px-3 pt-4 pb-1.5 text-[10px] font-bold uppercase tracking-widest text-dark-400 select-none"
                >
                  {t(entry.name)}
                </div>
              )
            }

            if (isNavGroup(entry)) {
              const groupActive = isGroupActive(entry)
              const isExpanded = expandedGroups.has(entry.name) || groupActive
              // Запретные подпункты отсеяны ещё в filterVisible.
              const visibleItems = entry.items

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
                                "sidebar-nav-item group flex items-center justify-center px-0 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 relative",
                                isActive
                                  ? "text-white bg-[var(--glass-bg-hover)] border border-[var(--glass-border-hover)] shadow-[0_0_15px_-4px_rgba(var(--glow-rgb),0.3)]"
                                  : "text-dark-200 hover:text-white hover:bg-[var(--glass-bg)]"
                              )}
                            >
                              {isActive && (
                                <span
                                  className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full"
                                  style={{ background: 'linear-gradient(180deg, var(--accent-from), var(--accent-to))' }}
                                />
                              )}
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
                        ? "text-white bg-[var(--glass-bg-hover)] border border-[var(--glass-border)]"
                        : "text-dark-200 hover:text-white hover:bg-[var(--glass-bg)]"
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
                    <div className="sidebar-group-items ml-3 pl-3 border-l border-[var(--glass-border)] space-y-0.5">
                      {visibleItems.map((item) => {
                        const isActive = location.pathname === item.href
                        return (
                          <Tooltip key={item.name} delayDuration={0}>
                            <TooltipTrigger asChild>
                              <Link
                                to={item.href}
                                onClick={handleNavClick}
                                className={cn(
                                  "group flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-all duration-200 relative overflow-hidden",
                                  isActive
                                    ? "text-white bg-[var(--glass-bg-hover)] border border-[var(--glass-border-hover)] shadow-[0_0_10px_-4px_rgba(var(--glow-rgb),0.2)]"
                                    : "text-dark-200 hover:text-white hover:bg-[var(--glass-bg)] hover:translate-x-0.5"
                                )}
                              >
                                {isActive && (
                                  <span
                                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-3.5 rounded-r-full"
                                    style={{ background: 'linear-gradient(180deg, var(--accent-from), var(--accent-to))' }}
                                  />
                                )}
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
            // Акцентный пункт отличается от рутинных: янтарная подсветка с
            // тонкой рамкой. Активное состояние важнее — оно перекрывает акцент,
            // иначе непонятно, на какой странице находишься.
            const accent = item.accent && !isActive
            return (
              <Tooltip key={item.name} delayDuration={0}>
                <TooltipTrigger asChild>
                  <Link
                    to={item.href}
                    onClick={handleNavClick}
                    className={cn(
                      "sidebar-nav-item group flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 relative overflow-hidden",
                      isActive
                        ? "text-white bg-[var(--glass-bg-hover)] border border-[var(--glass-border-hover)] shadow-[0_0_15px_-4px_rgba(var(--glow-rgb),0.3)]"
                        : accent
                          ? "text-amber-200 bg-amber-400/10 border border-amber-400/25 hover:bg-amber-400/15 hover:text-amber-100 hover:translate-x-0.5"
                          : "text-dark-200 hover:text-white hover:bg-[var(--glass-bg)] hover:translate-x-0.5",
                      collapsed && "justify-center px-0"
                    )}
                  >
                    {isActive && !collapsed && (
                      <span
                        className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full transition-all duration-300"
                        style={{ background: 'linear-gradient(180deg, var(--accent-from), var(--accent-to))' }}
                      />
                    )}
                    <item.icon
                      className={cn(
                        "w-5 h-5 flex-shrink-0 transition-transform duration-200",
                        !collapsed && "mr-3",
                        isActive ? "text-primary-400" : accent ? "text-amber-300 group-hover:scale-110" : "group-hover:scale-110"
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

      {/* Порядок пунктов и сворачивание. Сворачивание — только на десктопе:
          на телефоне меню и так выезжает поверх экрана. */}
      <div className={cn("flex items-center justify-center gap-1 py-2", collapsed && "flex-col")}>
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setCustomizeOpen(true)}
              className={cn(
                "h-8 w-8 text-dark-300 hover:text-white",
                isCustomized && "text-primary-400",
              )}
              aria-label={t('sidebar.customize.button')}
            >
              <ListOrdered className="w-4 h-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">{t('sidebar.customize.button')}</TooltipContent>
        </Tooltip>
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="hidden md:inline-flex h-8 w-8 text-dark-300 hover:text-white"
              aria-label={t('sidebar.toggleCollapse', 'Toggle sidebar')}
            >
              {collapsed ? <ChevronsRight className="w-4 h-4" /> : <ChevronsLeft className="w-4 h-4" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            {collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
          </TooltipContent>
        </Tooltip>
      </div>

      {/* Project links */}
      {role === 'superadmin' && (
        <>
      <div className="mx-4 h-px bg-gradient-to-r from-transparent via-[rgba(var(--glow-rgb),0.12)] to-transparent" />
      <div className={cn("px-4 py-2 space-y-0.5", collapsed && "px-2")}>
        {collapsed ? (
          <>
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <a
                  href="https://github.com/case211/remnawave-admin"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center py-1.5 text-dark-300 hover:text-white transition-colors"
                >
                  <Github className="w-4 h-4" />
                </a>
              </TooltipTrigger>
              <TooltipContent side="right">GitHub</TooltipContent>
            </Tooltip>
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <a
                  href="https://t.me/remnawave_admin"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center py-1.5 text-dark-300 hover:text-white transition-colors"
                >
                  <MessageCircle className="w-4 h-4" />
                </a>
              </TooltipTrigger>
              <TooltipContent side="right">Telegram</TooltipContent>
            </Tooltip>
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <a
                  href="https://github.com/case211/remnawave-admin#-поддержка"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center py-1.5 text-dark-300 hover:text-primary-400 transition-colors"
                >
                  <Heart className="w-4 h-4" />
                </a>
              </TooltipTrigger>
              <TooltipContent side="right">{t('sidebar.support')}</TooltipContent>
            </Tooltip>
          </>
        ) : (
          <>
            <a
              href="https://github.com/case211/remnawave-admin"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-2 py-1.5 text-xs text-dark-300 hover:text-white transition-colors rounded-md hover:bg-[var(--glass-bg)]"
            >
              <Github className="w-3.5 h-3.5 shrink-0" />
              <span>GitHub</span>
            </a>
            <a
              href="https://t.me/remnawave_admin"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-2 py-1.5 text-xs text-dark-300 hover:text-white transition-colors rounded-md hover:bg-[var(--glass-bg)]"
            >
              <MessageCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{t('sidebar.telegramChat')}</span>
            </a>
            <a
              href="https://github.com/case211/remnawave-admin#-поддержка"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-2 py-1.5 text-xs text-dark-300 hover:text-primary-400 transition-colors rounded-md hover:bg-[var(--glass-bg)]"
            >
              <Heart className="w-3.5 h-3.5 shrink-0" />
              <span>{t('sidebar.support')}</span>
            </a>
          </>
        )}
      </div>
        </>
      )}

      {/* User info */}
      <div className="mx-4 h-px bg-gradient-to-r from-transparent via-[rgba(var(--glow-rgb),0.12)] to-transparent" />
      <div className={cn("p-4", collapsed && "p-2")}>
        <div className={cn("sidebar-user-section flex items-center", collapsed && "justify-center")}>
          <Tooltip delayDuration={0}>
            <TooltipTrigger asChild>
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center bg-[var(--glass-bg-hover)] border border-[var(--glass-border)] shadow-[0_0_15px_-4px_rgba(var(--glow-rgb),0.25)] flex-shrink-0 transition-shadow hover:shadow-[0_0_20px_-4px_rgba(var(--glow-rgb),0.4)]"
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
                <p className="text-xs text-muted-foreground capitalize">{role || t('sidebar.administrator')}</p>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setLogoutConfirmOpen(true)}
                    className="h-9 w-9 text-dark-200 hover:text-red-400"
                    aria-label={t('common.logout', 'Log out')}
                  >
                    <LogOut className="w-5 h-5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t('sidebar.logout')}</TooltipContent>
              </Tooltip>
            </>
          )}
          {collapsed && (
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setLogoutConfirmOpen(true)}
                  className="h-8 w-8 text-dark-200 hover:text-red-400 mt-2"
                  aria-label={t('common.logout', 'Log out')}
                >
                  <LogOut className="w-4 h-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">{t('sidebar.logout')}</TooltipContent>
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
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <div
        role={mobileOpen ? "dialog" : undefined}
        aria-modal={mobileOpen ? true : undefined}
        aria-label={mobileOpen ? "Navigation" : undefined}
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col",
          "glass-heavy animate-fade-in",
          "pt-safe pb-safe pl-[env(safe-area-inset-left)] md:pl-0",
          "[&::after]:content-[''] [&::after]:absolute [&::after]:right-0 [&::after]:inset-y-0 [&::after]:w-px [&::after]:bg-gradient-to-b [&::after]:from-transparent [&::after]:via-[rgba(var(--glow-rgb),0.2)] [&::after]:to-transparent",
          "transform transition-all duration-300 ease-in-out",
          "md:relative md:translate-x-0",
          collapsed ? "w-[4.5rem]" : "w-64",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
      >
        {sidebarContent}
      </div>

      <SidebarCustomizeDialog
        open={customizeOpen}
        onOpenChange={setCustomizeOpen}
        entries={orderedNavigation}
        visible={visibleNavigation}
        onMoveTop={moveTop}
        onMoveInGroup={moveInGroup}
        onReset={resetOrder}
        isCustomized={isCustomized}
      />

      <ConfirmDialog
        open={logoutConfirmOpen}
        onOpenChange={setLogoutConfirmOpen}
        title={t('sidebar.logoutConfirmTitle')}
        description={t('sidebar.logoutConfirmDescription')}
        confirmLabel={t('sidebar.logout')}
        variant="destructive"
        onConfirm={() => {
          setLogoutConfirmOpen(false)
          logout()
        }}
      />
    </>
  )
}
