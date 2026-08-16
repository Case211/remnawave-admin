import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ArrowLeft, Check, Plus, Smartphone, X } from '@/components/brand/icons'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

import {
  fetchClientReference,
  fetchSubmissions,
  proposeChange,
  voteSubmission,
} from './api'
import { CardSkeleton, Skeleton } from './primitives'
import type { ClientApp, Submission, SubmissionIn } from './types'

/**
 * /plugins/smart-support/clients — общий справочник клиентских приложений.
 *
 * Актуальные версии и баги версий ведут все панели вместе: одна предлагает
 * правку, остальные подтверждают или возражают. В справочник правка попадает
 * решением владельца сервера — счётчик согласных здесь для того, чтобы это
 * решение было на что опереть, а не чтобы пропускать автоматически: неверная
 * «актуальная версия» означает ложное «клиент устарел» разом у всех.
 *
 * Отчёт берёт эти данные сам; страница нужна, чтобы видеть, с чем он
 * сравнивает, и чинить это, когда справочник отстал от жизни.
 */
export default function ClientsPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [proposeFor, setProposeFor] = useState<{ kind: 'app' | 'issue'; appId: string } | null>(null)

  const reference = useQuery({
    queryKey: ['smart-support-clients'],
    queryFn: fetchClientReference,
    retry: false,
    staleTime: 60_000,
  })

  const submissions = useQuery({
    queryKey: ['smart-support-submissions'],
    queryFn: () => fetchSubmissions('all'),
    retry: false,
    staleTime: 15_000,
  })

  const vote = useMutation({
    mutationFn: ({ id, value }: { id: number; value: number }) => voteSubmission(id, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['smart-support-submissions'] }),
    onError: () => toast.error(t('plugins.smart_support.clients.vote_failed')),
  })

  const open = useMemo(
    () => (submissions.data?.submissions ?? []).filter((s) => s.status === 'pending'),
    [submissions.data],
  )
  const decided = useMemo(
    () => (submissions.data?.submissions ?? []).filter((s) => s.status !== 'pending'),
    [submissions.data],
  )

  return (
    <div className="space-y-6">
      <Link
        to="/plugins/smart-support"
        className="inline-flex items-center gap-1.5 text-sm text-dark-300 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        {t('plugins.smart_support.clients.back')}
      </Link>

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-white flex items-center gap-2">
            <Smartphone className="w-5 h-5 text-emerald-400" aria-hidden />
            {t('plugins.smart_support.clients.title')}
          </h1>
          <p className="mt-1 text-sm text-dark-300">
            {t('plugins.smart_support.clients.subtitle')}
          </p>
        </div>
        <Button size="sm" onClick={() => setProposeFor({ kind: 'app', appId: '' })}>
          <Plus className="w-4 h-4 mr-1.5" />
          {t('plugins.smart_support.clients.propose')}
        </Button>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
          {t('plugins.smart_support.clients.queue')}
          {open.length > 0 && (
            <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-primary-500/20 text-primary-300">
              {open.length}
            </span>
          )}
        </h2>

        {submissions.isLoading ? (
          <CardSkeleton rows={2} />
        ) : open.length === 0 ? (
          <p className="text-sm text-dark-400">{t('plugins.smart_support.clients.queue_empty')}</p>
        ) : (
          open.map((s) => (
            <SubmissionCard
              key={s.id}
              submission={s}
              busy={vote.isPending}
              onVote={(value) => vote.mutate({ id: s.id, value })}
            />
          ))
        )}

        {decided.length > 0 && (
          <details className="text-sm text-dark-300">
            <summary className="cursor-pointer py-1">
              {t('plugins.smart_support.clients.decided', { n: decided.length })}
            </summary>
            <div className="mt-2 space-y-2">
              {decided.map((s) => (
                <SubmissionCard key={s.id} submission={s} busy readOnly onVote={() => {}} />
              ))}
            </div>
          </details>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
          {t('plugins.smart_support.clients.reference')}
        </h2>

        {reference.isLoading ? (
          <>
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </>
        ) : (reference.data?.apps.length ?? 0) === 0 ? (
          <p className="text-sm text-dark-400">
            {t('plugins.smart_support.clients.reference_empty')}
          </p>
        ) : (
          <div className="glass-card divide-y divide-[var(--glass-border)]">
            {reference.data?.apps.map((app) => (
              <AppRow
                key={app.id}
                app={app}
                onPropose={(kind) => setProposeFor({ kind, appId: app.id })}
              />
            ))}
          </div>
        )}
      </section>

      {proposeFor && (
        <ProposeDialog
          kind={proposeFor.kind}
          appId={proposeFor.appId}
          onClose={() => setProposeFor(null)}
          onSent={() => {
            setProposeFor(null)
            qc.invalidateQueries({ queryKey: ['smart-support-submissions'] })
            toast.success(t('plugins.smart_support.clients.proposed'))
          }}
        />
      )}
    </div>
  )
}

/** Строка справочника: во что сейчас верит отчёт по этому приложению. */
function AppRow({ app, onPropose }: { app: ClientApp; onPropose: (kind: 'app' | 'issue') => void }) {
  const { t } = useTranslation()
  return (
    <div className="p-3 flex flex-wrap items-center gap-3">
      <div className="min-w-0 flex-1">
        <div className="text-sm text-white truncate">{app.title || app.id}</div>
        <div className="text-[11px] font-mono text-dark-400 truncate">{app.id}</div>
      </div>

      <div className="text-sm">
        {app.ambiguous ? (
          // Нумерация сборок разная — сравнивать версии нельзя, и отчёт этого
          // не делает; показываем причину, а не пустоту.
          <span className="text-dark-400">{t('plugins.smart_support.clients.ambiguous')}</span>
        ) : app.latest_version ? (
          <span className="text-dark-100 tabular-nums">{app.latest_version}</span>
        ) : (
          <span className="text-dark-400">{t('plugins.smart_support.clients.no_version')}</span>
        )}
      </div>

      {app.issues.length > 0 && (
        <span
          className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300"
          title={app.issues.map((i) => i.title).join('\n')}
        >
          {t('plugins.smart_support.clients.issues', { n: app.issues.length })}
        </span>
      )}

      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => onPropose('app')}>
          {t('plugins.smart_support.clients.fix_version')}
        </Button>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => onPropose('issue')}>
          {t('plugins.smart_support.clients.report_bug')}
        </Button>
      </div>
    </div>
  )
}

