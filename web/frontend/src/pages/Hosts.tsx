import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  HiRefresh,
  HiGlobe,
  HiDotsVertical,
  HiPencil,
  HiTrash,
  HiPlay,
  HiStop,
  HiStatusOnline,
  HiStatusOffline,
  HiLockClosed,
  HiShieldCheck,
} from 'react-icons/hi'
import client from '../api/client'

// Types matching backend HostListItem
interface Host {
  uuid: string
  remark: string
  address: string
  port: number
  is_disabled: boolean
  inbound_uuid: string | null
  sni: string | null
  host: string | null
  path: string | null
  security: string | null
  alpn: string | null
  fingerprint: string | null
}

interface HostListResponse {
  items: Host[]
  total: number
}

// API functions
const fetchHosts = async (): Promise<Host[]> => {
  const { data } = await client.get('/hosts')
  return data.items || data
}

function getSecurityLabel(security: string | null): string {
  if (!security) return '-'
  const labels: Record<string, string> = {
    'tls': 'TLS',
    'reality': 'Reality',
    'none': 'Без шифрования',
    'xtls': 'XTLS',
  }
  return labels[security] || security
}

function getSecurityColor(security: string | null): string {
  if (!security || security === 'none') return 'text-red-400'
  if (security === 'reality') return 'text-green-400'
  if (security === 'tls' || security === 'xtls') return 'text-blue-400'
  return 'text-dark-200'
}

