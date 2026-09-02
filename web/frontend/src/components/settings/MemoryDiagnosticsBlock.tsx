import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import client from '../../api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface CacheEntry {
  name: string
  items: number
  bytes: number
  note?: string
}

interface ProcessSnapshot {
  app_mode: string
  pid: number
  uptime_seconds: number | null
  rss_bytes: number | null
  rss_peak_bytes: number | null
  threads: number | null
  cpu_seconds: { user: number; system: number }
  asyncio_tasks: number
  tasks_by_coroutine: { coroutine: string; count: number }[]
  collector_stats: Record<string, number | string | null> | null
  caches: CacheEntry[]
}

interface Snapshot {
  taken_at: string
  host: {
    cpu_count: number | null
    load_avg: number[] | null
    mem_total_bytes: number | null
    mem_available_bytes: number | null
    swap_used_bytes?: number
    cgroup_mem_limit_bytes?: number
    disk_free_bytes?: number
    disk_total_bytes?: number
  }
  database: {
    error?: string
    size_bytes?: number
    active_connections?: number
    connections_last_hour?: number
    users_total?: number
    nodes_total?: number
    nodes_connected?: number
    activity?: { total: number; active: number; waiting_lock: number; idle_in_tx: number; longest_active_seconds: number }
    slow_queries?: { seconds: number; state: string; query: string }[]
  }
  collector_error?: string
  processes: ProcessSnapshot[]
}

function human(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '—'
  let value = bytes
  const units = ['B', 'KB', 'MB', 'GB']
  for (const unit of units) {
    if (value < 1024 || unit === 'GB') {
      return unit === 'B' ? `${value.toFixed(0)} ${unit}` : `${value.toFixed(1)} ${unit}`
    }
    value /= 1024
  }
  return `${value.toFixed(1)} GB`
}

/**
 * Снимок памяти: во что упёрлась админка прямо сейчас.
 *
 * Ставится по следам разбора, где память росла до потолка за час-три после
 * рестарта, а снять с работающей установки было нечего.
 */
export function MemoryDiagnosticsBlock() {
  const { t } = useTranslation()
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const take = async () => {
    setLoading(true)
    try {
      const { data } = await client.get<Snapshot>('/diagnostics/memory')
      setSnapshot(data)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  const download = async (fmt: 'json' | 'txt') => {
    setDownloading(true)
    try {
      const res = await client.get(`/diagnostics/memory/download?fmt=${fmt}`, {
        responseType: 'blob',
      })
      const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
      const url = URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.download = `diagnostics-${stamp}.${fmt}`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.diagnostics.title')}</CardTitle>
        <CardDescription>{t('settings.diagnostics.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Button onClick={take} disabled={loading}>
            {loading ? t('common.loading') : t('settings.diagnostics.take')}
          </Button>
          <Button variant="secondary" onClick={() => download('json')} disabled={downloading}>
            {t('settings.diagnostics.downloadJson')}
          </Button>
          <Button variant="secondary" onClick={() => download('txt')} disabled={downloading}>
            {t('settings.diagnostics.downloadTxt')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t('settings.diagnostics.downloadHint')}</p>

        {snapshot && (
          <div className="space-y-4 text-sm">
            <div className="grid gap-1 sm:grid-cols-2">
              <span>{t('settings.diagnostics.host')}: <b>{snapshot.host.cpu_count} CPU</b>, load {snapshot.host.load_avg?.join(' / ')}</span>
              <span>{t('settings.diagnostics.hostMem')}: <b>{human(snapshot.host.mem_available_bytes)}</b> / {human(snapshot.host.mem_total_bytes)}</span>
              {snapshot.database.error ? (
                <span className="text-destructive sm:col-span-2">{snapshot.database.error}</span>
              ) : (
                <>
                  <span>{t('settings.diagnostics.online')}: <b>{snapshot.database.active_connections}</b> ({snapshot.database.connections_last_hour} {t('settings.diagnostics.perHour')})</span>
                  <span>{t('settings.diagnostics.db')}: <b>{human(snapshot.database.size_bytes ?? null)}</b>, {snapshot.database.users_total} {t('settings.diagnostics.users')}, {snapshot.database.nodes_connected}/{snapshot.database.nodes_total} {t('settings.diagnostics.nodes')}</span>
                  {snapshot.database.activity && (
                    <span className="sm:col-span-2">
                      {t('settings.diagnostics.dbConns')}: {snapshot.database.activity.total}, {t('settings.diagnostics.active')} {snapshot.database.activity.active},
                      {' '}{t('settings.diagnostics.waitingLock')} {snapshot.database.activity.waiting_lock}, {t('settings.diagnostics.longest')} {snapshot.database.activity.longest_active_seconds}s
                    </span>
                  )}
                </>
              )}
            </div>
            {snapshot.collector_error && (
              <p className="text-xs text-amber-500">{snapshot.collector_error}</p>
            )}
            {snapshot.processes.map((p) => (
              <div key={p.pid} className="space-y-2 rounded-md border border-border/40 p-3">
                <div className="flex flex-wrap gap-x-6 gap-y-1">
                  <span><b>{p.app_mode}</b> · pid {p.pid}</span>
                  <span>{t('settings.diagnostics.rss')}: <b>{human(p.rss_bytes)}</b> ({t('settings.diagnostics.peak')} {human(p.rss_peak_bytes)})</span>
                  <span>CPU: {p.cpu_seconds.user}s user / {p.cpu_seconds.system}s sys</span>
                  <span>{t('settings.diagnostics.tasks')}: <b>{p.asyncio_tasks}</b></span>
                </div>
                {p.collector_stats && (
                  <div className="text-xs text-muted-foreground">
                    {t('settings.diagnostics.queue')}: {String(p.collector_stats.pending_users)} ({t('settings.diagnostics.peak')} {String(p.collector_stats.peak_queue_size)}),
                    {' '}{t('settings.diagnostics.lastDrain')}: {String(p.collector_stats.last_drain_duration_ms)} ms,
                    {' '}{t('settings.diagnostics.tasksDropped')}: {String(p.collector_stats.total_tasks_dropped)}
                  </div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-muted-foreground">
                      <tr>
                        <th className="py-1 pr-4">{t('settings.diagnostics.cache')}</th>
                        <th className="py-1 pr-4">{t('settings.diagnostics.items')}</th>
                        <th className="py-1">{t('settings.diagnostics.size')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.caches.filter((c) => c.items > 0).map((c) => (
                        <tr key={c.name} className="border-t border-border/40">
                          <td className="py-1 pr-4 font-mono">{c.name}</td>
                          <td className="py-1 pr-4">{c.items}</td>
                          <td className="py-1">{human(c.bytes)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default MemoryDiagnosticsBlock
