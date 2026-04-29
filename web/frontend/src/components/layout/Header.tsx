import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, Search, Menu, Globe, Check, ExternalLink } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AppearancePanel } from '../AppearancePanel'
import { useTranslation } from 'react-i18next'
import { notificationsApi, type Notification } from '@/api/notifications'
import { cn } from '@/lib/utils'

interface HeaderProps {
  onMenuToggle?: () => void
  onSearchClick?: () => void
}

function timeAgo(dateStr: string | null, t: (key: string, opts?: Record<string, unknown>) => string): string {
  if (!dateStr) return ''
  const now = Date.now()
  const date = new Date(dateStr).getTime()
  const diff = Math.floor((now - date) / 1000)
  if (diff < 60) return t('common.justNow')
  if (diff < 3600) return t('common.minutesAgo', { count: Math.floor(diff / 60) })
  if (diff < 86400) return t('common.hoursAgo', { count: Math.floor(diff / 3600) })
  return t('common.daysAgo', { count: Math.floor(diff / 86400) })
}

const SEVERITY_STYLES: Record<string, string> = {
  info: 'border-l-cyan-500',
  warning: 'border-l-yellow-500',
  critical: 'border-l-red-500',
  success: 'border-l-green-500',
}

export default function Header({ onMenuToggle, onSearchClick }: HeaderProps) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Unread count
  const { data: unreadData } = useQuery({
    queryKey: ['notifications-unread'],
    queryFn: () => notificationsApi.unreadCount(),
    refetchInterval: 30000,
  })
  const unreadCount = unreadData?.count || 0

  // Recent notifications for dropdown
  const { data: recentData } = useQuery({
    queryKey: ['notifications-recent'],
    queryFn: () => notificationsApi.list({ page: 1, per_page: 8 }),
    enabled: dropdownOpen,
  })

  // Mark all read
  const markAllRead = useMutation({
    mutationFn: () => notificationsApi.markRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications-unread'] })
      queryClient.invalidateQueries({ queryKey: ['notifications-recent'] })
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  // Click outside to close
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [dropdownOpen])

  const notifications = recentData?.items || []

  return (
    <header
      className="h-16 flex items-center justify-between px-4 md:px-6 animate-fade-in relative z-30 backdrop-blur-sm pt-safe pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] [&::after]:content-[''] [&::after]:absolute [&::after]:bottom-0 [&::after]:inset-x-0 [&::after]:h-px [&::after]:bg-gradient-to-r [&::after]:from-transparent [&::after]:via-[rgba(var(--glow-rgb),0.12)] [&::after]:to-transparent"
    >
      {/* Left side: hamburger + search */}
      <div className="flex items-center gap-3 flex-1">
        {/* Mobile menu button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onMenuToggle}
          className="md:hidden h-11 w-11"
          aria-label={t('header.menu', 'Open menu')}
        >
          <Menu className="w-6 h-6" />
        </Button>

        {/* Search trigger — opens Command Palette */}
        <button
          onClick={onSearchClick}
          className="header-search-bar flex-1 max-w-md hidden sm:flex items-center gap-2 h-10 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] backdrop-blur-sm px-3.5 text-sm text-muted-foreground hover:border-[var(--glass-border-hover)] hover:text-foreground hover:shadow-[0_0_15px_-5px_rgba(var(--glow-rgb),0.15)] transition-all duration-200 cursor-pointer"
        >
          <Search className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1 text-left">{t('header.searchPlaceholder')}</span>
          <span className="hidden lg:inline-flex items-center gap-1">
            <kbd className="h-5 select-none inline-flex items-center gap-1 rounded-md border border-[var(--glass-border)] bg-white/5 px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
              <span className="text-xs">&#x2318;</span>K
            </kbd>
            <kbd className="h-5 select-none inline-flex items-center rounded-md border border-[var(--glass-border)] bg-white/5 px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
              /
            </kbd>
          </span>
        </button>

        {/* Mobile search icon */}
        <Button
          variant="ghost"
          size="icon"
          className="sm:hidden h-11 w-11"
          onClick={onSearchClick}
          aria-label={t('header.search', 'Search')}
        >
          <Search className="w-5 h-5" />
        </Button>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-2 md:gap-4">
        {/* Appearance settings */}
        <AppearancePanel />

        {/* Language switcher */}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => i18n.changeLanguage(i18n.language === 'ru' ? 'en' : 'ru')}
          className="relative h-11 w-11 md:h-9 md:w-9"
        >
          <Globe className="w-5 h-5" />
          <span className="sr-only">{i18n.language === 'ru' ? 'EN' : 'RU'}</span>
        </Button>

        {/* Notifications bell with dropdown */}
        <div className="relative" ref={dropdownRef}>
          <Button
            variant="ghost"
            size="icon"
            className="relative h-11 w-11 md:h-9 md:w-9"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            aria-label={t('header.notifications', 'Notifications')}
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 flex items-center justify-center text-[10px] font-bold bg-red-500 text-white rounded-full leading-none">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </Button>

          {/* Dropdown */}
          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-2 w-96 max-w-[calc(100vw-2rem)] bg-[var(--glass-bg-solid)] backdrop-blur-[var(--glass-blur-heavy)] border border-[var(--glass-border)] rounded-2xl shadow-2xl z-50 animate-fade-in overflow-hidden shadow-[0_20px_60px_-15px_rgba(0,0,0,0.4)]">
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--glass-border)]">
                <h3 className="text-sm font-semibold" style={{ color: 'var(--text-heading)' }}>{t('notifications.title')}</h3>
                <div className="flex items-center gap-2">
                  {unreadCount > 0 && (
                    <button
                      onClick={() => markAllRead.mutate()}
                      className="text-xs text-primary-400 hover:text-primary-300 transition-colors flex items-center gap-1"
                    >
                      <Check className="w-3 h-3" />
                      {t('notifications.markAllRead')}
                    </button>
                  )}
                </div>
              </div>

              {/* Notification list */}
              <ScrollArea className="max-h-[400px]">
                {notifications.length === 0 ? (
                  <div className="py-12 text-center text-muted-foreground text-sm">
                    <Bell className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    {t('notifications.noNotifications')}
                  </div>
                ) : (
                  <div className="divide-y divide-[var(--glass-border)]">
                    {notifications.map((n: Notification) => (
                      <button
                        key={n.id}
                        onClick={() => {
                          if (n.link) {
                            navigate(n.link)
                            setDropdownOpen(false)
                          }
                        }}
                        className={cn(
                          'w-full text-left px-4 py-3 hover:bg-[var(--glass-bg-hover)] transition-all border-l-2',
                          n.is_read ? 'border-l-transparent opacity-60' : SEVERITY_STYLES[n.severity] || 'border-l-cyan-500',
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className={cn('text-sm truncate', n.is_read ? 'text-muted-foreground' : 'font-medium')} style={{ color: n.is_read ? undefined : 'var(--text-heading)' }}>
                              {n.title}
                            </p>
                            {n.body && (
                              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{n.body}</p>
                            )}
                          </div>
                          <span className="text-[10px] text-muted-foreground/70 whitespace-nowrap mt-0.5">
                            {timeAgo(n.created_at, t)}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </ScrollArea>

              {/* Footer */}
              <div className="px-4 py-2.5 border-t border-[var(--glass-border)]">
                <button
                  onClick={() => {
                    navigate('/notifications')
                    setDropdownOpen(false)
                  }}
                  className="text-xs text-primary-400 hover:text-primary-300 transition-colors flex items-center gap-1 w-full justify-center"
                >
                  {t('notifications.viewAll')}
                  <ExternalLink className="w-3 h-3" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Status indicator */}
        <Badge variant="default" className="gap-2 px-3 py-1.5 rounded-xl">
          <span
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ backgroundColor: 'var(--accent-from)', boxShadow: '0 0 8px rgba(var(--glow-rgb), 0.5)' }}
          />
          <span className="hidden sm:inline text-xs">{t('header.online')}</span>
        </Badge>
      </div>
    </header>
  )
}
