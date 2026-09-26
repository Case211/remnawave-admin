/**
 * NoticeTemplatesTab — тексты предупреждений, которые получает клиент.
 *
 * Шаблон свой на каждый вид нарушения: раздавшему подписку и качающему
 * торренты надо сказать разное. У каждого свой порог скора, выключатель и
 * каналы — Telegram и Email; предупреждение идёт строго по отмеченным. Тексты
 * у каналов раздельные: Telegram понимает только свою урезанную разметку,
 * письму нужна обычная вёрстка (пустое письмо собирается из текста Telegram).
 *
 * Текст уходит живому человеку от имени сервиса и не отзывается, поэтому
 * правка требует того же права, что и блокировка, и пишется в аудит.
 */
import { useEffect, useMemo, useState, type ComponentType } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useHasPermission } from '@/components/PermissionGate'
import { AlertTriangle, Check, Mail, Send, type IconProps } from '@/components/brand/icons'
import { toastMutationError } from '@/lib/mutationToast'
import { telegramMarkupIssues } from '@/lib/telegramHtml'
import { cn } from '@/lib/utils'
import { EmailNoticeEditor, TelegramNoticeEditor } from './NoticeEditors'

interface NoticeTemplate {
  kind: string
  enabled: boolean
  min_score: number
  send_telegram: boolean
  send_email: boolean
  subject_ru: string
  body_ru: string
  email_html_ru?: string | null
  updated_at?: string
  updated_by?: string | null
}

type Draft = Partial<NoticeTemplate>
type Channel = 'telegram' | 'email'

/** Цвет вида нарушения закреплён за именем: раздел должен узнаваться с ходу. */
const KIND_TONE: Record<string, string> = {
  default: 'border-cyan-400/25 bg-cyan-400/12 text-cyan-200',
  traffic_rate: 'border-amber-400/25 bg-amber-400/12 text-amber-200',
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

  const { data, isLoading } = useQuery({
    queryKey: ['violation-notice-templates'],
    queryFn: () => client.get('/violations/notice-templates').then((r) => r.data),
  })

  const templates: NoticeTemplate[] = useMemo(() => data?.items ?? [], [data])

  const save = useMutation({
    mutationFn: ({ kind, patch }: { kind: string; patch: Draft }) =>
      client.patch(`/violations/notice-templates/${kind}`, patch).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['violation-notice-templates'] })
      toast.success(t('violations.notices.saved'))
    },
    onError: (err) => toastMutationError(err, t('common.error')),
  })

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
          <p>{t('violations.notices.hint')}</p>
        </CardContent>
      </Card>

      {templates.map((row) => (
        <NoticeTemplateCard
          key={row.kind}
          row={row}
          canEdit={canEdit}
          saving={save.isPending && save.variables?.kind === row.kind}
          onSave={(patch) => save.mutate({ kind: row.kind, patch })}
        />
      ))}
    </div>
  )
}

interface NoticeTemplateCardProps {
  row: NoticeTemplate
  canEdit: boolean
  saving: boolean
  onSave: (patch: Draft) => void
}