// Host card component
function HostCard({
  host,
  onEnable,
  onDisable,
  onDelete,
}: {
  host: Host
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className={`card relative ${host.is_disabled ? 'opacity-60' : ''}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`p-2.5 rounded-lg ${host.is_disabled ? 'bg-gray-500/10' : 'bg-green-500/10'}`}>
            {host.is_disabled ? (
              <HiStatusOffline className="w-5 h-5 text-dark-200" />
            ) : (
              <HiStatusOnline className="w-5 h-5 text-green-400" />
            )}
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-white truncate">{host.remark || 'Без имени'}</h3>
            <p className="text-sm text-dark-200 flex items-center gap-1 truncate">
              <HiGlobe className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate">{host.address}:{host.port}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={host.is_disabled ? 'badge-gray' : 'badge-success'}>
            {host.is_disabled ? 'Откл.' : 'Активен'}
          </span>

          {/* Actions menu */}
          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="btn-ghost p-1.5 rounded"
            >
              <HiDotsVertical className="w-4 h-4" />
            </button>

            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="dropdown-menu">
                  <div className="border-t border-dark-400/20 my-1" />
                  {host.is_disabled ? (
                    <button
                      onClick={() => { onEnable(); setMenuOpen(false) }}
                      className="w-full px-3 py-2 text-left text-sm text-green-400 hover:bg-dark-600 flex items-center gap-2"
                    >
                      <HiPlay className="w-4 h-4" /> Включить
                    </button>
                  ) : (
                    <button
                      onClick={() => { onDisable(); setMenuOpen(false) }}
                      className="w-full px-3 py-2 text-left text-sm text-yellow-400 hover:bg-dark-600 flex items-center gap-2"
                    >
                      <HiStop className="w-4 h-4" /> Отключить
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (confirm('Удалить хост?')) onDelete()
                      setMenuOpen(false)
                    }}
                    className="w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-dark-600 flex items-center gap-2"
                  >
                    <HiTrash className="w-4 h-4" /> Удалить
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Details */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="bg-dark-800/50 rounded-lg p-2">
          <span className="text-dark-200 text-xs">Безопасность</span>
          <p className={`font-medium ${getSecurityColor(host.security)}`}>
            {host.security === 'reality' && <HiShieldCheck className="w-3.5 h-3.5 inline mr-1" />}
            {host.security === 'tls' && <HiLockClosed className="w-3.5 h-3.5 inline mr-1" />}
            {getSecurityLabel(host.security)}
          </p>
        </div>
        <div className="bg-dark-800/50 rounded-lg p-2">
          <span className="text-dark-200 text-xs">SNI</span>
          <p className="font-medium text-white truncate">{host.sni || '-'}</p>
        </div>
        {host.host && (
          <div className="bg-dark-800/50 rounded-lg p-2">
            <span className="text-dark-200 text-xs">Host</span>
            <p className="font-medium text-white truncate">{host.host}</p>
          </div>
        )}
        {host.path && (
          <div className="bg-dark-800/50 rounded-lg p-2">
            <span className="text-dark-200 text-xs">Path</span>
            <p className="font-medium text-white truncate font-mono text-xs">{host.path}</p>
          </div>
        )}
        {host.alpn && (
          <div className="bg-dark-800/50 rounded-lg p-2">
            <span className="text-dark-200 text-xs">ALPN</span>
            <p className="font-medium text-white truncate">{host.alpn}</p>
          </div>
        )}
        {host.fingerprint && (
          <div className="bg-dark-800/50 rounded-lg p-2">
            <span className="text-dark-200 text-xs">Fingerprint</span>
            <p className="font-medium text-white truncate">{host.fingerprint}</p>
          </div>
        )}
      </div>
    </div>
  )
}

// Loading skeleton
function HostSkeleton() {
  return (
    <div className="card animate-fade-in">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-dark-700 rounded-lg" />
          <div>
            <div className="h-4 w-32 bg-dark-700 rounded mb-2" />
            <div className="h-3 w-24 bg-dark-700 rounded" />
          </div>
        </div>
        <div className="h-5 w-16 bg-dark-700 rounded" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="h-12 bg-dark-700 rounded-lg" />
        <div className="h-12 bg-dark-700 rounded-lg" />
      </div>
    </div>
  )
}

export default function Hosts() {
  const queryClient = useQueryClient()

  // Fetch hosts
  const { data: hosts = [], isLoading, refetch } = useQuery({
    queryKey: ['hosts'],
    queryFn: fetchHosts,
    refetchInterval: 30000,
  })

  // Mutations
  const enableHost = useMutation({
    mutationFn: (uuid: string) => client.post(`/hosts/${uuid}/enable`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosts'] }),
  })

  const disableHost = useMutation({
    mutationFn: (uuid: string) => client.post(`/hosts/${uuid}/disable`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosts'] }),
  })

  const deleteHost = useMutation({
    mutationFn: (uuid: string) => client.delete(`/hosts/${uuid}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['hosts'] }),
  })

  // Stats
  const totalHosts = hosts.length
  const activeHosts = hosts.filter((h) => !h.is_disabled).length
  const disabledHosts = hosts.filter((h) => h.is_disabled).length

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Хосты</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">Управление хостами подключений</p>
        </div>
        <button
          onClick={() => refetch()}
          className="btn-secondary flex items-center gap-2 self-start sm:self-auto"
          disabled={isLoading}
        >
          <HiRefresh className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Обновить</span>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 md:gap-4">
        <div className="card text-center">
          <p className="text-xs md:text-sm text-dark-200">Всего</p>
          <p className="text-xl md:text-2xl font-bold text-white mt-1">
            {isLoading ? '-' : totalHosts}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-xs md:text-sm text-dark-200">Активные</p>
          <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
            {isLoading ? '-' : activeHosts}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-xs md:text-sm text-dark-200">Отключены</p>
          <p className="text-xl md:text-2xl font-bold text-dark-200 mt-1">
            {isLoading ? '-' : disabledHosts}
          </p>
        </div>
      </div>

      {/* Hosts grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <HostSkeleton key={i} />)
        ) : hosts.length === 0 ? (
          <div className="col-span-full card text-center py-12">
            <HiGlobe className="w-12 h-12 text-dark-300 mx-auto mb-3" />
            <p className="text-dark-200">Нет хостов</p>
          </div>
        ) : (
          hosts.map((host) => (
            <HostCard
              key={host.uuid}
              host={host}
              onEnable={() => enableHost.mutate(host.uuid)}
              onDisable={() => disableHost.mutate(host.uuid)}
              onDelete={() => deleteHost.mutate(host.uuid)}
            />
          ))
        )}
      </div>
    </div>
  )
}
