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
      className="h-16 border-b border-dark-400/10 flex items-center justify-between px-4 md:px-6 animate-fade-in bg-dark-700/95 backdrop-blur-xl"
    >
      {/* Left side: hamburger + search */}
      <div className="flex items-center gap-3 flex-1">
        {/* Mobile menu button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onMenuToggle}
          className="md:hidden"
        >
          <Menu className="w-6 h-6" />
        </Button>

        {/* Search trigger — opens Command Palette */}
        <button
          onClick={onSearchClick}
          className="header-search-bar flex-1 max-w-md hidden sm:flex items-center gap-2 h-10 rounded-md border border-dark-400/20 bg-dark-800 px-3 text-sm text-dark-300 hover:border-dark-400/40 hover:text-dark-200 transition-colors cursor-pointer"
        >
          <Search className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1 text-left">{t('header.searchPlaceholder')}</span>
          <kbd className="hidden lg:inline-flex h-5 select-none items-center gap-1 rounded border border-dark-400/30 bg-dark-700 px-1.5 font-mono text-[10px] font-medium text-dark-300">
            <span className="text-xs">&#x2318;</span>K
          </kbd>
        </button>

        {/* Mobile search icon */}
        <Button
          variant="ghost"
          size="icon"
          className="sm:hidden"
          onClick={onSearchClick}
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
          className="relative"
        >
          <Globe className="w-5 h-5" />
          <span className="sr-only">{i18n.language === 'ru' ? 'EN' : 'RU'}</span>
        </Button>

        {/* Notifications bell with dropdown */}
        <div className="relative" ref={dropdownRef}>
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            onClick={() => setDropdownOpen(!dropdownOpen)}
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
            <div className="absolute right-0 top-full mt-2 w-96 max-w-[calc(100vw-2rem)] bg-dark-700 border border-dark-400/20 rounded-xl shadow-2xl z-50 animate-fade-in overflow-hidden">
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-dark-400/20">
                <h3 className="text-sm font-semibold text-white">{t('notifications.title')}</h3>
                <div className="flex items-center gap-2">
                  {unreadCount > 0 && (
                    <button
                      onClick={() => markAllRead.mutate()}
                      className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-1"
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
                  <div className="py-12 text-center text-dark-300 text-sm">
                    <Bell className="w-8 h-8 mx-auto mb-2 opacity-30" />
                    {t('notifications.noNotifications')}
                  </div>
                ) : (
                  <div className="divide-y divide-dark-400/10">
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
                          'w-full text-left px-4 py-3 hover:bg-dark-600/50 transition-colors border-l-2',
                          n.is_read ? 'border-l-transparent opacity-60' : SEVERITY_STYLES[n.severity] || 'border-l-cyan-500',
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className={cn('text-sm truncate', n.is_read ? 'text-dark-200' : 'text-white font-medium')}>
                              {n.title}
                            </p>
                            {n.body && (
                              <p className="text-xs text-dark-300 mt-0.5 line-clamp-2">{n.body}</p>
                            )}
                          </div>
                          <span className="text-[10px] text-dark-400 whitespace-nowrap mt-0.5">
                            {timeAgo(n.created_at, t)}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </ScrollArea>

              {/* Footer */}
              <div className="px-4 py-2.5 border-t border-dark-400/20">
                <button
                  onClick={() => {
                    navigate('/notifications')
                    setDropdownOpen(false)
                  }}
                  className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors flex items-center gap-1 w-full justify-center"
                >
                  {t('notifications.viewAll')}
                  <ExternalLink className="w-3 h-3" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Status indicator */}
        <Badge variant="default" className="gap-2 px-3 py-1.5">
          <span
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ backgroundColor: 'var(--accent-from)', boxShadow: '0 0 8px rgba(var(--glow-rgb), 0.5)' }}
          />
          <span className="hidden sm:inline text-xs">Online</span>
        </Badge>
      </div>
    </header>
  )
}
