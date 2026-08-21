import {
  LayoutDashboard,
  Users,
  Server,
  Activity,
  Globe,
  ShieldAlert,
  Settings,
  UserCog,
  ClipboardList,
  Terminal,
  BarChart3,
  Zap,
  BellRing,
  Mail,
  HardDrive,
  Key,
  Bot,
  ShieldCheck,
  UsersRound,
  Ticket,
  Megaphone,
  Share2,
  ShieldBan,
  Package,
  Wallet,
  FileText,
  Boxes,
  Network,
  type LucideIcon,
} from '@/components/brand/icons'

export interface NavItem {
  type?: 'item'
  name: string
  href: string
  icon: LucideIcon
  permission: { resource: string; action: string } | null
}

export interface NavGroup {
  type: 'group'
  name: string
  icon: LucideIcon
  items: NavItem[]
}

export interface NavSection {
  type: 'section'
  name: string
}

export type NavigationEntry = NavItem | NavGroup | NavSection

export function isNavGroup(entry: NavigationEntry): entry is NavGroup {
  return entry.type === 'group'
}

export function isNavSection(entry: NavigationEntry): entry is NavSection {
  return entry.type === 'section'
}

/**
 * Пункты бокового меню в порядке по умолчанию.
 *
 * Список плоский: заголовок секции — такая же запись, как пункт, и «владеет»
 * всем, что идёт за ним до следующего заголовка. Это позволяет собирать меню
 * из кусков (пункты плагинов дописываются в конец) и хранить пользовательский
 * порядок как обычный массив ключей — см. lib/sidebarOrder.
 */
