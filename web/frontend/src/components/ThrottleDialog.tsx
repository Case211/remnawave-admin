import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import client from '../api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export interface ThrottleItem {
  user_uuid: string
  username: string | null
  rate_kbit: number
  reason: string | null
  created_by_username: string | null
  created_at: string
  until: string | null
}

export const fetchThrottles = async (): Promise<{ items: ThrottleItem[]; total: number }> => {
  const { data } = await client.get('/violations/throttles')
  return data
}

/** Действующее ограничение пользователя, если есть. Список маленький, отдельной ручки нет. */
export function useActiveThrottle(userUuid: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['throttles'],
    queryFn: fetchThrottles,
    enabled: enabled && !!userUuid,
    select: (data: { items: ThrottleItem[] }) => data.items.find((i) => i.user_uuid === userUuid) ?? null,
  })
}

interface ThrottleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Пользователь задан снаружи (карточка юзера): поле UUID не показываем. */
  userUuid?: string
}

/**
 * Диалог «Урезать скорость»: одно окно на страницу «Блокировки» и карточку юзера.
 * Пустая скорость и срок — значения из настроек, как и в API.
 */
export function ThrottleDialog({ open, onOpenChange, userUuid }: ThrottleDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [uuid, setUuid] = useState('')
  const [rate, setRate] = useState('')
  const [hours, setHours] = useState('')
  const [reason, setReason] = useState('')
  const target = (userUuid ?? uuid).trim()

  const reset = () => { setUuid(''); setRate(''); setHours(''); setReason('') }

  const addMutation = useMutation({
    mutationFn: (body: { user_uuid: string; rate_kbit?: number; expires_in_hours?: number; reason?: string }) =>
      client.post('/violations/throttle', body),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['throttles'] })
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      toast.success(
        res?.data?.moved_to_squad
          ? t('violations.throttles.toast.addedWithSquad')
          : t('violations.throttles.toast.added'),
      )
      onOpenChange(false)
      reset()
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message || t('common.error'))
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('violations.throttles.addTitle')}</DialogTitle>
          <DialogDescription>{t('violations.throttles.addDesc')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {!userUuid && (
            <div>
              <label className="mb-1 block text-sm">{t('violations.whitelist.userUuid')}</label>
              <Input value={uuid} onChange={(e) => setUuid(e.target.value)} placeholder="uuid" />
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm">{t('violations.throttles.rate')}</label>
            <Input
              type="number"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              placeholder={t('violations.throttles.ratePlaceholder')}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm">{t('violations.throttles.hours')}</label>
            <Input
              type="number"
              value={hours}
              onChange={(e) => setHours(e.target.value)}
              placeholder={t('violations.throttles.hoursPlaceholder')}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm">{t('violations.whitelist.reason')}</label>
            <Input value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('common.cancel')}</Button>
          <Button
            onClick={() => addMutation.mutate({
              user_uuid: target,
              rate_kbit: rate ? Number(rate) : undefined,
              expires_in_hours: hours ? Number(hours) : undefined,
              reason: reason.trim() || undefined,
            })}
            disabled={!target || addMutation.isPending}
          >
            {t('violations.throttles.add')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
