import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  HiSave,
  HiRefresh,
  HiCheck,
  HiExclamation,
  HiClock,
  HiLockClosed,
  HiLightningBolt,
} from 'react-icons/hi'
import client from '../api/client'

// Types matching backend ConfigItemResponse
interface ConfigItem {
  key: string
  value: string | null
  value_type: string
  category: string
  subcategory: string | null
  display_name: string | null
  description: string | null
  default_value: string | null
  env_var_name: string | null
  is_secret: boolean
  is_readonly: boolean
  is_env_override: boolean
  options: string[] | null
  sort_order: number
}

interface ConfigByCategoryResponse {
  categories: Record<string, ConfigItem[]>
}

interface SyncStatusItem {
  key: string
  last_sync_at: string | null
  sync_status: string
  error_message: string | null
  records_synced: number
}

// API functions
const fetchSettings = async (): Promise<ConfigByCategoryResponse> => {
  const { data } = await client.get('/settings')
  return data
}

const fetchSyncStatus = async (): Promise<{ items: SyncStatusItem[] }> => {
  const { data } = await client.get('/settings/sync-status')
  return data
}

const updateSetting = async ({ key, value }: { key: string; value: string }): Promise<void> => {
  await client.put(`/settings/${key}`, { value })
}

// Category labels in Russian
const categoryLabels: Record<string, string> = {
  'general': 'Общие',
  'notifications': 'Уведомления',
  'sync': 'Синхронизация',
  'violations': 'Обнаружение нарушений',
  'reports': 'Отчёты',
  'collector': 'Коллектор данных',
  'limits': 'Лимиты',
  'appearance': 'Внешний вид',
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)

  if (diffSec < 60) return 'Только что'
  if (diffMin < 60) return `${diffMin} мин назад`
  if (diffHour < 24) return `${diffHour} ч назад`
  return date.toLocaleDateString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [editedValues, setEditedValues] = useState<Record<string, string>>({})
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Fetch settings
  const { data: settingsData, isLoading: settingsLoading, refetch: refetchSettings } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  // Fetch sync status
  const { data: syncData } = useQuery({
    queryKey: ['syncStatus'],
    queryFn: fetchSyncStatus,
    refetchInterval: 15000,
  })

  // Save individual setting
  const saveMutation = useMutation({
    mutationFn: updateSetting,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      const newEdited = { ...editedValues }
      delete newEdited[variables.key]
      setEditedValues(newEdited)
      setSaveSuccess(variables.key)
      setSaveError(null)
      setTimeout(() => setSaveSuccess(null), 2000)
    },
    onError: (error: Error, variables) => {
      setSaveError(`${variables.key}: ${error.message}`)
    },
  })

  const categories = settingsData?.categories || {}
  const syncItems = syncData?.items || []
  const hasChanges = Object.keys(editedValues).length > 0

  const handleValueChange = (key: string, value: string) => {
    setEditedValues((prev) => ({ ...prev, [key]: value }))
  }

  const handleSaveAll = () => {
    for (const [key, value] of Object.entries(editedValues)) {
      saveMutation.mutate({ key, value })
    }
  }

  const handleReset = () => {
    setEditedValues({})
    setSaveError(null)
  }

  const getDisplayValue = (item: ConfigItem): string => {
    if (item.key in editedValues) {
      return editedValues[item.key]
    }
    return item.value || ''
  }

  const renderConfigItem = (item: ConfigItem) => {
    const displayValue = getDisplayValue(item)
    const label = item.display_name || item.key
    const isEditable = !item.is_readonly && !item.is_env_override
    const wasSaved = saveSuccess === item.key

    if (item.value_type === 'bool') {
      const boolValue = displayValue === 'true'
      return (
        <div key={item.key} className="flex items-center justify-between py-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-sm text-white">{label}</p>
              {item.is_readonly && <HiLockClosed className="w-3 h-3 text-dark-300" title="Только для чтения" />}
              {item.is_env_override && <HiLightningBolt className="w-3 h-3 text-yellow-500" title={`Переопределено: ${item.env_var_name}`} />}
              {wasSaved && <HiCheck className="w-4 h-4 text-green-400" />}
            </div>
            {item.description && <p className="text-xs text-dark-200 mt-0.5">{item.description}</p>}
          </div>
          <button
            onClick={() => isEditable && handleValueChange(item.key, boolValue ? 'false' : 'true')}
            disabled={!isEditable}
            className={`w-12 h-6 rounded-full relative transition-all duration-200 ${
              boolValue ? 'bg-primary-600' : 'bg-dark-600'
            } ${!isEditable ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
          >
            <span
              className={`absolute top-1 w-4 h-4 rounded-full transition-all ${
                boolValue ? 'right-1 bg-white' : 'left-1 bg-gray-400'
              }`}
            ></span>
          </button>
        </div>
      )
    }

    if (item.value_type === 'int' || item.value_type === 'float') {
      return (
        <div key={item.key} className="py-2">
          <div className="flex items-center gap-2 mb-1">
            <label className="block text-sm text-dark-200">{label}</label>
            {item.is_readonly && <HiLockClosed className="w-3 h-3 text-dark-300" />}
            {item.is_env_override && <HiLightningBolt className="w-3 h-3 text-yellow-500" title={`Переопределено: ${item.env_var_name}`} />}
            {wasSaved && <HiCheck className="w-4 h-4 text-green-400" />}
          </div>
          <input
            type="number"
            className="input w-full"
            value={displayValue}
            onChange={(e) => handleValueChange(item.key, e.target.value)}
            disabled={!isEditable}
            step={item.value_type === 'float' ? '0.1' : '1'}
          />
          {item.description && <p className="text-xs text-dark-200 mt-1">{item.description}</p>}
        </div>
      )
    }

    if (item.options && item.options.length > 0) {
      return (
        <div key={item.key} className="py-2">
          <div className="flex items-center gap-2 mb-1">
            <label className="block text-sm text-dark-200">{label}</label>
            {item.is_readonly && <HiLockClosed className="w-3 h-3 text-dark-300" />}
            {item.is_env_override && <HiLightningBolt className="w-3 h-3 text-yellow-500" />}
            {wasSaved && <HiCheck className="w-4 h-4 text-green-400" />}
          </div>
          <select
            className="input w-full"
            value={displayValue}
            onChange={(e) => handleValueChange(item.key, e.target.value)}
            disabled={!isEditable}
          >
            {item.options.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
          {item.description && <p className="text-xs text-dark-200 mt-1">{item.description}</p>}
        </div>
      )
    }

    // Default: string input
    return (
      <div key={item.key} className="py-2">
        <div className="flex items-center gap-2 mb-1">
          <label className="block text-sm text-dark-200">{label}</label>
          {item.is_readonly && <HiLockClosed className="w-3 h-3 text-dark-300" />}
          {item.is_env_override && <HiLightningBolt className="w-3 h-3 text-yellow-500" title={`Переопределено: ${item.env_var_name}`} />}
          {wasSaved && <HiCheck className="w-4 h-4 text-green-400" />}
        </div>
        <input
          type={item.is_secret ? 'password' : 'text'}
          className="input w-full"
          value={displayValue}
          onChange={(e) => handleValueChange(item.key, e.target.value)}
          disabled={!isEditable}
          placeholder={item.default_value || ''}
        />
        {item.description && <p className="text-xs text-dark-200 mt-1">{item.description}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Настройки</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">Конфигурация панели администратора</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReset}
            className="btn-secondary flex items-center gap-1"
            disabled={!hasChanges}
          >
            <HiRefresh className="w-4 h-4" />
            <span className="hidden sm:inline">Сбросить</span>
          </button>
          <button
            onClick={handleSaveAll}
            className="btn-primary flex items-center gap-1"
            disabled={!hasChanges || saveMutation.isPending}
          >
            {saveMutation.isPending ? (
              <HiRefresh className="w-4 h-4 animate-spin" />
            ) : (
              <HiSave className="w-4 h-4" />
            )}
            <span className="hidden sm:inline">Сохранить</span>
          </button>
        </div>
      </div>

      {/* Error display */}
      {saveError && (
        <div className="card border-red-500/50 bg-red-500/10">
          <div className="flex items-center gap-2 text-red-400">
            <HiExclamation className="w-5 h-5" />
            <span className="text-sm">{saveError}</span>
          </div>
        </div>
      )}

      {/* Sync status */}
      {syncItems.length > 0 && (
        <div className="card">
          <h2 className="text-base md:text-lg font-semibold text-white mb-3">Статус синхронизации</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {syncItems.map((item) => (
              <div key={item.key} className="bg-dark-800/50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-white capitalize">{item.key}</span>
                  <span className={`w-2 h-2 rounded-full ${
                    item.sync_status === 'success' ? 'bg-green-500' :
                    item.sync_status === 'error' ? 'bg-red-500' : 'bg-yellow-500'
                  }`}></span>
                </div>
                <div className="text-xs text-dark-200 flex items-center gap-1">
                  <HiClock className="w-3 h-3" />
                  {item.last_sync_at ? formatTimeAgo(item.last_sync_at) : 'Никогда'}
                </div>
                {item.records_synced > 0 && (
                  <div className="text-xs text-dark-200 mt-0.5">
                    {item.records_synced} записей
                  </div>
                )}
                {item.error_message && (
                  <div className="text-xs text-red-400 mt-1 truncate" title={item.error_message}>
                    {item.error_message}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Settings grouped by category */}
      {settingsLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card animate-fade-in">
              <div className="h-6 w-40 bg-dark-700 rounded mb-4"></div>
              <div className="space-y-4">
                <div className="h-10 bg-dark-700 rounded"></div>
                <div className="h-10 bg-dark-700 rounded"></div>
                <div className="h-10 bg-dark-700 rounded"></div>
              </div>
            </div>
          ))}
        </div>
      ) : Object.keys(categories).length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {Object.entries(categories).map(([category, items]) => (
            <div key={category} className="card">
              <h2 className="text-lg font-semibold text-white mb-3">
                {categoryLabels[category] || category}
              </h2>
              <div className="divide-y divide-dark-700">
                {items.map((item) => renderConfigItem(item))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card text-center py-12">
          <HiExclamation className="w-12 h-12 text-yellow-500 mx-auto mb-3" />
          <p className="text-dark-200">Настройки не найдены</p>
          <p className="text-sm text-dark-200 mt-1">
            Убедитесь, что база данных подключена и бот хотя бы раз запускался
          </p>
          <button
            onClick={() => refetchSettings()}
            className="btn-secondary mt-4 inline-flex items-center gap-2"
          >
            <HiRefresh className="w-4 h-4" />
            Повторить
          </button>
        </div>
      )}

      {/* Unsaved changes indicator */}
      {hasChanges && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 border border-primary-500/30 rounded-lg px-4 py-3 flex items-center gap-3 z-50 animate-fade-in" style={{ background: 'rgba(22, 27, 34, 0.95)', backdropFilter: 'blur(12px)', boxShadow: '0 8px 32px rgba(0,0,0,0.4), 0 0 20px -5px rgba(13, 148, 136, 0.3)' }}>
          <span className="text-sm text-dark-100">
            Несохранённые изменения: {Object.keys(editedValues).length}
          </span>
          <button
            onClick={handleSaveAll}
            className="btn-primary text-sm py-1.5 px-3"
            disabled={saveMutation.isPending}
          >
            Сохранить
          </button>
          <button onClick={handleReset} className="btn-ghost text-sm py-1.5 px-3">
            Отмена
          </button>
        </div>
      )}
    </div>
  )
}
