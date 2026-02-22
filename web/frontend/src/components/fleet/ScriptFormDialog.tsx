/**
 * ScriptFormDialog — Create or edit a custom script.
 */
import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { createScript, updateScript, type ScriptDetail, type ScriptCreate, type ScriptUpdate } from '@/api/fleet'

const CATEGORIES = ['security', 'network', 'system', 'monitoring', 'custom'] as const

interface ScriptFormDialogProps {
  open: boolean
  onClose: () => void
  editingScript: ScriptDetail | null
}

interface FormData {
  name: string
  display_name: string
  description: string
  category: string
  script_content: string
  timeout_seconds: string
  requires_root: boolean
}

const emptyForm: FormData = {
  name: '',
  display_name: '',
  description: '',
  category: 'custom',
  script_content: '#!/bin/bash\nset -e\n\n',
  timeout_seconds: '60',
  requires_root: false,
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9_\s-]/g, '')
    .replace(/[\s-]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

export default function ScriptFormDialog({ open, onClose, editingScript }: ScriptFormDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FormData>({ ...emptyForm })
  const [error, setError] = useState('')

  useEffect(() => {
    if (editingScript) {
      setForm({
        name: editingScript.name,
        display_name: editingScript.display_name,
        description: editingScript.description || '',
        category: editingScript.category,
        script_content: editingScript.script_content,
        timeout_seconds: editingScript.timeout_seconds.toString(),
        requires_root: editingScript.requires_root,
      })
    } else {
      setForm({ ...emptyForm })
    }
    setError('')
  }, [editingScript, open])

  const mutation = useMutation({
    mutationFn: async () => {
      const timeout = parseInt(form.timeout_seconds) || 60
      if (editingScript) {
        const body: ScriptUpdate = {
          display_name: form.display_name,
          description: form.description || undefined,
          category: form.category,
          script_content: form.script_content,
          timeout_seconds: timeout,
          requires_root: form.requires_root,
        }
        return updateScript(editingScript.id, body)
      }
      const body: ScriptCreate = {
        name: form.name || slugify(form.display_name),
        display_name: form.display_name,
        description: form.description || undefined,
        category: form.category,
        script_content: form.script_content,
        timeout_seconds: timeout,
        requires_root: form.requires_root,
      }
      return createScript(body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-scripts'] })
      toast.success(editingScript ? t('fleet.scripts.updated') : t('fleet.scripts.created'))
      onClose()
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
    },
  })

  const isValid = form.display_name.trim() && form.script_content.trim()

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {editingScript ? t('fleet.scripts.editScript') : t('fleet.scripts.createScript')}
          </DialogTitle>
          <DialogDescription>
            {editingScript
              ? t('fleet.scripts.editScriptDescription')
              : t('fleet.scripts.createScriptDescription')}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <Label>{t('fleet.scripts.formDisplayName')} *</Label>
            <Input
              value={form.display_name}
              onChange={(e) => {
                const val = e.target.value
                setForm((prev) => ({
                  ...prev,
                  display_name: val,
                  ...(editingScript ? {} : { name: slugify(val) }),
                }))
              }}
              placeholder="My Custom Script"
              className="mt-1.5"
            />
          </div>

          <div>
            <Label>{t('fleet.scripts.formName')}</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="my_custom_script"
              className="mt-1.5"
              disabled={!!editingScript}
            />
            <p className="text-xs text-dark-300 mt-1">{t('fleet.scripts.formNameHint')}</p>
          </div>

          <div>
            <Label>{t('fleet.scripts.formDescription')}</Label>
            <Input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder={t('fleet.scripts.formDescriptionPlaceholder')}
              className="mt-1.5"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>{t('fleet.scripts.formCategory')}</Label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1.5"
              >
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
            <div>
              <Label>{t('fleet.scripts.formTimeout')}</Label>
              <Input
                type="number"
                min="1"
                max="3600"
                value={form.timeout_seconds}
                onChange={(e) => setForm({ ...form, timeout_seconds: e.target.value })}
                className="mt-1.5"
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Switch
              checked={form.requires_root}
              onCheckedChange={(v) => setForm({ ...form, requires_root: v })}
            />
            <Label>{t('fleet.scripts.formRequiresRoot')}</Label>
          </div>

          <div>
            <Label>{t('fleet.scripts.formContent')} *</Label>
            <Textarea
              value={form.script_content}
              onChange={(e) => setForm({ ...form, script_content: e.target.value })}
              className="mt-1.5 font-mono text-xs min-h-[200px] resize-y"
              placeholder="#!/bin/bash"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !isValid}>
            {mutation.isPending
              ? t('common.saving')
              : editingScript
                ? t('common.save')
                : t('common.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
