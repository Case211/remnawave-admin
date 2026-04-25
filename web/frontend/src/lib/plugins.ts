/**
 * Frontend plugin registry — fetches the list of plugins registered with the
 * backend and exposes helpers used by Sidebar.tsx and App.tsx to render
 * plugin-contributed navigation and routes.
 *
 * Plugins themselves still ship their UI pages inside the open-source repo
 * (under ``src/plugins/<id>/``); this module only orchestrates which pages
 * appear in navigation and at what route, and lets the UI react to
 * ``license_state`` (e.g. show a "renew license" banner via 402 responses).
 */
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Bug,
  Globe,
  HardDrive,
  Heart,
  Key,
  LayoutDashboard,
  Mail,
  Search,
  Server,
  Settings,
  Shield,
  ShieldAlert,
  ShieldBan,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Terminal,
  Users,
  UsersRound,
  Wrench,
  Zap,
} from 'lucide-react'
import client from '@/api/client'

export type LicenseState = 'valid' | 'expired' | 'missing' | 'not_required'

export interface PluginNavEntry {
  path: string
  label_i18n: string
  icon: string
  permission?: [string, string] | null
  section_i18n?: string | null
}

export interface PluginInfo {
  id: string
  name: string
  version: string
  license_state: LicenseState
  api_prefix: string
  navigation: PluginNavEntry[]
}

/**
 * Map of icon names a plugin manifest may reference to actual lucide
 * components. Keep this list small and explicit — we don't want to bundle
 * the entire lucide library just to support arbitrary plugin icons.
 *
 * To add a new icon: import it above, then add it here.
 */
const ICON_MAP: Record<string, typeof LayoutDashboard> = {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Bug,
  Globe,
  HardDrive,
  Heart,
  Key,
  LayoutDashboard,
  Mail,
  Search,
  Server,
  Settings,
  Shield,
  ShieldAlert,
  ShieldBan,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Terminal,
  Users,
  UsersRound,
  Wrench,
  Zap,
}

export function resolvePluginIcon(name: string): typeof LayoutDashboard {
  return ICON_MAP[name] ?? Sparkles
}

export function isPluginUsable(p: PluginInfo): boolean {
  return p.license_state === 'valid' || p.license_state === 'not_required'
}

/**
 * Hook returning the list of plugins registered on the backend. The query
 * is cached for the session — plugins only change on container restart, so
 * staleTime is generous and refetch on focus is disabled.
 */
export function useActivePlugins() {
  return useQuery({
    queryKey: ['active-plugins'],
    queryFn: async () => {
      const { data } = await client.get<PluginInfo[]>('/plugins')
      return Array.isArray(data) ? data : []
    },
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  })
}
