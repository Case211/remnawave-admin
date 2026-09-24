import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Pencil, Plus, Trash2 } from '@/components/brand/icons'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { supportExtraApi, type SupportMacro, type MacroInput } from '@/api/support'

/** Подстановки, которые понимает applyMacro на странице обращений */
export const MACRO_PLACEHOLDERS = ['name', 'ticket', 'expires', 'days_left', 'balance', 'devices'] as const

const STATUSES = ['', 'open', 'answered', 'pending', 'closed'] as const

const EMPTY: MacroInput = { title: '', body: '', shortcut: null, set_status: null, add_tag_id: null, sort_order: 0 }

export function MacroManager({
  open,
  onOpenChange,
  macros,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  macros: SupportMacro[]
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<SupportMacro | null>(null)
  const [form, setForm] = useState<MacroInput | null>(null)
  const [deleting, setDeleting] = useState<SupportMacro | null>(null)

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['support-macros'] })

  const saveMutation = useMutation({
    mutationFn: (data: MacroInput) =>
      editing ? supportExtraApi.updateMacro(editing.id, data) : supportExtraApi.createMacro(data),
    onSuccess: () => {
      refresh()
      toast.success(t('support.macros.saved'))
      setForm(null)
      setEditing(null)
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => supportExtraApi.deleteMacro(id),
    onSuccess: () => {
      refresh()
      setDeleting(null)
    },
    onError: () => toast.error(t('common.error')),
  })

  const startEdit = (macro: SupportMacro | null) => {
    setEditing(macro)
    setForm(macro
      ? { title: macro.title, body: macro.body, shortcut: macro.shortcut, set_status: macro.set_status,
          add_tag_id: macro.add_tag_id, sort_order: macro.sort_order }
      : { ...EMPTY, sort_order: macros.length })
  }

  const insertPlaceholder = (name: string) => {
    if (!form) return
    setForm({ ...form, body: `${form.body}{{${name}}}` })
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) { setForm(null); setEditing(null) } }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('support.macros.title')}</DialogTitle>
            <DialogDescription>{t('support.macros.description')}</DialogDescription>
          </DialogHeader>

          {form ? (
            <div className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="macro-title">{t('support.macros.name')}</Label>
                  <Input id="macro-title" value={form.title} maxLength={120}
                    onChange={(e) => setForm({ ...form, title: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="macro-shortcut">{t('support.macros.shortcut')}</Label>
                  <Input id="macro-shortcut" value={form.shortcut ?? ''} maxLength={32} placeholder="/greet"
                    onChange={(e) => setForm({ ...form, shortcut: e.target.value.trim() || null })} />
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="macro-body">{t('support.macros.body')}</Label>
                <Textarea id="macro-body" value={form.body} rows={6} maxLength={4000}
                  onChange={(e) => setForm({ ...form, body: e.target.value })} />
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {MACRO_PLACEHOLDERS.map((name) => (
                    <button
                      key={name}
                      type="button"
                      onClick={() => insertPlaceholder(name)}
                      title={t(`support.macros.placeholders.${name}`)}
                      className="rounded border border-[var(--glass-border)] px-1.5 py-0.5 font-mono text-[11px] text-dark-200 hover:text-white"
                    >
                      {`{{${name}}}`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor="macro-status">{t('support.macros.setStatus')}</Label>
                <select
                  id="macro-status"
                  value={form.set_status ?? ''}
                  onChange={(e) => setForm({ ...form, set_status: e.target.value || null })}
                  className="w-full rounded-md border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm"
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{s ? t(`support.status.${s}`) : t('support.macros.keepStatus')}</option>
                  ))}
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" onClick={() => { setForm(null); setEditing(null) }}>{t('common.cancel')}</Button>
                <Button
                  onClick={() => saveMutation.mutate(form)}
                  disabled={!form.title.trim() || !form.body.trim() || saveMutation.isPending}
                >
                  {t('common.save')}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {macros.length === 0 && (
                <p className="py-4 text-center text-sm text-dark-300">{t('support.macros.empty')}</p>
              )}
              {macros.map((macro) => (
                <div key={macro.id} className="flex items-start gap-3 rounded-lg border border-[var(--glass-border)] p-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-white">
                      {macro.title}
                      {macro.shortcut && <span className="ml-2 font-mono text-xs text-dark-300">{macro.shortcut}</span>}
                    </p>
                    <p className="mt-0.5 line-clamp-2 text-xs text-dark-300">{macro.body}</p>
                  </div>
                  <Button variant="ghost" size="icon" aria-label={t('common.edit')} onClick={() => startEdit(macro)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={t('common.delete')} onClick={() => setDeleting(macro)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button variant="outline" className="w-full gap-1.5" onClick={() => startEdit(null)}>
                <Plus className="h-4 w-4" />
                {t('support.macros.add')}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleting != null}
        onOpenChange={(v) => { if (!v) setDeleting(null) }}
        title={t('support.macros.deleteTitle')}
        description={t('support.macros.deleteDescription', { title: deleting?.title ?? '' })}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
      />
    </>
  )
}
