import { useState } from 'react'
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

// API functions
const fetchNodes = async (): Promise<Node[]> => {
  const { data } = await client.get('/nodes')
  return data.items || data
}

// Utility functions
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 Б'
  const k = 1024
  const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
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

// Node card component
function NodeCard({
  node,
  onRestart,
  onEnable,
  onDisable,
  onDelete,
}: {
  node: Node
  onRestart: () => void
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
                className={`w-6 h-6 ${node.is_disabled ? 'text-gray-400' : 'text-red-400'}`}
              />
            )}
          </div>
          <div>
            <h3 className="font-semibold text-white">{node.name}</h3>
            <p className="text-sm text-gray-500 flex items-center gap-1">
              <HiGlobe className="w-3.5 h-3.5" />
              {node.address}:{node.port}
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
                <div className="absolute right-0 top-full mt-1 w-44 bg-dark-800 border border-dark-600 rounded-lg shadow-xl z-20 py-1">
                  <button
                    onClick={() => {
                      onRestart()
                      setMenuOpen(false)
                    }}
                    className="w-full px-3 py-2 text-left text-sm text-gray-300 hover:bg-dark-700 flex items-center gap-2"
                  >
                    <HiRefresh className="w-4 h-4" /> Перезапустить
                  </button>
                  <button
                    onClick={() => setMenuOpen(false)}
                    className="w-full px-3 py-2 text-left text-sm text-gray-300 hover:bg-dark-700 flex items-center gap-2"
                  >
                    <HiPencil className="w-4 h-4" /> Редактировать
                  </button>
                  <div className="border-t border-dark-600 my-1" />
                  {node.is_disabled ? (
                    <button
                      onClick={() => {
                        onEnable()
                        setMenuOpen(false)
                      }}
                      className="w-full px-3 py-2 text-left text-sm text-green-400 hover:bg-dark-700 flex items-center gap-2"
                    >
                      <HiPlay className="w-4 h-4" /> Включить
                    </button>
                  ) : (
                    <button
                      onClick={() => {
                        onDisable()
                        setMenuOpen(false)
                      }}
                      className="w-full px-3 py-2 text-left text-sm text-yellow-400 hover:bg-dark-700 flex items-center gap-2"
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
                    className="w-full px-3 py-2 text-left text-sm text-red-400 hover:bg-dark-700 flex items-center gap-2"
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
      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="text-center p-3 bg-dark-900/50 rounded-lg">
          <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
            <HiUsers className="w-4 h-4" />
            <span className="text-xs">Онлайн</span>
          </div>
          <p className="text-lg font-semibold text-white">{node.users_online}</p>
        </div>
        <div className="text-center p-3 bg-dark-900/50 rounded-lg">
          <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
            <HiChartBar className="w-4 h-4" />
            <span className="text-xs">Сегодня</span>
          </div>
          <p className="text-lg font-semibold text-white">
            {formatBytes(node.traffic_today_bytes)}
          </p>
        </div>
        <div className="text-center p-3 bg-dark-900/50 rounded-lg">
          <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
            <HiChartBar className="w-4 h-4" />
            <span className="text-xs">Всего</span>
          </div>
          <p className="text-lg font-semibold text-white">
            {formatBytes(node.traffic_total_bytes)}
          </p>
        </div>
      </div>

      {/* Footer info */}
      <div className="flex items-center justify-between text-xs text-gray-500 pt-3 border-t border-dark-700">
        <div className="flex items-center gap-1">
          <HiClock className="w-3.5 h-3.5" />
          {formatTimeAgo(node.last_seen_at)}
        </div>
        {node.xray_version && (
          <span className="text-gray-600">Xray {node.xray_version}</span>
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
    <div className="card animate-pulse">
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
          <div key={i} className="p-3 bg-dark-900/50 rounded-lg">
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

  // Calculate stats
  const totalNodes = nodes.length
  const onlineNodes = nodes.filter((n) => n.is_connected && !n.is_disabled).length
  const offlineNodes = nodes.filter((n) => !n.is_connected && !n.is_disabled).length
  const disabledNodes = nodes.filter((n) => n.is_disabled).length
  const totalUsersOnline = nodes.reduce((sum, n) => sum + n.users_online, 0)

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Ноды</h1>
          <p className="text-gray-400 mt-1">Управление серверами</p>
        </div>
        <button
          onClick={() => refetch()}
          className="btn-secondary flex items-center gap-2"
          disabled={isLoading}
        >
          <HiRefresh className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          Обновить
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="card text-center">
          <p className="text-sm text-gray-400">Всего</p>
          <p className="text-2xl font-bold text-white mt-1">
            {isLoading ? '-' : totalNodes}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-sm text-gray-400">Онлайн</p>
          <p className="text-2xl font-bold text-green-400 mt-1">
            {isLoading ? '-' : onlineNodes}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-sm text-gray-400">Офлайн</p>
          <p className="text-2xl font-bold text-red-400 mt-1">
            {isLoading ? '-' : offlineNodes}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-sm text-gray-400">Отключены</p>
          <p className="text-2xl font-bold text-gray-400 mt-1">
            {isLoading ? '-' : disabledNodes}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-sm text-gray-400">Пользователей</p>
          <p className="text-2xl font-bold text-primary-400 mt-1">
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
            <HiStatusOffline className="w-12 h-12 text-gray-600 mx-auto mb-3" />
            <p className="text-gray-400">Нет добавленных нод</p>
          </div>
        ) : (
          nodes.map((node) => (
            <NodeCard
              key={node.uuid}
              node={node}
              onRestart={() => restartNode.mutate(node.uuid)}
              onEnable={() => enableNode.mutate(node.uuid)}
              onDisable={() => disableNode.mutate(node.uuid)}
              onDelete={() => deleteNode.mutate(node.uuid)}
            />
          ))
        )}
      </div>
    </div>
  )
}
