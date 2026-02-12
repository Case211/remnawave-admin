import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  Users,
  Server,
  Globe,
  ShieldAlert,
  Settings,
  UserCog,
  Ship,
  UserPlus,
  Search,
  ClipboardList,
  Terminal,
  BarChart3,
} from 'lucide-react'
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
} from '@/components/ui/command'
import client from '@/api/client'

interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [search, setSearch] = useState('')

  // Reset search when closing
  useEffect(() => {
    if (!open) setSearch('')
  }, [open])

  const runCommand = useCallback(
    (command: () => void) => {
      onOpenChange(false)
      command()
    },
    [onOpenChange],
  )

  // Search users when query is long enough
  const { data: userResults } = useQuery({
    queryKey: ['command-search-users', search],
    queryFn: async () => {
      const { data } = await client.get('/users', {
        params: { search, page: 1, per_page: 5 },
      })
      return data.items as { uuid: string; username: string | null; email: string | null; status: string }[]
    },
    enabled: open && search.length >= 2,
    staleTime: 10_000,
  })

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput
        placeholder={t('commandPalette.placeholder')}
        value={search}
        onValueChange={setSearch}
      />
      <CommandList>
        <CommandEmpty>{t('commandPalette.noResults')}</CommandEmpty>

        {/* User search results */}
        {userResults && userResults.length > 0 && (
          <CommandGroup heading={t('commandPalette.users')}>
            {userResults.map((user) => (
              <CommandItem
                key={user.uuid}
                value={`user-${user.username || user.email || user.uuid}`}
                onSelect={() => runCommand(() => navigate(`/users/${user.uuid}`))}
              >
                <Users className="mr-2 h-4 w-4" />
                <span>{user.username || user.email || user.uuid.slice(0, 8)}</span>
                <span className="ml-auto text-xs text-dark-300">{user.status}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {/* Navigation */}
        <CommandGroup heading={t('commandPalette.navigation')}>
          <CommandItem
            value="dashboard дашборд"
            onSelect={() => runCommand(() => navigate('/'))}
          >
            <LayoutDashboard className="mr-2 h-4 w-4" />
            {t('nav.dashboard')}
          </CommandItem>
          <CommandItem
            value="users пользователи"
            onSelect={() => runCommand(() => navigate('/users'))}
          >
            <Users className="mr-2 h-4 w-4" />
            {t('nav.users')}
          </CommandItem>
          <CommandItem
            value="nodes ноды серверы"
            onSelect={() => runCommand(() => navigate('/nodes'))}
          >
            <Server className="mr-2 h-4 w-4" />
            {t('nav.nodes')}
          </CommandItem>
          <CommandItem
            value="fleet флот"
            onSelect={() => runCommand(() => navigate('/fleet'))}
          >
            <Ship className="mr-2 h-4 w-4" />
            {t('nav.fleet')}
          </CommandItem>
          <CommandItem
            value="hosts хосты"
            onSelect={() => runCommand(() => navigate('/hosts'))}
          >
            <Globe className="mr-2 h-4 w-4" />
            {t('nav.hosts')}
          </CommandItem>
          <CommandItem
            value="violations нарушения"
            onSelect={() => runCommand(() => navigate('/violations'))}
          >
            <ShieldAlert className="mr-2 h-4 w-4" />
            {t('nav.violations')}
          </CommandItem>
          <CommandItem
            value="analytics аналитика гео карта тренды"
            onSelect={() => runCommand(() => navigate('/analytics'))}
          >
            <BarChart3 className="mr-2 h-4 w-4" />
            {t('nav.analytics')}
          </CommandItem>
          <CommandItem
            value="settings настройки"
            onSelect={() => runCommand(() => navigate('/settings'))}
          >
            <Settings className="mr-2 h-4 w-4" />
            {t('nav.settings')}
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        {/* Administration */}
        <CommandGroup heading={t('commandPalette.administration')}>
          <CommandItem
            value="admins администраторы роли"
            onSelect={() => runCommand(() => navigate('/admins'))}
          >
            <UserCog className="mr-2 h-4 w-4" />
            {t('nav.admins')}
          </CommandItem>
          <CommandItem
            value="audit аудит журнал лог"
            onSelect={() => runCommand(() => navigate('/audit'))}
          >
            <ClipboardList className="mr-2 h-4 w-4" />
            {t('nav.audit')}
          </CommandItem>
          <CommandItem
            value="logs логи системные"
            onSelect={() => runCommand(() => navigate('/logs'))}
          >
            <Terminal className="mr-2 h-4 w-4" />
            {t('nav.logs')}
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        {/* Quick actions */}
        <CommandGroup heading={t('commandPalette.quickActions')}>
          <CommandItem
            value="create user создать пользователя"
            onSelect={() => runCommand(() => navigate('/users?action=create'))}
          >
            <UserPlus className="mr-2 h-4 w-4" />
            {t('commandPalette.createUser')}
          </CommandItem>
          <CommandItem
            value="search users поиск пользователей"
            onSelect={() => runCommand(() => navigate('/users'))}
          >
            <Search className="mr-2 h-4 w-4" />
            {t('commandPalette.searchUsers')}
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
