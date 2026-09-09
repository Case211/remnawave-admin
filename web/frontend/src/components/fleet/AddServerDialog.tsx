import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Copy, ShieldCheck, Server } from '@/components/brand/icons'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import client from '@/api/client'

interface CreatedServer {
  uuid: string
  name: string
  install_command: string
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Свой сервер в мониторинг: бот, панель, база — что угодно с Docker.
 * Бэкенд заводит строку nodes с is_external, выдаёт токен агента и возвращает
 * готовую команду установки; агент на таком сервере живёт без Xray.
 */
export default function AddServerDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [address, setAddress] = useState('')
  const [description, setDescription] = useState('')
  const [created, setCreated] = useState<CreatedServer | null>(null)
  const [copied, setCopied] = useState(false)

  const create = useMutation({
    mutationFn: async () => {
      const { data } = await client.post('/nodes/external', {
        name: name.trim(),
        address: address.trim(),
        description: description.trim() || null,
      })
      return data as CreatedServer
    },
    onSuccess: (data) => {
      setCreated(data)
      queryClient.invalidateQueries({ queryKey: ['fleet'] })
      toast.success(t('fleet.server.createdToast', { name: data.name }))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(t('fleet.server.createFailed'), { description: err.response?.data?.detail || err.message })
    },
  })

  const reset = () => {
    setName('')
    setAddress('')
    setDescription('')
    setCreated(null)
    setCopied(false)
  }

  const handleOpenChange = (next: boolean) => {
    if (!next) reset()
    onOpenChange(next)
  }

  const copyCommand = async () => {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.install_command)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('fleet.server.copyFailed'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Server className="w-5 h-5 text-sky-400" />
            {t('fleet.server.title')}
          </DialogTitle>
          <DialogDescription>{t('fleet.server.description')}</DialogDescription>
        </DialogHeader>

        {!created ? (
          <form
            className="space-y-4"
            onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate() }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="ext-server-name">{t('fleet.server.name')}</Label>
              <Input
                id="ext-server-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('fleet.server.namePlaceholder')}
                maxLength={100}
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ext-server-address">{t('fleet.server.address')}</Label>
              <Input
                id="ext-server-address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="203.0.113.10"
                maxLength={255}
              />
              <p className="text-xs text-dark-300">{t('fleet.server.addressHint')}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ext-server-note">{t('fleet.server.note')}</Label>
              <Textarea
                id="ext-server-note"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('fleet.server.notePlaceholder')}
                maxLength={500}
                rows={2}
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => handleOpenChange(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={!name.trim() || create.isPending}>
                {create.isPending ? t('fleet.server.creating') : t('fleet.server.create')}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm text-green-400">
              <ShieldCheck className="w-4 h-4" />
              {t('fleet.server.created', { name: created.name })}
            </div>
            <pre className="whitespace-pre-wrap break-all rounded-lg bg-[var(--glass-bg)] p-3 text-xs font-mono text-dark-100 select-all">
              {created.install_command}
            </pre>
            <p className="text-xs text-dark-300">{t('fleet.server.installHint')}</p>
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={copyCommand}>
                <Copy className="w-4 h-4 mr-2" />
                {copied ? t('fleet.server.copied') : t('fleet.server.copy')}
              </Button>
              <Button type="button" onClick={() => handleOpenChange(false)}>
                {t('common.close')}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