/** Карточка правки: что предлагают, сколько панелей согласно, свой голос. */
function SubmissionCard({
  submission,
  onVote,
  busy,
  readOnly,
}: {
  submission: Submission
  onVote: (value: number) => void
  busy: boolean
  readOnly?: boolean
}) {
  const { t } = useTranslation()
  const p = submission.payload as Record<string, string | boolean | undefined>
  const parts: string[] = []
  if (submission.kind === 'app') {
    if (p.latest_version) parts.push(`${t('plugins.smart_support.clients.version')} ${p.latest_version}`)
    if (p.title) parts.push(String(p.title))
    if (p.ambiguous) parts.push(t('plugins.smart_support.clients.ambiguous'))
  } else {
    if (p.title) parts.push(String(p.title))
    parts.push(`${p.version_min || '…'} — ${p.version_max || '…'}`)
    if (p.platform) parts.push(String(p.platform))
  }

  return (
    <div className="glass-card p-3 flex flex-wrap items-center gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs text-dark-300">{submission.app_id}</span>
          <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-300">
            {t(`plugins.smart_support.clients.kind.${submission.kind}`)}
          </span>
          {submission.mine && (
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary-500/15 text-primary-300">
              {t('plugins.smart_support.clients.mine')}
            </span>
          )}
          {submission.status !== 'pending' && (
            <span
              className={cn(
                'text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded',
                submission.status === 'accepted'
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'bg-dark-500/20 text-dark-300',
              )}
            >
              {t(`plugins.smart_support.clients.status.${submission.status}`)}
            </span>
          )}
        </div>
        <div className="mt-1 text-sm text-white">{parts.join(' · ')}</div>
        {submission.comment && (
          <div className="text-xs text-dark-400">{submission.comment}</div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span
          className="text-xs text-dark-300"
          title={t('plugins.smart_support.clients.votes_hint')}
        >
          <Check className="inline w-3.5 h-3.5 text-emerald-400 mr-1" />
          {t('plugins.smart_support.clients.agree_count', { n: submission.votes_up })}
          {submission.votes_down > 0 && (
            <span className="ml-2 text-dark-400">−{submission.votes_down}</span>
          )}
        </span>

        {/* За своё не голосуют: автор согласен по определению, и его голос
            только раздувал бы счётчик, ничего не подтверждая. */}
        {!readOnly && !submission.mine && (
          <div className="flex items-center gap-1">
            <Button
              variant={submission.my_vote === 1 ? 'default' : 'outline'}
              size="sm"
              className="h-7 px-2"
              disabled={busy}
              onClick={() => onVote(submission.my_vote === 1 ? 0 : 1)}
              aria-label={t('plugins.smart_support.clients.agree')}
              title={t('plugins.smart_support.clients.agree')}
            >
              <Check className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant={submission.my_vote === -1 ? 'default' : 'outline'}
              size="sm"
              className="h-7 px-2"
              disabled={busy}
              onClick={() => onVote(submission.my_vote === -1 ? 0 : -1)}
              aria-label={t('plugins.smart_support.clients.disagree')}
              title={t('plugins.smart_support.clients.disagree')}
            >
              <X className="w-3.5 h-3.5" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

/** Форма правки: версия приложения либо баг конкретных версий. */
function ProposeDialog({
  kind: initialKind,
  appId: initialAppId,
  onClose,
  onSent,
}: {
  kind: 'app' | 'issue'
  appId: string
  onClose: () => void
  onSent: () => void
}) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<'app' | 'issue'>(initialKind)
  const [appId, setAppId] = useState(initialAppId)
  const [comment, setComment] = useState('')
  const [version, setVersion] = useState('')
  const [ambiguous, setAmbiguous] = useState(false)
  const [title, setTitle] = useState('')
  const [versionMin, setVersionMin] = useState('')
  const [versionMax, setVersionMax] = useState('')
  const [workaround, setWorkaround] = useState('')

  const send = useMutation({
    mutationFn: (body: SubmissionIn) => proposeChange(body),
    onSuccess: onSent,
    onError: () => toast.error(t('plugins.smart_support.clients.propose_failed')),
  })

  const valid = appId.trim().length > 0 && (kind === 'app' ? true : title.trim().length > 0)

  const submit = () => {
    const payload =
      kind === 'app'
        ? { latest_version: version.trim(), ambiguous }
        : {
            title: title.trim(),
            version_min: versionMin.trim(),
            version_max: versionMax.trim(),
            workaround: workaround.trim(),
          }
    send.mutate({ kind, app_id: appId.trim(), payload, comment: comment.trim() })
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('plugins.smart_support.clients.propose_title')}</DialogTitle>
          <DialogDescription>
            {t('plugins.smart_support.clients.propose_hint')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-1 p-1 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] w-fit">
          {(['app', 'issue'] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={cn(
                'px-3 py-1 text-xs font-medium rounded-md transition-colors',
                kind === k ? 'bg-primary-500/25 text-white' : 'text-dark-300 hover:text-white',
              )}
            >
              {t(`plugins.smart_support.clients.kind.${k}`)}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs text-dark-300">
              {t('plugins.smart_support.clients.app_id')}
            </Label>
            <Input
              value={appId}
              onChange={(e) => setAppId(e.target.value)}
              placeholder="Happ"
              className="h-8 text-xs"
            />
            <p className="text-[11px] text-dark-400">
              {t('plugins.smart_support.clients.app_id_hint')}
            </p>
          </div>

          {kind === 'app' ? (
            <>
              <div className="space-y-1">
                <Label className="text-xs text-dark-300">
                  {t('plugins.smart_support.clients.latest_version')}
                </Label>
                <Input
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  placeholder="3.19.0"
                  className="h-8 text-xs"
                />
              </div>
              <div className="flex items-center gap-3">
                <Switch id="ambiguous" checked={ambiguous} onCheckedChange={setAmbiguous} />
                <Label htmlFor="ambiguous" className="text-xs text-dark-200">
                  {t('plugins.smart_support.clients.ambiguous_label')}
                </Label>
              </div>
            </>
          ) : (
            <>
              <div className="space-y-1">
                <Label className="text-xs text-dark-300">
                  {t('plugins.smart_support.clients.bug_title')}
                </Label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label className="text-xs text-dark-300">
                    {t('plugins.smart_support.clients.version_min')}
                  </Label>
                  <Input
                    value={versionMin}
                    onChange={(e) => setVersionMin(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-dark-300">
                    {t('plugins.smart_support.clients.version_max')}
                  </Label>
                  <Input
                    value={versionMax}
                    onChange={(e) => setVersionMax(e.target.value)}
                    className="h-8 text-xs"
                  />
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-dark-300">
                  {t('plugins.smart_support.clients.workaround')}
                </Label>
                <Input
                  value={workaround}
                  onChange={(e) => setWorkaround(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
            </>
          )}

          <div className="space-y-1">
            <Label className="text-xs text-dark-300">
              {t('plugins.smart_support.clients.comment')}
            </Label>
            <Input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="h-8 text-xs"
            />
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button size="sm" onClick={submit} disabled={!valid || send.isPending}>
            {t('plugins.smart_support.clients.send')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
