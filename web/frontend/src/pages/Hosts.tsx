import { useState, useEffect } from 'react'
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
  HiX,
  HiPlus,
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

interface HostEditFormData {
  remark: string
  address: string
  port: string
  sni: string
  host: string
  path: string
  security: string
  alpn: string
  fingerprint: string
}

// Host edit modal
function HostEditModal({
  host,
  onClose,
  onSave,
  isPending,
  error,
}: {
  host: Host
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const [form, setForm] = useState<HostEditFormData>({
    remark: host.remark || '',
    address: host.address || '',
    port: String(host.port),
    sni: host.sni || '',
    host: host.host || '',
    path: host.path || '',
    security: host.security || 'none',
    alpn: host.alpn || '',
    fingerprint: host.fingerprint || '',
  })

  useEffect(() => {
    setForm({
      remark: host.remark || '',
      address: host.address || '',
      port: String(host.port),
      sni: host.sni || '',
      host: host.host || '',
      path: host.path || '',
      security: host.security || 'none',
      alpn: host.alpn || '',
      fingerprint: host.fingerprint || '',
    })
  }, [host])

  const handleSubmit = () => {
    const updateData: Record<string, unknown> = {}
    if (form.remark !== (host.remark || '')) updateData.remark = form.remark
    if (form.address !== (host.address || '')) updateData.address = form.address
    const newPort = parseInt(form.port, 10)
    if (!isNaN(newPort) && newPort !== host.port) updateData.port = newPort
    if (form.sni !== (host.sni || '')) updateData.sni = form.sni || null
    if (form.host !== (host.host || '')) updateData.host = form.host || null
    if (form.path !== (host.path || '')) updateData.path = form.path || null
    if (form.security !== (host.security || 'none')) updateData.security = form.security
    if (form.alpn !== (host.alpn || '')) updateData.alpn = form.alpn || null
    if (form.fingerprint !== (host.fingerprint || '')) updateData.fingerprint = form.fingerprint || null

    if (Object.keys(updateData).length === 0) {
      onClose()
      return
    }
    onSave(updateData)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg card border border-dark-400/20 animate-scale-in max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Редактирование хоста</h2>
          <button onClick={onClose} className="btn-ghost p-1.5 rounded">
            <HiX className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Название</label>
            <input
              type="text"
              value={form.remark}
              onChange={(e) => setForm({ ...form, remark: e.target.value })}
              className="input"
              placeholder="Название хоста"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-dark-200 mb-1.5">Адрес</label>
              <input
                type="text"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                className="input"
                placeholder="IP или домен"
              />
            </div>
            <div>
              <label className="block text-sm text-dark-200 mb-1.5">Порт</label>
              <input
                type="number"
                min="1"
                max="65535"
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
                className="input"
                placeholder="Порт"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Безопасность</label>
            <select
              value={form.security}
              onChange={(e) => setForm({ ...form, security: e.target.value })}
              className="input"
            >
              <option value="none">Без шифрования</option>
              <option value="tls">TLS</option>
              <option value="reality">Reality</option>
              <option value="xtls">XTLS</option>
            </select>
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">SNI</label>
            <input
              type="text"
              value={form.sni}
              onChange={(e) => setForm({ ...form, sni: e.target.value })}
              className="input"
              placeholder="Server Name Indication"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Host</label>
            <input
              type="text"
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
              className="input"
              placeholder="Host header"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Path</label>
            <input
              type="text"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              className="input font-mono text-sm"
              placeholder="/path"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">ALPN</label>
            <input
              type="text"
              value={form.alpn}
              onChange={(e) => setForm({ ...form, alpn: e.target.value })}
              className="input"
              placeholder="h2,http/1.1"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Fingerprint</label>
            <input
              type="text"
              value={form.fingerprint}
              onChange={(e) => setForm({ ...form, fingerprint: e.target.value })}
              className="input"
              placeholder="chrome, firefox, safari..."
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            disabled={isPending}
            className="btn-secondary px-4 py-2"
          >
            Отмена
          </button>
          <button
            onClick={handleSubmit}
            disabled={isPending || !form.address.trim() || !form.port}
            className="btn-primary px-4 py-2"
          >
            {isPending ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Host create modal
function HostCreateModal({
  onClose,
  onSave,
  isPending,
  error,
}: {
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const [form, setForm] = useState<HostEditFormData>({
    remark: '',
    address: '',
    port: '443',
    sni: '',
    host: '',
    path: '',
    security: 'tls',
    alpn: '',
    fingerprint: '',
  })

  const handleSubmit = () => {
    const createData: Record<string, unknown> = {
      remark: form.remark.trim(),
      address: form.address.trim(),
    }
    const port = parseInt(form.port, 10)
    if (!isNaN(port)) createData.port = port
    createData.security = form.security
    if (form.sni.trim()) createData.sni = form.sni.trim()
    if (form.host.trim()) createData.host = form.host.trim()
    if (form.path.trim()) createData.path = form.path.trim()
    if (form.alpn.trim()) createData.alpn = form.alpn.trim()
    if (form.fingerprint.trim()) createData.fingerprint = form.fingerprint.trim()
    onSave(createData)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg card border border-dark-400/20 animate-scale-in max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Добавление хоста</h2>
          <button onClick={onClose} className="btn-ghost p-1.5 rounded">
            <HiX className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Название</label>
            <input
              type="text"
              value={form.remark}
              onChange={(e) => setForm({ ...form, remark: e.target.value })}
              className="input"
              placeholder="Название хоста"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-dark-200 mb-1.5">Адрес</label>
              <input
                type="text"
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                className="input"
                placeholder="IP или домен"
              />
            </div>
            <div>
              <label className="block text-sm text-dark-200 mb-1.5">Порт</label>
              <input
                type="number"
                min="1"
                max="65535"
                value={form.port}
                onChange={(e) => setForm({ ...form, port: e.target.value })}
                className="input"
                placeholder="Порт"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Безопасность</label>
            <select
              value={form.security}
              onChange={(e) => setForm({ ...form, security: e.target.value })}
              className="input"
            >
              <option value="none">Без шифрования</option>
              <option value="tls">TLS</option>
              <option value="reality">Reality</option>
              <option value="xtls">XTLS</option>
            </select>
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">SNI</label>
            <input
              type="text"
              value={form.sni}
              onChange={(e) => setForm({ ...form, sni: e.target.value })}
              className="input"
              placeholder="Server Name Indication"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Host</label>
            <input
              type="text"
              value={form.host}
              onChange={(e) => setForm({ ...form, host: e.target.value })}
              className="input"
              placeholder="Host header"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Path</label>
            <input
              type="text"
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              className="input font-mono text-sm"
              placeholder="/path"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">ALPN</label>
            <input
              type="text"
              value={form.alpn}
              onChange={(e) => setForm({ ...form, alpn: e.target.value })}
              className="input"
              placeholder="h2,http/1.1"
            />
          </div>

          <div>
            <label className="block text-sm text-dark-200 mb-1.5">Fingerprint</label>
            <input
              type="text"
              value={form.fingerprint}
              onChange={(e) => setForm({ ...form, fingerprint: e.target.value })}
              className="input"
              placeholder="chrome, firefox, safari..."
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            disabled={isPending}
            className="btn-secondary px-4 py-2"
          >
            Отмена
          </button>
          <button
            onClick={handleSubmit}
            disabled={isPending || !form.address.trim() || !form.port}
            className="btn-primary px-4 py-2"
          >
            {isPending ? 'Создание...' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Host card component
function HostCard({
  host,
  onEdit,
  onEnable,
  onDisable,
  onDelete,
}: {
  host: Host
  onEdit: () => void
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className={`card relative ${host.is_disabled ? 'opacity-60' : ''} ${menuOpen ? 'z-30' : ''}`}>
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
                <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
                <div className="dropdown-menu">
                  <button
                    onClick={() => { onEdit(); setMenuOpen(false) }}
                    className="w-full px-3 py-2 text-left text-sm text-dark-100 hover:bg-dark-600 flex items-center gap-2"
                  >
                    <HiPencil className="w-4 h-4" /> Редактировать
                  </button>
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
  const [editingHost, setEditingHost] = useState<Host | null>(null)
  const [editError, setEditError] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createError, setCreateError] = useState('')

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

  const updateHost = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: Record<string, unknown> }) =>
      client.patch(`/hosts/${uuid}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      setEditingHost(null)
      setEditError('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setEditError(err.response?.data?.detail || err.message || 'Ошибка сохранения')
    },
  })

  const createHost = useMutation({
    mutationFn: (data: Record<string, unknown>) => client.post('/hosts', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hosts'] })
      setShowCreateModal(false)
      setCreateError('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setCreateError(err.response?.data?.detail || err.message || 'Ошибка создания')
    },
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
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            onClick={() => { setShowCreateModal(true); setCreateError('') }}
            className="btn-primary flex items-center gap-2"
          >
            <HiPlus className="w-4 h-4" />
            <span className="hidden sm:inline">Добавить</span>
          </button>
          <button
            onClick={() => refetch()}
            className="btn-secondary flex items-center gap-2"
            disabled={isLoading}
          >
            <HiRefresh className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Обновить</span>
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 md:gap-4">
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <p className="text-xs md:text-sm text-dark-200">Всего</p>
          <p className="text-xl md:text-2xl font-bold text-white mt-1">
            {isLoading ? '-' : totalHosts}
          </p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <p className="text-xs md:text-sm text-dark-200">Активные</p>
          <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
            {isLoading ? '-' : activeHosts}
          </p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
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
          hosts.map((host, i) => (
            <div key={host.uuid} className="animate-fade-in-up" style={{ animationDelay: `${0.1 + i * 0.06}s` }}>
              <HostCard
                host={host}
                onEdit={() => { setEditingHost(host); setEditError('') }}
                onEnable={() => enableHost.mutate(host.uuid)}
                onDisable={() => disableHost.mutate(host.uuid)}
                onDelete={() => deleteHost.mutate(host.uuid)}
              />
            </div>
          ))
        )}
      </div>

      {/* Edit modal */}
      {editingHost && (
        <HostEditModal
          host={editingHost}
          onClose={() => { setEditingHost(null); setEditError('') }}
          onSave={(data) => updateHost.mutate({ uuid: editingHost.uuid, data })}
          isPending={updateHost.isPending}
          error={editError}
        />
      )}

      {/* Create modal */}
      {showCreateModal && (
        <HostCreateModal
          onClose={() => { setShowCreateModal(false); setCreateError('') }}
          onSave={(data) => createHost.mutate(data)}
          isPending={createHost.isPending}
          error={createError}
        />
      )}
    </div>
  )
}