function NoticeTemplateCard({ row, canEdit, saving, onSave }: NoticeTemplateCardProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<Draft>({})
  const [channel, setChannel] = useState<Channel>(row.send_telegram === false ? 'email' : 'telegram')

  // Шаблон сохранили (здесь или в другой вкладке) — черновик устарел. Правка
  // соседнего шаблона свой черновик не сбрасывает.
  useEffect(() => {
    setDraft({})
  }, [row.updated_at])

  const value = <K extends keyof NoticeTemplate>(key: K): NoticeTemplate[K] =>
    (key in draft ? draft[key] : row[key]) as NoticeTemplate[K]
  const edit = (patch: Draft) => setDraft((prev) => ({ ...prev, ...patch }))

  const enabled = value('enabled')
  const sendTelegram = value('send_telegram') !== false
  const sendEmail = Boolean(value('send_email'))
  const body = value('body_ru') || ''
  const issues = useMemo(() => telegramMarkupIssues(body), [body])
  const dirty = Object.keys(draft).length > 0

  return (
    <Card>
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

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <CheckField
            checked={enabled}
            disabled={!canEdit}
            onChange={(checked) => edit({ enabled: checked })}
            label={t('violations.notices.enabled')}
          />
          <span className="hidden h-4 w-px bg-[var(--glass-border)] sm:block" aria-hidden="true" />
          {/* Хотя бы один канал остаётся всегда: выключают предупреждение переключателем выше */}
          <CheckField
            checked={sendTelegram}
            disabled={!canEdit || (sendTelegram && !sendEmail)}
            title={sendTelegram && !sendEmail ? t('violations.notices.lastChannel') : undefined}
            onChange={(checked) => edit({ send_telegram: checked })}
            icon={Send}
            label={t('violations.notices.telegram')}
          />
          <CheckField
            checked={sendEmail}
            disabled={!canEdit || (sendEmail && !sendTelegram)}
            title={sendEmail && !sendTelegram ? t('violations.notices.lastChannel') : undefined}
            onChange={(checked) => edit({ send_email: checked })}
            icon={Mail}
            label={t('violations.notices.email')}
          />
          <label
            className="flex items-center gap-2 text-sm text-dark-200"
            title={t('violations.notices.minScoreHint')}
          >
            {t('violations.notices.minScore')}
            <Input
              type="number"
              min={0}
              max={100}
              value={value('min_score')}
              disabled={!canEdit}
              onChange={(e) => edit({ min_score: Number(e.target.value) })}
              className="h-8 w-20"
            />
          </label>
        </div>

        {enabled && !body.trim() && (
          <p className="text-xs text-amber-300">{t('violations.notices.emptyBody')}</p>
        )}

        <Tabs value={channel} onValueChange={(v) => setChannel(v as Channel)}>
          <TabsList aria-label={t('violations.notices.editorFor')}>
            <TabsTrigger value="telegram" className="gap-1.5">
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
              {t('violations.notices.telegram')}
              {issues.length > 0 && (
                <span className="h-1.5 w-1.5 rounded-full bg-red-400" aria-label={t('violations.notices.issuesTitle')} />
              )}
              {!sendTelegram && <span className="text-[11px] text-dark-300">· {t('violations.notices.channelOff')}</span>}
            </TabsTrigger>
            <TabsTrigger value="email" className="gap-1.5">
              <Mail className="h-3.5 w-3.5" aria-hidden="true" />
              {t('violations.notices.email')}
              {!sendEmail && <span className="text-[11px] text-dark-300">· {t('violations.notices.channelOff')}</span>}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="telegram">
            <TelegramNoticeEditor
              value={body}
              onChange={(next) => edit({ body_ru: next })}
              issues={issues}
              readOnly={!canEdit}
            />
          </TabsContent>
          <TabsContent value="email">
            <EmailNoticeEditor
              subject={value('subject_ru') || ''}
              html={value('email_html_ru') || ''}
              telegramText={body}
              readOnly={!canEdit}
              onSubject={(next) => edit({ subject_ru: next })}
              onHtml={(next) => edit({ email_html_ru: next })}
            />
          </TabsContent>
        </Tabs>

        {dirty && canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              onClick={() => onSave(draft)}
              disabled={saving || issues.length > 0}
              className="gap-1.5"
            >
              <Check className="h-3.5 w-3.5" aria-hidden="true" />
              {t('common.save')}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setDraft({})}>
              {t('common.cancel')}
            </Button>
            {issues.length > 0 && (
              <span className="text-xs text-red-300">{t('violations.notices.saveBlocked')}</span>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

interface CheckFieldProps {
  checked: boolean
  disabled: boolean
  onChange: (checked: boolean) => void
  label: string
  title?: string
  icon?: ComponentType<IconProps>
}

function CheckField({ checked, disabled, onChange, label, title, icon: Icon }: CheckFieldProps) {
  return (
    <label className={cn('flex items-center gap-2 text-sm text-dark-200', disabled && 'cursor-not-allowed')} title={title}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-cyan-400"
      />
      {Icon && <Icon className="h-3.5 w-3.5 text-dark-300" aria-hidden="true" />}
      {label}
    </label>
  )
}