export const navigation: NavigationEntry[] = [
  // Overview — «смотрю на систему»
  { type: 'section', name: 'nav.sections.overview' },
  { name: 'nav.dashboard', href: '/', icon: LayoutDashboard, permission: null },
  { name: 'nav.analytics', href: '/analytics', icon: BarChart3, permission: { resource: 'analytics', action: 'view' } },
  // Плагины стоят здесь, а не в «Администрировании»: закопанные в подменю,
  // они не попадались на глаза владельцам панелей — часть узнавала об их
  // существовании только из чата.
  { name: 'nav.adminPlugins', href: '/admin/plugins', icon: Package, permission: { resource: 'plugins', action: 'view' } },
  // People — «управляю людьми»
  { type: 'section', name: 'nav.sections.people' },
  { name: 'nav.users', href: '/users', icon: Users, permission: { resource: 'users', action: 'view' } },
  { name: 'nav.squads', href: '/squads', icon: UsersRound, permission: { resource: 'users', action: 'view' } },
  // Infrastructure — «управляю железом и конфигурацией»
  { type: 'section', name: 'nav.sections.infrastructure' },
  { name: 'nav.nodes', href: '/nodes', icon: Server, permission: { resource: 'nodes', action: 'view' } },
  { name: 'nav.fleet', href: '/fleet', icon: Activity, permission: { resource: 'fleet', action: 'view' } },
  { name: 'nav.hosts', href: '/hosts', icon: Globe, permission: { resource: 'hosts', action: 'view' } },
  { name: 'nav.dns', href: '/dns', icon: Network, permission: { resource: 'dns', action: 'view' } },
  { name: 'nav.bscheck', href: '/bscheck', icon: ShieldCheck, permission: { resource: 'bscheck', action: 'view' } },
  { name: 'nav.finance', href: '/finance', icon: Wallet, permission: { resource: 'finance', action: 'view' } },
  { name: 'nav.resources', href: '/resources', icon: Boxes, permission: { resource: 'resources', action: 'view' } },
  // Security — «защищаюсь»
  { type: 'section', name: 'nav.sections.security' },
  { name: 'nav.violations', href: '/violations', icon: ShieldAlert, permission: { resource: 'violations', action: 'view' } },
  { name: 'nav.blocking', href: '/blocking', icon: ShieldBan, permission: { resource: 'blocked_ips', action: 'view' } },
  { name: 'nav.reports', href: '/reports', icon: FileText, permission: { resource: 'reports', action: 'view' } },
  // Services — «настраиваю реакции и каналы»
  { type: 'section', name: 'nav.sections.services' },
  { name: 'nav.automations', href: '/automations', icon: Zap, permission: { resource: 'automation', action: 'view' } },
  { name: 'nav.notifications', href: '/notifications', icon: BellRing, permission: { resource: 'notifications', action: 'view' } },
  { name: 'nav.mailServer', href: '/mailserver', icon: Mail, permission: { resource: 'mailserver', action: 'view' } },
  { name: 'nav.apiKeys', href: '/api-keys', icon: Key, permission: { resource: 'api_keys', action: 'view' } },
  // Bedolaga
  { type: 'section', name: 'nav.sections.bedolaga' },
  {
    type: 'group',
    name: 'nav.bedolagaGroup',
    icon: Bot,
    items: [
      { name: 'nav.bedolaga.dashboard', href: '/bedolaga', icon: BarChart3, permission: { resource: 'bedolaga', action: 'view' } },
      { name: 'nav.bedolaga.customers', href: '/bedolaga/customers', icon: Users, permission: { resource: 'bedolaga_customers', action: 'view' } },
      { name: 'nav.bedolaga.promo', href: '/bedolaga/promo', icon: Ticket, permission: { resource: 'bedolaga_promo', action: 'view' } },
      { name: 'nav.bedolaga.marketing', href: '/bedolaga/marketing', icon: Megaphone, permission: { resource: 'bedolaga_marketing', action: 'view' } },
      { name: 'nav.bedolaga.referrals', href: '/bedolaga/referrals', icon: Share2, permission: { resource: 'bedolaga', action: 'view' } },
    ],
  },
  // Administration
  { type: 'section', name: 'nav.sections.admin' },
  {
    type: 'group',
    name: 'nav.administration',
    icon: ShieldCheck,
    items: [
      { name: 'nav.admins', href: '/admins', icon: UserCog, permission: { resource: 'admins', action: 'view' } },
      { name: 'nav.audit', href: '/audit', icon: ClipboardList, permission: { resource: 'audit', action: 'view' } },
      { name: 'nav.logs', href: '/logs', icon: Terminal, permission: { resource: 'logs', action: 'view' } },
      { name: 'nav.backups', href: '/backups', icon: HardDrive, permission: { resource: 'backups', action: 'view' } },
    ],
  },
  { name: 'nav.settings', href: '/settings', icon: Settings, permission: { resource: 'settings', action: 'view' } },
]

type PermissionCheck = (resource: string, action: string) => boolean

/** Виден ли пункт текущему админу (пункты без permission видны всем). */
export function isItemVisible(item: NavItem, hasPermission: PermissionCheck): boolean {
  if (!item.permission) return true
  return hasPermission(item.permission.resource, item.permission.action)
}

/**
 * Оставить только то, что админ имеет право видеть.
 *
 * Группа возвращается уже без запретных подпунктов, а заголовок секции живёт
 * ровно до тех пор, пока за ним остаётся хотя бы один видимый пункт: иначе в
 * меню висели бы пустые подписи.
 */
export function filterVisible(
  entries: NavigationEntry[],
  hasPermission: PermissionCheck,
): NavigationEntry[] {
  return entries
    .filter((entry, idx) => {
      if (isNavSection(entry)) {
        for (let i = idx + 1; i < entries.length; i++) {
          const next = entries[i]
          if (isNavSection(next)) break
          if (isNavGroup(next) && next.items.some((item) => isItemVisible(item, hasPermission))) return true
          if (!isNavGroup(next) && isItemVisible(next as NavItem, hasPermission)) return true
        }
        return false
      }
      if (isNavGroup(entry)) {
        return entry.items.some((item) => isItemVisible(item, hasPermission))
      }
      return isItemVisible(entry as NavItem, hasPermission)
    })
    .map((entry) =>
      isNavGroup(entry)
        ? { ...entry, items: entry.items.filter((item) => isItemVisible(item, hasPermission)) }
        : entry,
    )
}
