import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  HiRefresh,
  HiStatusOnline,
  HiStatusOffline,
  HiGlobe,
  HiUsers,
  HiChartBar,
  HiClock,
  HiDotsVertical,
  HiPencil,
  HiTrash,
  HiPlay,
  HiStop,
  HiX,
} from 'react-icons/hi'
import client from '../api/client'

// Types
interface Node {
  uuid: string
  name: string
  address: string
  port: number
  is_connected: boolean
  is_disabled: boolean
  is_xray_running: boolean
  users_online: number
  xray_version: string | null
  message: string | null
  traffic_total_bytes: number
  traffic_today_bytes: number
  created_at: string
  last_seen_at: string | null
}

interface NodeEditFormData {
  name: string
  address: string
  port: string
}

// API functions
const fetchNodes = async (): Promise<Node[]> => {
  const { data } = await client.get('/nodes')
  return data.items || data
}

// Utility functions
function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  if (i < 0 || i >= sizes.length) return '0 Б'
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Никогда'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return 'Только что'
  if (diffMin < 60) return `${diffMin} мин назад`
  if (diffHour < 24) return `${diffHour} ч назад`
  return `${diffDay} дн назад`
}

// Node edit modal
function NodeEditModal({
  node,
  onClose,
  onSave,
  isPending,
  error,
}: {
  node: Node
  onClose: () => void
  onSave: (data: Record<string, unknown>) => void
  isPending: boolean
  error: string
}) {
  const [form, setForm] = useState<NodeEditFormData>({
    name: node.name,
    address: node.address,
    port: String(node.port),
  })

  useEffect(() => {
    setForm({
      name: node.name,
      address: node.address,
      port: String(node.port),
    })
  }, [node])

  const handleSubmit = () => {
    const updateData: Record<string, unknown> = {}
    if (form.name !== node.name) updateData.name = form.name
    if (form.address !== node.address) updateData.address = form.address
    const newPort = parseInt(form.port, 10)
    if (!isNaN(newPort) && newPort !== node.port) updateData.port = newPort
    if (Object.keys(updateData).length === 0) {
      onClose()
      return
    }
    onSave(updateData)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md card border border-dark-400/20 animate-scale-in">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Редактирование ноды</h2>
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
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="input"
              placeholder="Название ноды"
            />
          </div>
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
            disabled={isPending || !form.name.trim() || !form.address.trim() || !form.port}
            className="btn-primary px-4 py-2"
          >
            {isPending ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Node card component
function NodeCard({
  node,
  onRestart,
  onEdit,
  onEnable,
  onDisable,
  onDelete,
}: {
  node: Node
  onRestart: () => void
  onEdit: () => void
  onEnable: () => void
  onDisable: () => void
  onDelete: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  const isOnline = node.is_connected && !node.is_disabled
  const statusText = node.is_disabled
    ? 'Отключён'
    : node.is_connected
      ? 'Онлайн'
      : 'Офлайн'
  const statusClass = node.is_disabled
    ? 'badge-gray'
    : node.is_connected
      ? 'badge-success'
      : 'badge-danger'

  return (
    <div
      className={`card relative ${node.is_disabled ? 'opacity-60' : ''}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={`p-2.5 rounded-lg ${
              isOnline
                ? 'bg-green-500/10'
                : node.is_disabled
                  ? 'bg-gray-500/10'
                  : 'bg-red-500/10'
            }`}
          >
            {isOnline ? (
              <HiStatusOnline className="w-6 h-6 text-green-400" />
            ) : (
              <HiStatusOffline
                className={`w-6 h-6 ${node.is_disabled ? 'text-dark-200' : 'text-red-400'}`}
              />
            )}
          </div>
          <div>
            <h3 className="font-semibold text-white">{node.name}</h3>
            <p className="text-sm text-dark-200 flex items-center gap-1 truncate">
              <HiGlobe className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate">{node.address}:{node.port}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={statusClass}>{statusText}</span>

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
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setMenuOpen(false)}
                />
                <div className="dropdown-menu">
                  <button
                    onClick={() => {
                      onRestart()
                      setMenuOpen(false)
                    }}
                    className="w-full px-3 py-2 text-left text-sm text-dark-100 hover:bg-dark-600 flex items-center gap-2"
                  >
                    <HiRefresh className="w-4 h-4" /> Перезапустить
                  </button>
                  <button
                    onClick={() => {
                      onEdit()
                      setMenuOpen(false)
                    }}
                    className="w-full px-3 py-2 text-left text-sm text-dark-100 hover:bg-dark-600 flex items-center gap-2"
                  >
                    <HiPencil className="w-4 h-4" /> Редактировать
                  </button>
                  <div className="border-t border-dark-400/20 my-1" />
                  {node.is_disabled ? (
                    <button
                      onClick={() => {
                        onEnable()
                        setMenuOpen(false)
                      }}
                      className="w-full px-3 py-2 text-left text-sm text-green-400 hover:bg-dark-600 flex items-center gap-2"
                    >
                      <HiPlay className="w-4 h-4" /> Включить
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        onDisable()
                        setMenuOpen(false)
                      }}
                      className="w-full px-3 py-2 text-left text-sm text-yellow-400 hover:bg-dark-600 flex items-center gap-2"
                    >
                      <HiStop className="w-4 h-4" /> Отключить
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (confirm('Удалить ноду?')) {
                        onDelete()
                      }
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

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 md:gap-4 mb-4">
        <div className="text-center p-2 md:p-3 bg-dark-800/50 rounded-lg">
          <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
            <HiUsers className="w-3.5 h-3.5" />
            <span className="text-[10px] md:text-xs">Онлайн</span>
          </div>
          <p className="text-base md:text-lg font-semibold text-white">{node.users_online}</p>
        </div>
        <div className="text-center p-2 md:p-3 bg-dark-800/50 rounded-lg">
          <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
            <HiChartBar className="w-3.5 h-3.5" />
            <span className="text-[10px] md:text-xs">Сегодня</span>
          </div>
          <p className="text-sm md:text-lg font-semibold text-white">
            {formatBytes(node.traffic_today_bytes)}
          </p>
        </div>
        <div className="text-center p-2 md:p-3 bg-dark-800/50 rounded-lg">
          <div className="flex items-center justify-center gap-1 text-dark-200 mb-1">
            <HiChartBar className="w-3.5 h-3.5" />
            <span className="text-[10px] md:text-xs">Всего</span>
          </div>
          <p className="text-sm md:text-lg font-semibold text-white">
            {formatBytes(node.traffic_total_bytes)}
          </p>
        </div>
      </div>

      {/* Footer info */}
      <div className="flex items-center justify-between text-xs text-dark-200 pt-3 border-t border-dark-400/10">
        <div className="flex items-center gap-1">
          <HiClock className="w-3.5 h-3.5" />
          {formatTimeAgo(node.last_seen_at)}
        </div>
        {node.xray_version && (
          <span className="text-dark-300">Xray {node.xray_version}</span>
        )}
      </div>

      {/* Error message */}
      {node.message && !node.is_connected && (
        <div className="mt-3 p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
          {node.message}
        </div>
      )}
    </div>
  )
}

// Loading skeleton
function NodeSkeleton() {
  return (
    <div className="card animate-fade-in">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 bg-dark-700 rounded-lg" />
          <div>
            <div className="h-4 w-32 bg-dark-700 rounded mb-2" />
            <div className="h-3 w-24 bg-dark-700 rounded" />
          </div>
        </div>
        <div className="h-5 w-16 bg-dark-700 rounded" />
      </div>
      <div className="grid grid-cols-3 gap-4 mb-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="p-3 bg-dark-800/50 rounded-lg">
            <div className="h-3 w-12 bg-dark-700 rounded mx-auto mb-2" />
            <div className="h-5 w-8 bg-dark-700 rounded mx-auto" />
          </div>
        ))}
      </div>
      <div className="h-3 w-20 bg-dark-700 rounded" />
    </div>
  )
}

export default function Nodes() {
  const queryClient = useQueryClient()
  const [editingNode, setEditingNode] = useState<Node | null>(null)
  const [editError, setEditError] = useState('')

  // Fetch nodes
  const { data: nodes = [], isLoading, refetch } = useQuery({
    queryKey: ['nodes'],
    queryFn: fetchNodes,
    refetchInterval: 15000, // Refresh every 15 seconds
  })

  // Mutations
  const restartNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/restart`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
    },
  })

  const enableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/enable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
    },
  })

  const disableNode = useMutation({
    mutationFn: (uuid: string) => client.post(`/nodes/${uuid}/disable`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
    },
  })

  const deleteNode = useMutation({
    mutationFn: (uuid: string) => client.delete(`/nodes/${uuid}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
    },
  })

  const updateNode = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: Record<string, unknown> }) =>
      client.patch(`/nodes/${uuid}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      setEditingNode(null)
      setEditError('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setEditError(err.response?.data?.detail || err.message || 'Ошибка сохранения')
    },
  })

  // Calculate stats
  const totalNodes = nodes.length
  const onlineNodes = nodes.filter((n) => n.is_connected && !n.is_disabled).length
  const offlineNodes = nodes.filter((n) => !n.is_connected && !n.is_disabled).length
  const disabledNodes = nodes.filter((n) => n.is_disabled).length
  const totalUsersOnline = nodes.reduce((sum, n) => sum + n.users_online, 0)

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Ноды</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">Управление серверами</p>
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
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 md:gap-4">
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
          <p className="text-xs md:text-sm text-dark-200">Всего</p>
          <p className="text-xl md:text-2xl font-bold text-white mt-1">
            {isLoading ? '-' : totalNodes}
          </p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
          <p className="text-xs md:text-sm text-dark-200">Онлайн</p>
          <p className="text-xl md:text-2xl font-bold text-green-400 mt-1">
            {isLoading ? '-' : onlineNodes}
          </p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.15s' }}>
          <p className="text-xs md:text-sm text-dark-200">Офлайн</p>
          <p className="text-xl md:text-2xl font-bold text-red-400 mt-1">
            {isLoading ? '-' : offlineNodes}
          </p>
        </div>
        <div className="card text-center animate-fade-in-up" style={{ animationDelay: '0.2s' }}>
          <p className="text-xs md:text-sm text-dark-200">Отключены</p>
          <p className="text-xl md:text-2xl font-bold text-dark-200 mt-1">
            {isLoading ? '-' : disabledNodes}
          </p>
        </div>
        <div className="card text-center col-span-2 sm:col-span-1 animate-fade-in-up" style={{ animationDelay: '0.25s' }}>
          <p className="text-xs md:text-sm text-dark-200">Пользователей</p>
          <p className="text-xl md:text-2xl font-bold text-primary-400 mt-1">
            {isLoading ? '-' : totalUsersOnline}
          </p>
        </div>
      </div>

      {/* Nodes grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {isLoading ? (
          // Loading skeletons
          Array.from({ length: 4 }).map((_, i) => <NodeSkeleton key={i} />)
        ) : nodes.length === 0 ? (
          <div className="col-span-full card text-center py-12">
            <HiStatusOffline className="w-12 h-12 text-dark-300 mx-auto mb-3" />
            <p className="text-dark-200">Нет добавленных нод</p>
          </div>
        ) : (
          nodes.map((node, i) => (
            <div key={node.uuid} className="animate-fade-in-up" style={{ animationDelay: `${0.1 + i * 0.06}s` }}>
              <NodeCard
                node={node}
                onRestart={() => restartNode.mutate(node.uuid)}
                onEdit={() => { setEditingNode(node); setEditError('') }}
                onEnable={() => enableNode.mutate(node.uuid)}
                onDisable={() => disableNode.mutate(node.uuid)}
                onDelete={() => deleteNode.mutate(node.uuid)}
              />
            </div>
          ))
        )}
      </div>

      {/* Edit modal */}
      {editingNode && (
        <NodeEditModal
          node={editingNode}
          onClose={() => { setEditingNode(null); setEditError('') }}
          onSave={(data) => updateNode.mutate({ uuid: editingNode.uuid, data })}
          isPending={updateNode.isPending}
          error={editError}
        />
      )}
    </div>
  )
}
