import { useEffect, useState } from 'react'
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

export const fetchThrottles = async (): Promise<{
  items: ThrottleItem[]
  total: number
  /** Скорость по умолчанию из настроек; 0 — без лимита. */
  default_rate_kbit?: number
}> => {
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
 * Скорость подставляется из настроек; 0 или пусто — без лимита, то есть
 * персональное ограничение снимается. Пустой срок — значение из настроек.
 */
export function ThrottleDialog({ open, onOpenChange, userUuid }: ThrottleDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [uuid, setUuid] = useState('')
  const [rate, setRate] = useState('')
  const [hours, setHours] = useState('')
  const [reason, setReason] = useState('')
  const [rateTouched, setRateTouched] = useState(false)
  const target = (userUuid ?? uuid).trim()

  const { data: throttleList } = useQuery({ queryKey: ['throttles'], queryFn: fetchThrottles, enabled: open })
  const defaultRate = throttleList?.default_rate_kbit
  // Подставляем скорость из настроек, пока админ поле не трогал: пустое поле — это «без лимита»
  useEffect(() => {
    if (open && !rateTouched && defaultRate) setRate(String(defaultRate))
  }, [open, rateTouched, defaultRate])

  const reset = () => { setUuid(''); setRate(''); setHours(''); setReason(''); setRateTouched(false) }

  const addMutation = useMutation({
    mutationFn: (body: { user_uuid: string; rate_kbit?: number; expires_in_hours?: number; reason?: string }) =>
      client.post('/violations/throttle', body),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['throttles'] })
      queryClient.invalidateQueries({ queryKey: ['violations'] })
      if (res?.data?.rate_kbit === 0) {
        toast.success(
          res.data.lifted
            ? t('violations.throttles.toast.noLimit')
            : t('violations.throttles.toast.nothingToLift'),
        )
      } else {
        toast.success(
          res?.data?.moved_to_squad
            ? t('violations.throttles.toast.addedWithSquad')
            : t('violations.throttles.toast.added'),
        )
      }
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
              onChange={(e) => { setRate(e.target.value); setRateTouched(true) }}
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
              rate_kbit: rate.trim() ? Number(rate) : 0,
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
