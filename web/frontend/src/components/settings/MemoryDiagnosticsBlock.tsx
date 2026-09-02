import { useEffect, useRef, useState } from 'react'
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

interface SeriesStatus {
  running: boolean
  started_at: string | null
  finished_at: string | null
  duration_seconds: number
  elapsed_seconds: number
  snapshots_taken: number
  error: string | null
  has_result: boolean
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
  const [series, setSeries] = useState<SeriesStatus | null>(null)
  const [busy, setBusy] = useState(false)
  // Что скачать по окончании сбора, если сбор запустили кнопкой скачивания
  const pendingDownload = useRef<'json' | 'txt' | null>(null)
  const SERIES_MINUTES = 3

  const fetchStatus = async (): Promise<SeriesStatus | null> => {
    try {
      const { data } = await client.get<SeriesStatus>('/diagnostics/series/status')
      setSeries(data)
      return data
    } catch {
      return null
    }
  }

  // При открытии вкладки подхватываем уже идущую серию — сбор живёт на сервере
  useEffect(() => {
    fetchStatus()
  }, [])

  // Пока сбор идёт — опрашиваем каждые 3 с; по окончании показываем итог
  useEffect(() => {
    if (!series?.running) return
    const timer = setInterval(async () => {
      const st = await fetchStatus()
      if (st && !st.running) {
        clearInterval(timer)
        await showResult()
        if (pendingDownload.current) {
          const fmt = pendingDownload.current
          pendingDownload.current = null
          await download(fmt)
        }
      }
    }, 3000)
    return () => clearInterval(timer)
  }, [series?.running])

  const showResult = async () => {
    try {
      const { data } = await client.get('/diagnostics/series/download?fmt=json')
      const snaps: Snapshot[] = data.snapshots || []
      if (snaps.length) setSnapshot(snaps[snaps.length - 1])
    } catch {
      // итог не критичен: файл всё равно можно скачать
    }
  }

  const startSeries = async (thenDownload: 'json' | 'txt' | null) => {
    setBusy(true)
    try {
      const { data } = await client.post<SeriesStatus>('/diagnostics/series/start', { minutes: SERIES_MINUTES })
      pendingDownload.current = thenDownload
      setSeries(data)
    } catch (err: any) {
      if (err.response?.status === 409) {
        // серия уже идёт — просто подхватываем её
        pendingDownload.current = thenDownload
        setSeries(err.response.data)
      } else {
        toast.error(err.response?.data?.detail || err.message)
      }
    } finally {
      setBusy(false)
    }
  }

  const stopSeries = async () => {
    try {
      const { data } = await client.post<SeriesStatus>('/diagnostics/series/stop')
      setSeries(data)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message)
    }
  }

  const download = async (fmt: 'json' | 'txt') => {
    setBusy(true)
    try {
      const res = await client.get(`/diagnostics/series/download?fmt=${fmt}`, { responseType: 'blob' })
      const stamp = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 19)
      const url = URL.createObjectURL(new Blob([res.data]))
      const link = document.createElement('a')
      link.href = url
      link.download = `diagnostics-series-${stamp}.${fmt}`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message)
    } finally {
      setBusy(false)
    }
  }

  const running = !!series?.running
  const progress = series && series.duration_seconds
    ? Math.min(100, Math.round((series.elapsed_seconds / series.duration_seconds) * 100))
    : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.diagnostics.title')}</CardTitle>
        <CardDescription>{t('settings.diagnostics.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {running ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-2 text-sm">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                {t('settings.diagnostics.collecting')}
              </span>
              <Button variant="ghost" size="sm" onClick={stopSeries}>
                {t('settings.diagnostics.stop')}
              </Button>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded bg-muted">
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">
              {t('settings.diagnostics.progress', {
                taken: series?.snapshots_taken ?? 0,
                elapsed: series?.elapsed_seconds ?? 0,
                total: series?.duration_seconds ?? 0,
              })}
            </p>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => startSeries(null)} disabled={busy}>
              {t('settings.diagnostics.take')}
            </Button>
            <Button variant="secondary" onClick={() => (series?.has_result ? download('json') : startSeries('json'))} disabled={busy}>
              {t('settings.diagnostics.downloadJson')}
            </Button>
            <Button variant="secondary" onClick={() => (series?.has_result ? download('txt') : startSeries('txt'))} disabled={busy}>
              {t('settings.diagnostics.downloadTxt')}
            </Button>
          </div>
        )}
        {!running && series?.has_result && (
          <p className="text-xs text-muted-foreground">
            {t('settings.diagnostics.lastSeries', {
              taken: series.snapshots_taken,
              elapsed: series.elapsed_seconds,
            })}
            {series.error ? ` · ${series.error}` : ''}
          </p>
        )}
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
