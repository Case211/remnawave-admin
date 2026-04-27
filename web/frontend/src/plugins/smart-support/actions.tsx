import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

import { executeAction, fetchActions } from './api'
import type {
  ActionExecuteOut,
  ActionMetadata,
  ActionParamSpec,
} from './types'

/**
 * Maps the rule engine's ``suggested_action`` strings to action ids
 * the plugin actually exposes. ``null`` means "advisory only, no
 * button" — e.g. ``switch_node`` is operator guidance, not something
 * we automate.
 */
const SUGGESTED_TO_ACTION: Record<string, string | null> = {
  switch_node: null,
  notify_update: null,
  reset_traffic: 'reset_traffic',
  extend_subscription: 'extend_subscription',
  revoke: 'revoke_subscription',
  revoke_subscription: 'revoke_subscription',
  disable: 'disable_user',
  disable_user: 'disable_user',
  enable_user: 'enable_user',
  disconnect: 'disconnect_user',
  disconnect_user: 'disconnect_user',
}


export function useActionsCatalog() {
  return useQuery({
    queryKey: ['smart-support-actions'],
    queryFn: fetchActions,
    staleTime: 5 * 60_000,
    retry: false,
  })
}


/**
 * Hook giving callers a tiny imperative API: ``run(actionId, params)``.
 * The hook itself doesn't open dialogs — it just fires the mutation.
 * For confirmation, use :func:`ActionLauncher`.
 */
export function useRunAction(opts: { userUuid: string; ruleId?: string | null }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ actionId, params }: { actionId: string; params: Record<string, unknown> }) =>
      executeAction(actionId, {
        user_uuid: opts.userUuid,
        params,
        triggered_by_rule_id: opts.ruleId ?? null,
      }),
    onSuccess: (data: ActionExecuteOut) => {
      toast.success(data.message || t('plugins.smart_support.actions.success'))
      // Invalidate the report so the UI reflects the new state.
      qc.invalidateQueries({ queryKey: ['smart-support-report', opts.userUuid] })
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail
      const msg = detail?.message || t('plugins.smart_support.actions.error')
      toast.error(msg)
    },
  })
}


/**
 * One-shot button that runs an action through the proper confirm/params
 * flow. Used both inside HypothesisRow (small inline button) and inside
 * QuickActionsCard (row of buttons).
 *
 * If the action requires a confirmation or a parameter input, a dialog
 * pops first; otherwise we run immediately.
 */
export function ActionLauncher({
  meta,
  userUuid,
  ruleId,
  variant = 'default',
  size = 'sm',
  className,
  children,
}: {
  meta: ActionMetadata
  userUuid: string
  ruleId?: string | null
  variant?: 'default' | 'outline' | 'destructive' | 'secondary'
  size?: 'sm' | 'default'
  className?: string
  children?: React.ReactNode
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [params, setParams] = useState<Record<string, unknown>>(() => initParams(meta.params))

  const mutation = useRunAction({ userUuid, ruleId })

  const needsDialog = meta.requires_confirmation || meta.params.length > 0

  const onTrigger = () => {
    if (!needsDialog) {
      mutation.mutate({ actionId: meta.id, params: {} })
      return
    }
    setParams(initParams(meta.params))
    setOpen(true)
  }

  const onConfirm = () => {
    mutation.mutate({ actionId: meta.id, params })
    setOpen(false)
  }

  const resolvedVariant: NonNullable<typeof variant> =
    meta.severity === 'destructive' && variant === 'default' ? 'destructive' : variant

  return (
    <>
      <Button
        variant={resolvedVariant}
        size={size}
        onClick={onTrigger}
        disabled={mutation.isPending}
        className={className}
      >
        {mutation.isPending && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
        {children ?? t(meta.title_i18n)}
      </Button>

      {needsDialog && (
        <AlertDialog open={open} onOpenChange={setOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t(meta.title_i18n)}</AlertDialogTitle>
              <AlertDialogDescription>
                {meta.severity === 'destructive'
                  ? t('plugins.smart_support.actions.confirm_destructive')
                  : t('plugins.smart_support.actions.confirm_safe')}
              </AlertDialogDescription>
            </AlertDialogHeader>

            {meta.params.length > 0 && (
              <div className="space-y-3 py-2">
                {meta.params.map((p) => (
                  <ParamInput
                    key={p.name}
                    spec={p}
                    value={params[p.name]}
                    onChange={(v) => setParams((prev) => ({ ...prev, [p.name]: v }))}
                  />
                ))}
              </div>
            )}

            <AlertDialogFooter>
              <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
              <AlertDialogAction
                onClick={onConfirm}
                className={
                  meta.severity === 'destructive'
                    ? 'bg-red-500 hover:bg-red-600 text-white'
                    : ''
                }
              >
                {t('plugins.smart_support.actions.run')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </>
  )
}


function ParamInput({
  spec,
  value,
  onChange,
}: {
  spec: ActionParamSpec
  value: unknown
  onChange: (v: unknown) => void
}) {
  const { t } = useTranslation()
  const label = spec.label_i18n ? t(spec.label_i18n) : spec.name

  if (spec.type === 'boolean') {
    return (
      <div className="flex items-center gap-3">
        <Switch
          id={`p-${spec.name}`}
          checked={!!value}
          onCheckedChange={(v) => onChange(v)}
        />
        <Label htmlFor={`p-${spec.name}`} className="text-sm">
          {label}
        </Label>
      </div>
    )
  }
  if (spec.type === 'number') {
    return (
      <div className="space-y-1.5">
        <Label className="text-xs text-dark-300">{label}</Label>
        <Input
          type="number"
          value={value === undefined || value === null ? '' : String(value)}
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        />
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-dark-300">{label}</Label>
      <Input
        type="text"
        value={value === undefined || value === null ? '' : String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}


function initParams(specs: ActionParamSpec[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const s of specs) {
    if (s.default !== undefined && s.default !== null) {
      out[s.name] = s.default
    }
  }
  return out
}


export function actionForSuggested(suggested: string | null | undefined): string | null {
  if (!suggested) return null
  return SUGGESTED_TO_ACTION[suggested] ?? null
}


export function useActionByIdFinder() {
  const { data } = useActionsCatalog()
  return useMemo(() => {
    const map = new Map<string, ActionMetadata>()
    for (const a of data?.actions ?? []) {
      map.set(a.id, a)
    }
    return (id: string | null | undefined) => (id ? map.get(id) ?? null : null)
  }, [data])
}
