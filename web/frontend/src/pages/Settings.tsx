import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  AlertTriangle,
  Clock,
  Lock,
  Zap,
  ChevronDown,
  ChevronRight,
  Search,
  RefreshCw,
  Database,
  X,
  Eye,
  EyeOff,
  Copy,
  KeyRound,
} from 'lucide-react'
import { toast } from 'sonner'
import client from '../api/client'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import { useHasPermission } from '@/components/PermissionGate'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

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
  env_value: string | null
  is_secret: boolean
  is_readonly: boolean
  is_env_override: boolean
  source: string // "db" | "env" | "default" | "none"
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

const resetSetting = async (key: string): Promise<void> => {
  await client.delete(`/settings/${key}`)
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


const subcategoryLabels: Record<string, string> = {
  'topics': 'Топики уведомлений',
  'weights': 'Веса компонентов скора',
}

const SYNC_ENTITY_LABELS: Record<string, string> = {
  users: 'Пользователи',
  nodes: 'Ноды',
  hosts: 'Хосты',
  config_profiles: 'Профили',
  templates: 'Шаблоны',
  snippets: 'Сниппеты',
  squads: 'Сквады',
  hwid_devices: 'HWID устройства',
  asn: 'ASN база',
}

// Entity keys that can be synced manually (maps display key -> API trigger key)
const SYNCABLE_ENTITIES: Record<string, string> = {
  users: 'users',
  nodes: 'nodes',
  hosts: 'hosts',
  config_profiles: 'config_profiles',
  hwid_devices: 'hwid_devices',
  asn: 'asn',
}

function SyncStatusBlock({
  syncItems,
  queryClient,
  canEdit,
}: {
  syncItems: SyncStatusItem[]
  queryClient: ReturnType<typeof useQueryClient>
  canEdit: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [syncingEntity, setSyncingEntity] = useState<string | null>(null)

  const syncMutation = useMutation({
    mutationFn: async (entity: string) => {
      setSyncingEntity(entity)
      await client.post(`/settings/sync/${entity}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] })
      setSyncingEntity(null)
      toast.success('Синхронизация завершена')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setSyncingEntity(null)
      toast.error(err.response?.data?.detail || err.message || 'Ошибка синхронизации')
    },
  })

  const syncAllMutation = useMutation({
    mutationFn: async () => {
      setSyncingEntity('all')
      await client.post('/settings/sync/all')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setSyncingEntity(null)
      toast.success('Полная синхронизация завершена')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setSyncingEntity(null)
      toast.error(err.response?.data?.detail || err.message || 'Ошибка синхронизации')
    },
  })

  // Filter out tokens from display, and ensure all SYNCABLE_ENTITIES are visible
  // even if they don't have a sync_metadata row yet (e.g. ASN before first sync)
  const existingKeys = new Set(syncItems.map((item) => item.key))
  const missingItems: SyncStatusItem[] = Object.keys(SYNCABLE_ENTITIES)
    .filter((key) => !existingKeys.has(key))
    .map((key) => ({
      key,
      last_sync_at: null,
      sync_status: 'never',
      error_message: null,
      records_synced: 0,
    }))
  const visibleItems = [...syncItems, ...missingItems].filter((item) => item.key !== 'tokens')

  const successCount = visibleItems.filter((i) => i.sync_status === 'success').length
  const errorCount = visibleItems.filter((i) => i.sync_status === 'error').length

  return (
    <Card className="p-0 overflow-hidden animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 md:p-5 hover:bg-dark-700/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          {isOpen ? (
            <ChevronDown className="w-5 h-5 text-dark-200 transition-transform duration-200" />
          ) : (
            <ChevronRight className="w-5 h-5 text-dark-200 transition-transform duration-200" />
          )}
          <h2 className="text-base font-semibold text-white">Синхронизация</h2>
          <span className="text-xs text-dark-300">{visibleItems.length}</span>
        </div>
        <div className="flex items-center gap-2">
          {errorCount > 0 && (
            <Badge variant="destructive" className="text-[10px] px-1.5 py-0.5">
              {errorCount} ошибок
            </Badge>
          )}
          {successCount > 0 && (
            <Badge variant="success" className="text-[10px] px-1.5 py-0.5">
              {successCount} ОК
            </Badge>
          )}
        </div>
      </button>

      {isOpen && (
        <div className="px-4 pb-4 md:px-5 md:pb-5 space-y-3">
          {/* Sync all button */}
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => { e.stopPropagation(); syncAllMutation.mutate() }}
              disabled={syncingEntity !== null || !canEdit}
              className="flex items-center gap-1.5 text-xs font-medium text-primary-400 bg-primary-500/10 hover:bg-primary-500/20 border-primary-500/20"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', syncingEntity === 'all' && 'animate-spin')} />
              Синхронизировать всё
            </Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {visibleItems.map((item) => {
              const entityKey = SYNCABLE_ENTITIES[item.key]
              const isSyncing = syncingEntity === item.key || syncingEntity === 'all'
              return (
                <div key={item.key} className="bg-dark-800/50 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-white">
                      {SYNC_ENTITY_LABELS[item.key] || item.key}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {entityKey && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => syncMutation.mutate(entityKey)}
                          disabled={syncingEntity !== null || !canEdit}
                          className="h-6 w-6 text-dark-400 hover:text-primary-400"
                          title="Синхронизировать"
                        >
                          <RefreshCw className={cn('w-3.5 h-3.5', isSyncing && 'animate-spin')} />
                        </Button>
                      )}
                      <span className={cn(
                        'w-2 h-2 rounded-full',
                        item.sync_status === 'success' ? 'bg-green-500' :
                        item.sync_status === 'error' ? 'bg-red-500' :
                        item.sync_status === 'never' ? 'bg-dark-400' : 'bg-yellow-500'
                      )} />
                    </div>
                  </div>
                  <div className="text-xs text-dark-200 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
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
              )
            })}
          </div>
        </div>
      )}
    </Card>
  )
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

function SourceBadge({ source }: { source: string }) {
  if (source === 'db') {
    return (
      <Badge className="gap-1 text-[10px] px-1.5 py-0.5" title="Значение из БД (наивысший приоритет)">
        <Database className="w-2.5 h-2.5" />
        БД
      </Badge>
    )
  }
  if (source === 'env') {
    return (
      <Badge variant="warning" className="gap-1 text-[10px] px-1.5 py-0.5" title="Значение из .env файла (fallback)">
        <Zap className="w-2.5 h-2.5" />
        .env
      </Badge>
    )
  }
  if (source === 'default') {
    return (
      <Badge variant="secondary" className="gap-1 text-[10px] px-1.5 py-0.5" title="Значение по умолчанию">
        По умолч.
      </Badge>
    )
  }
  return null
}

// Debounce hook for auto-save on text/number inputs
function useDebounce(callback: (key: string, value: string) => void, delay: number) {
  const timeoutRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  const debouncedFn = useCallback(
    (key: string, value: string) => {
      if (timeoutRef.current[key]) {
        clearTimeout(timeoutRef.current[key])
      }
      timeoutRef.current[key] = setTimeout(() => {
        callback(key, value)
        delete timeoutRef.current[key]
      }, delay)
    },
    [callback, delay],
  )

  // Cancel pending on unmount
  useEffect(() => {
    const refs = timeoutRef.current
    return () => {
      Object.values(refs).forEach(clearTimeout)
    }
  }, [])

  return debouncedFn
}

// Password generation constants
const PW_LOWER = 'abcdefghjkmnpqrstuvwxyz'
const PW_UPPER = 'ABCDEFGHJKMNPQRSTUVWXYZ'
const PW_DIGITS = '23456789'
const PW_SPECIAL = '!@#$%^&*_+-='
const PW_ALL = PW_LOWER + PW_UPPER + PW_DIGITS + PW_SPECIAL

function generatePassword(length = 16): string {
  const arr = new Uint32Array(length)
  crypto.getRandomValues(arr)
  const pick = (charset: string, rnd: number) => charset[rnd % charset.length]
  const chars = [
    pick(PW_LOWER, arr[0]),
    pick(PW_UPPER, arr[1]),
    pick(PW_DIGITS, arr[2]),
    pick(PW_SPECIAL, arr[3]),
  ]
  for (let i = 4; i < length; i++) {
    chars.push(pick(PW_ALL, arr[i]))
  }
  for (let i = chars.length - 1; i > 0; i--) {
    const j = arr[i] % (i + 1)
    ;[chars[i], chars[j]] = [chars[j], chars[i]]
  }
  return chars.join('')
}

interface PasswordStrengthResult {
  score: number
  level: 'none' | 'weak' | 'fair' | 'good' | 'strong'
  label: string
  color: string
  checks: {
    length: boolean
    lower: boolean
    upper: boolean
    digit: boolean
    special: boolean
  }
}

function getPasswordStrength(password: string): PasswordStrengthResult {
  const checks = {
    length: password.length >= 8,
    lower: /[a-z]/.test(password),
    upper: /[A-Z]/.test(password),
    digit: /\d/.test(password),
    special: /[!@#$%^&*_+\-=\[\]{}|;:',.<>?/\\~`"()]/.test(password),
  }
  const passedCount = Object.values(checks).filter(Boolean).length
  let score = passedCount * 16
  if (password.length >= 12) score += 10
  if (password.length >= 16) score += 10
  score = Math.min(100, score)

  if (password.length === 0) return { score: 0, level: 'none', label: '', color: '', checks }
  if (score < 30) return { score, level: 'weak', label: 'Слабый', color: '#ef4444', checks }
  if (score < 60) return { score, level: 'fair', label: 'Средний', color: '#f59e0b', checks }
  if (score < 80) return { score, level: 'good', label: 'Хороший', color: '#22c55e', checks }
  return { score, level: 'strong', label: 'Надёжный', color: '#10b981', checks }
}

function SettingsPasswordStrengthBar({ password }: { password: string }) {
  const strength = useMemo(() => getPasswordStrength(password), [password])

  if (password.length === 0) return null

  return (
    <div className="space-y-2 mt-2">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 rounded-full bg-dark-600/50 overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${strength.score}%`,
              backgroundColor: strength.color,
              boxShadow: `0 0 8px ${strength.color}40`,
            }}
          />
        </div>
        <span
          className="text-[11px] font-medium min-w-[60px] text-right transition-colors duration-300"
          style={{ color: strength.color }}
        >
          {strength.label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {[
          { ok: strength.checks.length, text: '8+ символов' },
          { ok: strength.checks.lower, text: 'Строчная (a-z)' },
          { ok: strength.checks.upper, text: 'Заглавная (A-Z)' },
          { ok: strength.checks.digit, text: 'Цифра (0-9)' },
          { ok: strength.checks.special, text: 'Спецсимвол' },
        ].map((c) => (
          <div
            key={c.text}
            className={cn(
              'text-[11px] flex items-center gap-1 transition-colors duration-200',
              c.ok ? 'text-green-400' : 'text-dark-300'
            )}
          >
            {c.ok ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
            {c.text}
          </div>
        ))}
      </div>
    </div>
  )
}

function SettingsPasswordInput({
  value,
  onChange,
  placeholder,
  autoComplete,
  disabled,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  autoComplete?: string
  disabled?: boolean
}) {
  const [show, setShow] = useState(false)

  return (
    <div className="relative">
      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-dark-400 pointer-events-none" />
      <Input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder || '••••••••'}
        autoComplete={autoComplete}
        disabled={disabled}
        className="w-full text-sm pl-10 pr-10 bg-dark-900 border-2 border-dark-600 text-white focus:border-accent-teal"
      />
      <button
        type="button"
        onClick={() => setShow(!show)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-400 hover:text-dark-200 transition-colors"
        tabIndex={-1}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  )
}

function ChangePasswordBlock() {
  const [isOpen, setIsOpen] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [copied, setCopied] = useState(false)
  const user = useAuthStore((s) => s.user)

  const { data: adminInfo } = useQuery({
    queryKey: ['adminInfo'],
    queryFn: () => authApi.getMe(),
  })

  const isPasswordAuth = user?.authMethod === 'password'
  const isGenerated = adminInfo?.password_is_generated ?? false
  const strength = useMemo(() => getPasswordStrength(newPassword), [newPassword])
  const allChecks = Object.values(strength.checks).every(Boolean)
  const passwordsMatch = newPassword === confirmPassword && confirmPassword.length > 0
  const canSubmit = currentPassword.length > 0 && allChecks && passwordsMatch && !saving

  const handleGenerate = () => {
    const pw = generatePassword(16)
    setNewPassword(pw)
    setConfirmPassword(pw)
  }

  const handleCopyNew = async () => {
    if (!newPassword) return
    try {
      await navigator.clipboard.writeText(newPassword)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard may not be available
    }
  }

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSaving(true)
    setError('')
    setSuccess('')
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setSuccess('Пароль успешно изменён')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка при смене пароля')
    } finally {
      setSaving(false)
    }
  }

  if (!isPasswordAuth) return null

  return (
    <Card className="p-0 overflow-hidden animate-fade-in-up" style={{ animationDelay: '0.06s' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 md:p-5 hover:bg-dark-700/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          {isOpen ? (
            <ChevronDown className="w-5 h-5 text-dark-200" />
          ) : (
            <ChevronRight className="w-5 h-5 text-dark-200" />
          )}
          <h2 className="text-base font-semibold text-white">Смена пароля</h2>
          {isGenerated && (
            <Badge variant="warning" className="text-[10px] px-1.5 py-0.5">
              Требуется смена
            </Badge>
          )}
        </div>
        <Lock className="w-4 h-4 text-dark-300" />
      </button>

      {isOpen && (
        <div className="px-4 md:px-5 pb-4 md:pb-5 border-t border-dark-700/50 animate-fade-in-down space-y-4">
          {isGenerated && (
            <div className="text-xs text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 rounded-lg px-3 py-2.5">
              Вы используете автоматически сгенерированный пароль. Рекомендуется сменить его на свой.
            </div>
          )}

          {error && (
            <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5 flex items-center">
              <span className="flex-1">{error}</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setError('')}
                className="h-5 w-5 ml-2 text-red-300 hover:text-red-200"
              >
                <X className="w-3 h-3" />
              </Button>
            </div>
          )}

          {success && (
            <div className="text-xs text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2.5">
              {success}
            </div>
          )}

          <div>
            <Label className="block text-xs font-medium text-dark-300 mb-1.5">Текущий пароль</Label>
            <SettingsPasswordInput
              value={currentPassword}
              onChange={setCurrentPassword}
              placeholder="Введите текущий пароль"
              autoComplete="current-password"
              disabled={saving}
            />
          </div>

          <Separator className="bg-dark-700/50" />

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <Label className="text-xs font-medium text-dark-300">Новый пароль</Label>
              <div className="flex items-center gap-1">
                {newPassword && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCopyNew}
                    className="h-6 px-2 text-[11px] text-dark-400 hover:text-dark-200"
                  >
                    {copied ? <Check className="w-3 h-3 mr-1 text-green-400" /> : <Copy className="w-3 h-3 mr-1" />}
                    {copied ? 'Скопировано' : 'Копировать'}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleGenerate}
                  disabled={saving}
                  className="h-6 px-2 text-[11px] text-accent-teal hover:text-accent-teal/80 hover:bg-accent-teal/10"
                >
                  <KeyRound className="w-3 h-3 mr-1" />
                  Генератор
                </Button>
              </div>
            </div>
            <SettingsPasswordInput
              value={newPassword}
              onChange={setNewPassword}
              placeholder="Введите новый пароль"
              autoComplete="new-password"
              disabled={saving}
            />
            <SettingsPasswordStrengthBar password={newPassword} />
          </div>

          <div>
            <Label className="block text-xs font-medium text-dark-300 mb-1.5">Подтвердите новый пароль</Label>
            <SettingsPasswordInput
              value={confirmPassword}
              onChange={setConfirmPassword}
              placeholder="Повторите новый пароль"
              autoComplete="new-password"
              disabled={saving}
            />
            {confirmPassword.length > 0 && !passwordsMatch && (
              <p className="text-[11px] text-red-400 mt-1">Пароли не совпадают</p>
            )}
            {confirmPassword.length > 0 && passwordsMatch && (
              <p className="text-[11px] text-green-400 mt-1 flex items-center gap-1">
                <Check className="w-3 h-3" /> Пароли совпадают
              </p>
            )}
          </div>

          <Button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="w-full text-sm bg-accent-teal text-white hover:bg-accent-teal/90 disabled:opacity-40"
          >
            {saving ? 'Сохранение...' : 'Сменить пароль'}
          </Button>
        </div>
      )}
    </Card>
  )
}

function IpWhitelistBlock() {
  const [isOpen, setIsOpen] = useState(false)
  const [newIp, setNewIp] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const { data, refetch } = useQuery({
    queryKey: ['ipWhitelist'],
    queryFn: async () => {
      const { data } = await client.get('/settings/ip-whitelist')
      return data as { enabled: boolean; ips: string[] }
    },
  })

  const ips = data?.ips || []
  const enabled = data?.enabled || false

  const saveList = async (newList: string[]) => {
    setSaving(true)
    setError('')
    try {
      await client.put('/settings/ip-whitelist', { value: newList.join(',') })
      await refetch()
    } catch (e: unknown) {
      const axiosErr = e as { response?: { data?: { detail?: string } }; message?: string }
      setError(axiosErr?.response?.data?.detail || axiosErr?.message || 'Error')
    } finally {
      setSaving(false)
    }
  }

  const addIp = () => {
    const val = newIp.trim()
    if (!val) return
    if (ips.includes(val)) {
      setError('IP already in the list')
      return
    }
    saveList([...ips, val])
    setNewIp('')
  }

  const removeIp = (ip: string) => {
    saveList(ips.filter((i) => i !== ip))
  }

  const disableWhitelist = () => {
    saveList([])
  }

  return (
    <Card className="p-0 overflow-hidden animate-fade-in-up" style={{ animationDelay: '0.08s' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 md:p-5 hover:bg-dark-700/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          {isOpen ? (
            <ChevronDown className="w-5 h-5 text-dark-200" />
          ) : (
            <ChevronRight className="w-5 h-5 text-dark-200" />
          )}
          <h2 className="text-base font-semibold text-white">IP Whitelist</h2>
          {enabled ? (
            <Badge variant="success" className="text-[10px] px-1.5 py-0.5">
              {ips.length} IP
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0.5">
              off
            </Badge>
          )}
        </div>
        <Lock className="w-4 h-4 text-dark-300" />
      </button>
      {isOpen && (
        <div className="px-4 md:px-5 pb-4 md:pb-5 border-t border-dark-700/50 animate-fade-in-down space-y-3">
          <p className="text-xs text-dark-200">
            Если список пуст — доступ разрешён с любого IP. При добавлении IP доступ будет ограничен только указанными адресами.
            Поддерживаются CIDR (например, 10.0.0.0/8).
          </p>

          {error && (
            <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-2 flex items-center">
              <span className="flex-1">{error}</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setError('')}
                className="h-5 w-5 ml-2 text-red-300 hover:text-red-200"
              >
                <X className="w-3 h-3" />
              </Button>
            </div>
          )}

          {/* Current IPs */}
          {ips.length > 0 && (
            <div className="space-y-1">
              {ips.map((ip) => (
                <div
                  key={ip}
                  className="flex items-center justify-between bg-dark-800/50 rounded px-3 py-1.5 group"
                >
                  <code className="text-sm text-white font-mono">{ip}</code>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeIp(ip)}
                    className="h-6 w-6 text-dark-400 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                    title="Remove"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}

          {/* Add new IP */}
          <div className="flex gap-2">
            <Input
              type="text"
              value={newIp}
              onChange={(e) => setNewIp(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addIp()}
              placeholder="1.2.3.4 or 10.0.0.0/24"
              className="flex-1 font-mono text-sm"
              disabled={saving}
            />
            <Button
              onClick={addIp}
              disabled={!newIp.trim() || saving}
              size="sm"
              className="px-4 text-sm"
            >
              {saving ? '...' : 'Add'}
            </Button>
          </div>

          {/* Disable button */}
          {enabled && (
            <Button
              variant="link"
              onClick={disableWhitelist}
              className="text-xs text-dark-300 hover:text-red-400 p-0 h-auto"
            >
              Disable whitelist (allow all IPs)
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}


export default function Settings() {
  const queryClient = useQueryClient()
  const canEdit = useHasPermission('settings', 'edit')
  const [search, setSearch] = useState('')
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({})
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set())
  const [savedKeys, setSavedKeys] = useState<Set<string>>(new Set())
  const [errorKeys, setErrorKeys] = useState<Record<string, string>>({})
  const [pendingValues, setPendingValues] = useState<Record<string, string>>({})

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

  // Save mutation — auto-save individual setting
  const saveMutation = useMutation({
    mutationFn: updateSetting,
    onMutate: ({ key }) => {
      setSavingKeys((prev) => new Set(prev).add(key))
      setErrorKeys((prev) => { const n = { ...prev }; delete n[key]; return n })
    },
    onSuccess: (_data, { key }) => {
      setSavingKeys((prev) => { const n = new Set(prev); n.delete(key); return n })
      setSavedKeys((prev) => new Set(prev).add(key))
      setPendingValues((prev) => { const n = { ...prev }; delete n[key]; return n })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setTimeout(() => setSavedKeys((prev) => { const n = new Set(prev); n.delete(key); return n }), 2000)
    },
    onError: (error: Error, { key }) => {
      setSavingKeys((prev) => { const n = new Set(prev); n.delete(key); return n })
      setErrorKeys((prev) => ({ ...prev, [key]: error.message }))
    },
  })

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: resetSetting,
    onSuccess: (_data, key) => {
      setPendingValues((prev) => { const n = { ...prev }; delete n[key]; return n })
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setSavedKeys((prev) => new Set(prev).add(key))
      setTimeout(() => setSavedKeys((prev) => { const n = new Set(prev); n.delete(key); return n }), 2000)
    },
  })

  const categories = settingsData?.categories || {}
  const syncItems = syncData?.items || []

  const toggleCategory = (category: string) => {
    setOpenCategories((prev) => ({ ...prev, [category]: !prev[category] }))
  }

  // Immediate save for bool/select — user clicks toggle and it saves right away
  const saveImmediately = useCallback(
    (key: string, value: string) => {
      saveMutation.mutate({ key, value })
    },
    [saveMutation],
  )

  // Debounced save for text/number — saves 800ms after user stops typing
  const saveDebounced = useDebounce(
    useCallback(
      (key: string, value: string) => {
        saveMutation.mutate({ key, value })
      },
      [saveMutation],
    ),
    800,
  )

  const handleTextChange = (key: string, value: string) => {
    setPendingValues((prev) => ({ ...prev, [key]: value }))
    saveDebounced(key, value)
  }

  const handleBoolToggle = (key: string, currentValue: boolean) => {
    const newVal = currentValue ? 'false' : 'true'
    setPendingValues((prev) => ({ ...prev, [key]: newVal }))
    saveImmediately(key, newVal)
  }

  const handleSelectChange = (key: string, value: string) => {
    setPendingValues((prev) => ({ ...prev, [key]: value }))
    saveImmediately(key, value)
  }

  const handleReset = (key: string) => {
    resetMutation.mutate(key)
  }

  const getDisplayValue = (item: ConfigItem): string => {
    if (item.key in pendingValues) return pendingValues[item.key]
    return item.value || ''
  }

  // Filter items by search
  const matchesSearch = (item: ConfigItem): boolean => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      (item.display_name?.toLowerCase().includes(q) ?? false) ||
      item.key.toLowerCase().includes(q) ||
      (item.description?.toLowerCase().includes(q) ?? false) ||
      (item.env_var_name?.toLowerCase().includes(q) ?? false)
    )
  }

  const renderConfigItem = (item: ConfigItem) => {
    const displayValue = getDisplayValue(item)
    const label = item.display_name || item.key
    const isEditable = !item.is_readonly && canEdit
    const isSaving = savingKeys.has(item.key)
    const wasSaved = savedKeys.has(item.key)
    const hasError = item.key in errorKeys
    const canReset = item.source === 'db' && !item.is_readonly && canEdit

    const statusIcon = isSaving ? (
      <RefreshCw className="w-3.5 h-3.5 text-primary-400 animate-spin" />
    ) : wasSaved ? (
      <Check className="w-3.5 h-3.5 text-green-400" />
    ) : hasError ? (
      <span title={errorKeys[item.key]}><AlertTriangle className="w-3.5 h-3.5 text-red-400" /></span>
    ) : null

    if (item.value_type === 'bool') {
      const boolValue = displayValue === 'true'
      return (
        <div key={item.key} className="flex items-center justify-between py-3 group">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-sm text-white">{label}</p>
              {item.is_readonly && <span title="Только для чтения"><Lock className="w-3 h-3 text-dark-300" /></span>}
              <SourceBadge source={item.source} />
              {statusIcon}
            </div>
            {item.description && <p className="text-xs text-dark-200 mt-0.5">{item.description}</p>}
            {item.is_env_override && item.source !== 'env' && (
              <p className="text-[10px] text-yellow-500/60 mt-0.5">
                .env: {item.env_var_name} = {item.env_value || '(set)'}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {canReset && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleReset(item.key)}
                className="h-6 w-6 text-dark-300 hover:text-dark-100 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Сбросить (использовать .env или значение по умолчанию)"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            )}
            <Switch
              checked={boolValue}
              onCheckedChange={() => isEditable && handleBoolToggle(item.key, boolValue)}
              disabled={!isEditable || isSaving}
            />
          </div>
        </div>
      )
    }

    if (item.value_type === 'int' || item.value_type === 'float') {
      return (
        <div key={item.key} className="py-3 group">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Label className="block text-sm text-dark-200">{label}</Label>
            {item.is_readonly && <Lock className="w-3 h-3 text-dark-300" />}
            <SourceBadge source={item.source} />
            {statusIcon}
            {canReset && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleReset(item.key)}
                className="h-6 w-6 text-dark-300 hover:text-dark-100 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Сбросить"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>
          <Input
            type="number"
            className="w-full"
            value={displayValue}
            onChange={(e) => handleTextChange(item.key, e.target.value)}
            disabled={!isEditable || isSaving}
            step={item.value_type === 'float' ? '0.1' : '1'}
          />
          <div className="flex items-center gap-2 mt-1">
            {item.description && <p className="text-xs text-dark-200 flex-1">{item.description}</p>}
            {item.is_env_override && item.source !== 'env' && (
              <p className="text-[10px] text-yellow-500/60 whitespace-nowrap">
                .env: {item.env_value}
              </p>
            )}
          </div>
        </div>
      )
    }

    if (item.options && item.options.length > 0) {
      return (
        <div key={item.key} className="py-3 group">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Label className="block text-sm text-dark-200">{label}</Label>
            {item.is_readonly && <Lock className="w-3 h-3 text-dark-300" />}
            <SourceBadge source={item.source} />
            {statusIcon}
            {canReset && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => handleReset(item.key)}
                className="h-6 w-6 text-dark-300 hover:text-dark-100 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Сбросить"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>
          <Select
            value={displayValue}
            onValueChange={(value) => handleSelectChange(item.key, value)}
            disabled={!isEditable || isSaving}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {item.options.map((opt) => (
                <SelectItem key={opt} value={opt}>{opt}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {item.description && <p className="text-xs text-dark-200 mt-1">{item.description}</p>}
        </div>
      )
    }

    // Default: string input
    return (
      <div key={item.key} className="py-3 group">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <Label className="block text-sm text-dark-200">{label}</Label>
          {item.is_readonly && <Lock className="w-3 h-3 text-dark-300" />}
          <SourceBadge source={item.source} />
          {statusIcon}
          {canReset && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleReset(item.key)}
              className="h-6 w-6 text-dark-300 hover:text-dark-100 opacity-0 group-hover:opacity-100 transition-opacity"
              title="Сбросить"
            >
              <X className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
        <Input
          type={item.is_secret ? 'password' : 'text'}
          className="w-full"
          value={displayValue}
          onChange={(e) => handleTextChange(item.key, e.target.value)}
          disabled={!isEditable || isSaving}
          placeholder={item.default_value || ''}
        />
        <div className="flex items-center gap-2 mt-1">
          {item.description && <p className="text-xs text-dark-200 flex-1">{item.description}</p>}
          {item.is_env_override && item.source !== 'env' && (
            <p className="text-[10px] text-yellow-500/60 whitespace-nowrap">
              .env: {item.env_value}
            </p>
          )}
        </div>
      </div>
    )
  }

  // Group items by subcategory within a category
  const renderCategoryItems = (items: ConfigItem[]) => {
    const filtered = items.filter(matchesSearch)
    if (filtered.length === 0) return null

    // Separate into subcategories
    const mainItems = filtered.filter((i) => !i.subcategory)
    const subcategories: Record<string, ConfigItem[]> = {}
    for (const item of filtered) {
      if (item.subcategory) {
        if (!subcategories[item.subcategory]) subcategories[item.subcategory] = []
        subcategories[item.subcategory].push(item)
      }
    }

    return (
      <>
        {mainItems.length > 0 && (
          <div className="divide-y divide-dark-700/50">
            {mainItems.map((item) => renderConfigItem(item))}
          </div>
        )}
        {Object.entries(subcategories).map(([sub, subItems]) => (
          <div key={sub} className="mt-3">
            <div className="text-xs font-medium text-dark-300 uppercase tracking-wider mb-1 px-1">
              {subcategoryLabels[sub] || sub}
            </div>
            <div className="bg-dark-800/30 rounded-lg px-3 divide-y divide-dark-700/30">
              {subItems.map((item) => renderConfigItem(item))}
            </div>
          </div>
        ))}
      </>
    )
  }

  // Count filtered items per category
  const filteredCounts = Object.entries(categories).reduce(
    (acc, [cat, items]) => {
      acc[cat] = items.filter(matchesSearch).length
      return acc
    },
    {} as Record<string, number>,
  )

  const totalFiltered = Object.values(filteredCounts).reduce((a, b) => a + b, 0)

  // Auto-open categories when searching
  const effectiveOpenCategories = search
    ? Object.fromEntries(Object.entries(filteredCounts).map(([cat, count]) => [cat, count > 0]))
    : openCategories

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="page-header">
        <div>
          <h1 className="page-header-title">Настройки</h1>
          <p className="text-dark-200 mt-1 text-sm md:text-base">
            Конфигурация бота и панели. Приоритет: БД {'>'} .env {'>'} по умолчанию
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => refetchSettings()}
          className="flex items-center gap-1"
        >
          <RefreshCw className="w-4 h-4" />
          <span className="hidden sm:inline">Обновить</span>
        </Button>
      </div>

      {/* Search */}
      <div className="relative animate-fade-in-up" style={{ animationDelay: '0.05s' }}>
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-300 pointer-events-none" />
        <Input
          type="text"
          placeholder="Поиск настроек..."
          className="w-full pl-10 pr-10"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {search && (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSearch('')}
            className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 text-dark-300 hover:text-dark-100"
          >
            <X className="w-4 h-4" />
          </Button>
        )}
        {search && (
          <p className="text-xs text-dark-200 mt-1 ml-1">
            Найдено: {totalFiltered} настроек
          </p>
        )}
      </div>

      {/* Sync status - collapsible */}
      {!search && (
        <SyncStatusBlock syncItems={syncItems} queryClient={queryClient} canEdit={canEdit} />
      )}

      {/* Security blocks */}
      {!search && <ChangePasswordBlock />}
      {!search && <IpWhitelistBlock />}

      {/* Settings as accordion */}
      {settingsLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4 md:p-5">
                <Skeleton className="h-6 w-40" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : Object.keys(categories).length > 0 ? (
        <div className="space-y-2">
          {Object.entries(categories).map(([category, items], catIdx) => {
            const isOpen = effectiveOpenCategories[category] ?? false
            const filteredCount = filteredCounts[category] || 0
            const dbCount = items.filter((i) => i.source === 'db').length

            // Hide categories with no matches when searching
            if (search && filteredCount === 0) return null

            return (
              <Card key={category} className="p-0 overflow-hidden animate-fade-in-up" style={{ animationDelay: `${0.05 * catIdx}s` }}>
                <button
                  onClick={() => toggleCategory(category)}
                  className="w-full flex items-center justify-between p-4 md:p-5 hover:bg-dark-700/30 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    {isOpen ? (
                      <ChevronDown className="w-5 h-5 text-dark-200 transition-transform duration-200" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-dark-200 transition-transform duration-200" />
                    )}
                    <h2 className="text-base font-semibold text-white">
                      {categoryLabels[category] || category}
                    </h2>
                    <span className="text-xs text-dark-300">
                      {search ? `${filteredCount}/${items.length}` : items.length}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {dbCount > 0 && (
                      <Badge className="text-[10px] px-1.5 py-0.5">
                        {dbCount} в БД
                      </Badge>
                    )}
                  </div>
                </button>
                {isOpen && (
                  <div className="px-4 md:px-5 pb-4 md:pb-5 border-t border-dark-700/50 animate-fade-in-down">
                    {renderCategoryItems(items)}
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      ) : (
        <Card className="text-center py-12">
          <CardContent className="pt-6">
            <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-3" />
            <p className="text-dark-200">Настройки не найдены</p>
            <p className="text-sm text-dark-200 mt-1">
              Убедитесь, что база данных подключена и бот хотя бы раз запускался
            </p>
            <Button
              variant="secondary"
              onClick={() => refetchSettings()}
              className="mt-4 inline-flex items-center gap-2"
            >
              <RefreshCw className="w-4 h-4" />
              Повторить
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Legend */}
      {!settingsLoading && Object.keys(categories).length > 0 && !search && (
        <Card className="animate-fade-in-up" style={{ animationDelay: '0.4s' }}>
          <CardContent className="pt-4 md:pt-6">
            <h3 className="text-xs font-medium text-dark-300 uppercase tracking-wider mb-2">Приоритет значений</h3>
            <div className="flex flex-wrap items-center gap-3 text-xs text-dark-200">
              <div className="flex items-center gap-1.5">
                <SourceBadge source="db" />
                <span>-- установлено в БД (главный)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <SourceBadge source="env" />
                <span>-- из .env файла (fallback)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <SourceBadge source="default" />
                <span>-- значение по умолчанию</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Lock className="w-3 h-3 text-dark-400" />
                <span>-- только чтение</span>
              </div>
              <div className="flex items-center gap-1.5">
                <X className="w-3 h-3 text-dark-400" />
                <span>-- сбросить к fallback</span>
              </div>
            </div>
            <Separator className="my-2" />
            <p className="text-[11px] text-dark-300">
              Настройки применяются мгновенно после изменения. Для сброса наведите на настройку и нажмите X.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
