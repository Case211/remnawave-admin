/**
 * NoticeTemplatesTab — тексты предупреждений, которые получает клиент.
 *
 * Шаблон свой на каждый вид нарушения: раздавшему подписку и качающему
 * торренты надо сказать разное. У каждого свой порог скора и выключатель —
 * оператор решает, о чём вообще предупреждать, а о чём молчать.
 *
 * Текст уходит живому человеку от имени сервиса и не отзывается, поэтому
 * правка требует того же права, что и блокировка, и пишется в аудит.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useHasPermission } from '@/components/PermissionGate'
import { AlertTriangle, Check, Mail } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

interface NoticeTemplate {
  kind: string
  enabled: boolean
  min_score: number
  send_email: boolean
  subject_ru: string
  body_ru: string
  updated_at?: string
  updated_by?: string | null
}

/** Цвет вида нарушения закреплён за именем: раздел должен узнаваться с ходу. */
const KIND_TONE: Record<string, string> = {
  default: 'border-cyan-400/25 bg-cyan-400/12 text-cyan-200',
  temporal: 'border-violet-400/25 bg-violet-400/12 text-violet-200',
  geo: 'border-sky-400/25 bg-sky-400/12 text-sky-200',
  asn: 'border-emerald-400/25 bg-emerald-400/12 text-emerald-200',
  profile: 'border-amber-400/25 bg-amber-400/12 text-amber-200',
  device: 'border-rose-400/25 bg-rose-400/12 text-rose-200',
  hwid: 'border-rose-400/25 bg-rose-400/12 text-rose-200',
  user_agent: 'border-violet-400/25 bg-violet-400/12 text-violet-200',
  torrent: 'border-orange-400/25 bg-orange-400/12 text-orange-200',
}

export function NoticeTemplatesTab() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canEdit = useHasPermission('violations', 'resolve')
  const [drafts, setDrafts] = useState<Record<string, Partial<NoticeTemplate>>>({})

  const { data, isLoading } = useQuery({
    queryKey: ['violation-notice-templates'],
    queryFn: () => client.get('/violations/notice-templates').then((r) => r.data),
  })

  const templates: NoticeTemplate[] = useMemo(() => data?.items ?? [], [data])

  // Пришли свежие данные — забытые черновики не должны их перекрывать.
  useEffect(() => {
    setDrafts({})
  }, [data])

  const save = useMutation({
    mutationFn: ({ kind, patch }: { kind: string; patch: Partial<NoticeTemplate> }) =>
      client.patch(`/violations/notice-templates/${kind}`, patch).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['violation-notice-templates'] })
      toast.success(t('violations.notices.saved'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const patchOf = (kind: string) => drafts[kind] ?? {}
  const valueOf = <K extends keyof NoticeTemplate>(row: NoticeTemplate, key: K): NoticeTemplate[K] =>
    (patchOf(row.kind)[key] as NoticeTemplate[K]) ?? row[key]
  const dirty = (kind: string) => Object.keys(patchOf(kind)).length > 0

  const edit = (kind: string, patch: Partial<NoticeTemplate>) =>
    setDrafts((prev) => ({ ...prev, [kind]: { ...prev[kind], ...patch } }))

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="flex items-start gap-3 p-4 text-sm text-dark-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-300" aria-hidden="true" />
          <p>
            {t('violations.notices.hint')}
          </p>
        </CardContent>
      </Card>

      {templates.map((row) => {
        const enabled = valueOf(row, 'enabled')
        return (
          <Card key={row.kind}>
            <CardContent className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold',
                    KIND_TONE[row.kind] || KIND_TONE.default,
                  )}
                >
                  {t(`violations.notices.kinds.${row.kind}`, { defaultValue: row.kind })}
                </span>
                {!enabled && (
                  <span className="rounded-full bg-[var(--glass-bg)] px-2 py-0.5 text-[11px] text-dark-300">
                    {t('violations.notices.off')}
                  </span>
                )}
                <span className="flex-1" />
                {row.updated_by && (
                  <span className="text-[11px] text-dark-300">
                    {t('violations.notices.updatedBy', { name: row.updated_by })}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-2 text-sm text-dark-200">
                  <input
                    type="checkbox"
                    checked={enabled}
                    disabled={!canEdit}
                    onChange={(e) => edit(row.kind, { enabled: e.target.checked })}
                    className="h-4 w-4 accent-cyan-400"
                  />
                  {t('violations.notices.enabled')}
                </label>

                <label className="flex items-center gap-2 text-sm text-dark-200">
                  <Mail className="h-3.5 w-3.5 text-dark-300" aria-hidden="true" />
                  <input
                    type="checkbox"
                    checked={valueOf(row, 'send_email')}
                    disabled={!canEdit}
                    onChange={(e) => edit(row.kind, { send_email: e.target.checked })}
                    className="h-4 w-4 accent-cyan-400"
                  />
                  {t('violations.notices.alsoEmail')}
                </label>

                <label className="flex items-center gap-2 text-sm text-dark-200">
                  {t('violations.notices.minScore')}
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={valueOf(row, 'min_score')}
                    disabled={!canEdit}
                    onChange={(e) => edit(row.kind, { min_score: Number(e.target.value) })}
                    className="h-8 w-20"
                  />
                </label>
              </div>

              <Input
                value={valueOf(row, 'subject_ru') || ''}
                disabled={!canEdit}
                placeholder={t('violations.notices.subjectPlaceholder')}
                onChange={(e) => edit(row.kind, { subject_ru: e.target.value })}
                className="h-9"
              />

              <textarea
                value={valueOf(row, 'body_ru') || ''}
                disabled={!canEdit}
                placeholder={t('violations.notices.bodyPlaceholder')}
                onChange={(e) => edit(row.kind, { body_ru: e.target.value })}
                rows={5}
                className="w-full resize-y rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] p-3 text-sm text-dark-100 outline-none focus:border-cyan-400/40 focus-visible:ring-2 focus-visible:ring-cyan-400/60"
              />

              {dirty(row.kind) && canEdit && (
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => save.mutate({ kind: row.kind, patch: patchOf(row.kind) })}
                    disabled={save.isPending}
                    className="gap-1.5"
                  >
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('common.save')}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDrafts((prev) => ({ ...prev, [row.kind]: {} }))}
                  >
                    {t('common.cancel')}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
