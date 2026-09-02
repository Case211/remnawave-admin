import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import client from '../../api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface CacheEntry {
  name: string
  items: number
  bytes: number
  note?: string
}

interface Snapshot {
  taken_at: string
  rss_bytes: number | null
  asyncio_tasks: number
  gc_counts: number[]
  caches: CacheEntry[]
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
  const [chatId, setChatId] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)

  const take = async () => {
    setLoading(true)
    try {
      const { data } = await client.get<Snapshot>('/api/v2/diagnostics/memory')
      setSnapshot(data)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message)
    } finally {
      setLoading(false)
    }
  }

  const send = async () => {
    setSending(true)
    try {
      const { data } = await client.post('/api/v2/diagnostics/memory/send', {
        chat_id: chatId.trim() || undefined,
      })
      setSnapshot(data.snapshot)
      toast.success(t('settings.diagnostics.sent'))
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message)
    } finally {
      setSending(false)
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
          <Input
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            placeholder={t('settings.diagnostics.chatPlaceholder')}
            className="max-w-[220px]"
          />
          <Button variant="secondary" onClick={send} disabled={sending}>
            {sending ? t('common.loading') : t('settings.diagnostics.send')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t('settings.diagnostics.chatHint')}</p>

        {snapshot && (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-x-6 gap-y-1">
              <span>{t('settings.diagnostics.rss')}: <b>{human(snapshot.rss_bytes)}</b></span>
              <span>{t('settings.diagnostics.tasks')}: <b>{snapshot.asyncio_tasks}</b></span>
            </div>
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
                  {snapshot.caches.map((c) => (
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
        )}
      </CardContent>
    </Card>
  )
}

export default MemoryDiagnosticsBlock
