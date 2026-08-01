import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeftRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  CreditCard,
  Download,
  KeyRound,
  Loader2,
  Package,
  Power,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Upload,
  Zap,
} from '@/components/brand/icons'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import {
  connectStore,
  disconnectStore,
  fetchCatalog,
  fetchOrderStatus,
  fetchStoreStatus,
  installPlugin,
  licenseErrorCode,
  purchase,
  redeemCode,
  restartBackend,
  startTrial,
  syncNow,
  transferOut,
  uninstallPlugin,
  uploadWheel,
  type CatalogPlugin,
  type CatalogTariff,
  type CatalogText,
  type EntitlementQuota,
  type PluginEntitlement,
  type PurchaseItem,
  type PurchaseResponse,
  type StoreStatus,
  type TransferOutResponse,
} from '@/api/adminPlugins'

/**
 * Admin → Plugins: the store (keyless model). Catalog cards with prices
 * and subscription states, purchase flow (USDT + memo, order polling),
 * install/update from the licensing server, promo/transfer codes.
 * Superadmin-only — enforced server-side, sidebar hides the entry.
 */

function pickText(text: CatalogText | undefined, lang: string): string {
  if (!text) return ''
  const short = lang.split('-')[0]
  return text[short] ?? text.en ?? text.ru ?? Object.values(text)[0] ?? ''
}

/** Numeric segment-wise version compare: 1 if a > b. */
function cmpVersions(a: string, b: string): number {
  const pa = a.split('.').map((s) => parseInt(s, 10) || 0)
  const pb = b.split('.').map((s) => parseInt(s, 10) || 0)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (d !== 0) return d > 0 ? 1 : -1
  }
  return 0
}

function formatTs(ts: number | null | undefined, lang: string): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString(lang.startsWith('ru') ? 'ru-RU' : 'en-US', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function useServerError() {
  const { t } = useTranslation()
  return (err: unknown, fallbackKey: string): string => {
    const code = licenseErrorCode(err)
    if (code) {
      const known = t(`adminPlugins.server_errors.${code}`, { defaultValue: '' })
      if (known) return known
      return t('adminPlugins.errors.server_code', { code })
    }
    return t(fallbackKey)
  }
}

function copyWithToast(t: (k: string) => string, value: string) {
  navigator.clipboard
    .writeText(value)
    .then(() => toast.success(t('adminPlugins.copied')))
    .catch(() => toast.error(t('adminPlugins.errors.copy_failed')))
}

export default function AdminPlugins() {
  const { t, i18n } = useTranslation()
  const qc = useQueryClient()
  const lang = i18n.language

  const statusQ = useQuery({
    queryKey: ['plugin-store-status'],
    queryFn: fetchStoreStatus,
    retry: false,
    refetchInterval: 60_000,
  })
  const catalogQ = useQuery({
    queryKey: ['plugin-store-catalog'],
    queryFn: fetchCatalog,
    retry: false,
    staleTime: 5 * 60_000,
  })

  const [needsRestart, setNeedsRestart] = useState(false)
  const [purchaseTarget, setPurchaseTarget] = useState<{
    plugin: CatalogPlugin
    mode: 'subscription' | 'topup'
    /** План, выбранный в карточке; без него диалог берёт первый из каталога. */
    tariff?: CatalogTariff
  } | null>(null)
  const [redeemOpen, setRedeemOpen] = useState(false)
  const [transferOpen, setTransferOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [confirmingUninstall, setConfirmingUninstall] = useState<{ id: string; name: string } | null>(null)
  const [confirmingRestart, setConfirmingRestart] = useState(false)

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['plugin-store-status'] })
    qc.invalidateQueries({ queryKey: ['plugin-store-catalog'] })
  }

  const serverError = useServerError()
  const syncMutation = useMutation({
    mutationFn: syncNow,
    onSuccess: () => {
      toast.success(t('adminPlugins.sync_ok'))
      refresh()
    },
    onError: (err: unknown) => toast.error(serverError(err, 'adminPlugins.errors.sync_failed')),
  })
  const connectMutation = useMutation({
    mutationFn: connectStore,
    onSuccess: () => {
      toast.success(t('adminPlugins.connect_ok'))
      refresh()
    },
    onError: (err: unknown) => toast.error(serverError(err, 'adminPlugins.errors.connect_failed')),
  })
  const disconnectMutation = useMutation({
    mutationFn: disconnectStore,
    onSuccess: () => {
      toast.success(t('adminPlugins.disconnect_ok'))
      refresh()
    },
    onError: () => toast.error(t('adminPlugins.errors.disconnect_failed')),
  })

  const status = statusQ.data
  const catalog = catalogQ.data

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('adminPlugins.title')}</h1>
          <p className="mt-1 text-sm text-dark-300">{t('adminPlugins.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            {t('adminPlugins.sync')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setRedeemOpen(true)}>
            <KeyRound className="w-4 h-4 mr-2" />
            {t('adminPlugins.redeem')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="w-4 h-4 mr-2" />
            {t('adminPlugins.upload')}
          </Button>
        </div>
      </div>

      {needsRestart && (
        <div className="glass-card border border-amber-500/40 bg-amber-500/5 p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          <div className="flex-1 text-sm text-amber-100">{t('adminPlugins.restart_hint')}</div>
          <Button variant="outline" size="sm" onClick={() => setConfirmingRestart(true)}>
            <Power className="w-4 h-4 mr-2" />
            {t('adminPlugins.restart')}
          </Button>
        </div>
      )}

      {status?.messages.map((msg, i) => (
        <div
          key={i}
          className={`glass-card p-3 flex items-center gap-3 text-sm border ${
            msg.level === 'warning'
              ? 'border-amber-500/40 bg-amber-500/5 text-amber-100'
              : 'border-sky-500/30 bg-sky-500/5 text-sky-100'
          }`}
        >
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            {t(msg.text_i18n, {
              defaultValue: msg.text_i18n,
              plugin: String(msg.args?.plugin ?? ''),
              date: formatTs(Number(msg.args?.paid_until) || null, lang),
            })}
          </span>
        </div>
      ))}

      {status && !status.registered && (
        <div className="glass-card border border-primary-500/40 bg-primary-500/5 p-4 flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-primary-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-sm text-white font-medium">{t('adminPlugins.connect.title')}</div>
            <p className="mt-1 text-xs text-dark-300">{t('adminPlugins.connect.privacy')}</p>
          </div>
          <Button size="sm" onClick={() => connectMutation.mutate()} disabled={connectMutation.isPending}>
            {connectMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <KeyRound className="w-4 h-4 mr-2" />
            )}
            {t('adminPlugins.connect.button')}
          </Button>
        </div>
      )}

      <ConnectionCard
        status={status}
        loading={statusQ.isLoading}
        lang={lang}
        onTransfer={() => setTransferOpen(true)}
        onDisconnect={() => disconnectMutation.mutate()}
        disconnecting={disconnectMutation.isPending}
      />

      {catalogQ.isLoading ? (
        <div className="glass-card p-5 text-sm text-dark-300">{t('common.loading')}</div>
      ) : catalogQ.isError ? (
        <div className="glass-card p-5 text-sm text-dark-300">
          {serverError(catalogQ.error, 'adminPlugins.errors.catalog_failed')}
        </div>
      ) : !catalog || catalog.plugins.length === 0 ? (
        <div className="glass-card p-5 text-sm text-dark-400">{t('adminPlugins.catalog_empty')}</div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          {catalog.plugins.map((p) => (
            <PluginCard
              key={p.id}
              plugin={p}
              entitlement={status?.plugins[p.id]}
              installedVersion={status?.installed[p.id]}
              lang={lang}
              onBuy={(mode, tariff) => setPurchaseTarget({ plugin: p, mode, tariff })}
              onInstalled={() => {
                setNeedsRestart(true)
                refresh()
              }}
              onUninstall={() => setConfirmingUninstall({ id: p.id, name: pickText(p.name, lang) })}
            />
          ))}
        </div>
      )}

      <ExtraInstalled status={status} catalog={catalog?.plugins ?? []} onUninstall={setConfirmingUninstall} />

      {purchaseTarget && (
        <PurchaseDialog
          plugin={purchaseTarget.plugin}
          mode={purchaseTarget.mode}
          tariff={purchaseTarget.tariff}
          lang={lang}
          onClose={() => {
            setPurchaseTarget(null)
            refresh()
          }}
        />
      )}
      {redeemOpen && <RedeemDialog onClose={() => { setRedeemOpen(false); refresh() }} />}
      {transferOpen && <TransferDialog onClose={() => { setTransferOpen(false); refresh() }} lang={lang} />}
      {uploadOpen && (
        <UploadDialog
          onClose={(installed) => {
            setUploadOpen(false)
            if (installed) setNeedsRestart(true)
            refresh()
          }}
        />
      )}
      {confirmingUninstall && (
        <UninstallDialog
          plugin={confirmingUninstall}
          onClose={(removed) => {
            setConfirmingUninstall(null)
            if (removed) setNeedsRestart(true)
            refresh()
          }}
        />
      )}
      {confirmingRestart && <RestartDialog onClose={() => setConfirmingRestart(false)} />}
    </div>
  )
}


function ConnectionCard({
  status,
  loading,
  lang,
  onTransfer,
  onDisconnect,
  disconnecting,
}: {
  status: StoreStatus | undefined
  loading: boolean
  lang: string
  onTransfer: () => void
  onDisconnect: () => void
  disconnecting: boolean
}) {
  const { t } = useTranslation()
  if (loading || !status) {
    return <div className="glass-card p-4 text-sm text-dark-300">{t('common.loading')}</div>
  }
  const hasSubs = Object.keys(status.plugins).length > 0
  return (
    <div className="glass-card p-4 flex items-center gap-4 flex-wrap text-sm">
      <div className="flex items-center gap-2">
        <span
          className={`w-2 h-2 rounded-full ${
            status.registered ? (status.last_error ? 'bg-amber-400' : 'bg-emerald-400') : 'bg-dark-400'
          }`}
        />
        <span className="text-white">
          {status.registered ? t('adminPlugins.link.registered') : t('adminPlugins.link.not_registered')}
        </span>
      </div>
      {status.instance_id && (
        <button
          type="button"
          className="font-mono text-xs text-dark-300 hover:text-white transition-colors"
          title={status.instance_id}
          onClick={() => copyWithToast(t, status.instance_id!)}
        >
          {status.instance_id.slice(0, 8)}…
        </button>
      )}
      <span className="text-dark-400 text-xs">
        {t('adminPlugins.link.last_sync')}: {formatTs(status.last_sync_ok, lang)}
      </span>
      {status.last_error && (
        <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">
          {status.last_error}
        </span>
      )}
      <div className="ml-auto flex items-center gap-3">
        {hasSubs && (
          <button
            type="button"
            onClick={onTransfer}
            className="inline-flex items-center gap-1.5 text-xs text-dark-300 hover:text-white transition-colors"
          >
            <ArrowLeftRight className="w-3.5 h-3.5" />
            {t('adminPlugins.transfer.open')}
          </button>
        )}
        {status.registered && (
          <button
            type="button"
            onClick={onDisconnect}
            disabled={disconnecting}
            className="inline-flex items-center gap-1.5 text-xs text-dark-300 hover:text-red-300 transition-colors disabled:opacity-50"
          >
            {disconnecting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}
            {t('adminPlugins.disconnect')}
          </button>
        )}
      </div>
    </div>
  )
}


function StateBadge({ ent }: { ent: PluginEntitlement | undefined }) {
  const { t } = useTranslation()
  if (!ent) {
    return (
      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-300">
        {t('adminPlugins.state.none')}
      </span>
    )
  }
  const styles: Record<string, string> = {
    active: 'bg-emerald-500/15 text-emerald-300',
    grace: 'bg-amber-500/15 text-amber-300',
    expired: 'bg-red-500/15 text-red-300',
  }
  return (
    <span
      className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${
        styles[ent.state] ?? styles.expired
      }`}
    >
      {t(`adminPlugins.state.${ent.state}`)}
    </span>
  )
}


function QuotaBar({ quota }: { quota: EntitlementQuota }) {
  const { t } = useTranslation()
  const pct = quota.period_limit > 0 ? Math.min(100, (quota.used / quota.period_limit) * 100) : 0
  const color = pct < 75 ? 'bg-emerald-400' : pct < 95 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-dark-300">{t('adminPlugins.quota.title')}</span>
        <span className="text-white font-mono">
          {quota.used} / {quota.period_limit}
          {quota.topup_left > 0 && (
            <span className="text-emerald-300"> {t('adminPlugins.quota.topup', { n: quota.topup_left })}</span>
          )}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--glass-bg)] overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}


function PluginCard({
  plugin,
  entitlement,
  installedVersion,
  lang,
  onBuy,
  onInstalled,
  onUninstall,
}: {
  plugin: CatalogPlugin
  entitlement: PluginEntitlement | undefined
  installedVersion: string | undefined
  lang: string
  onBuy: (mode: 'subscription' | 'topup', tariff?: CatalogTariff) => void
  onInstalled: () => void
  onUninstall: () => void
}) {
  const { t } = useTranslation()
  const serverError = useServerError()
  const [dataSentOpen, setDataSentOpen] = useState(false)
  const [pickedTariff, setPickedTariff] = useState<string | null>(null)

  const usable = entitlement && (entitlement.state === 'active' || entitlement.state === 'grace')
  const updateAvailable =
    installedVersion !== undefined && cmpVersions(plugin.latest_version, installedVersion) > 0
  // Пока план не выбран руками, показываем оплаченный (tier) — иначе первый по sort.
  const tariff =
    plugin.tariffs.find((x) => x.code === (pickedTariff ?? entitlement?.tier)) ?? plugin.tariffs[0]
  // Плагин снят с продажи: цен в каталоге нет, покупка и триал закрыты на
  // сервере. Поля нет — сервер лицензирования старой версии, продаётся.
  const salePaused = plugin.purchasable === false
  const saleNote = pickText(plugin.sale_note ?? {}, lang) || t('adminPlugins.sale_paused')
  // Нулевая цена = пробный план: его не покупают, а активируют через /v1/trial.
  const isTrial = !!tariff && tariff.price.rub === 0 && tariff.price.usdt === 0
  const trialInCatalog = plugin.tariffs.some((x) => x.price.rub === 0 && x.price.usdt === 0)
  const topup = plugin.topups[0]

  const installMutation = useMutation({
    mutationFn: () => installPlugin(plugin.id),
    onSuccess: (res) => {
      toast.success(res.message || t('adminPlugins.install_ok'))
      onInstalled()
    },
    onError: (err: unknown) => toast.error(serverError(err, 'adminPlugins.errors.install_failed')),
  })
  const trialMutation = useMutation({
    mutationFn: () => startTrial(plugin.id),
    onSuccess: () => {
      toast.success(t('adminPlugins.trial_ok'))
      onInstalled()
    },
    onError: (err: unknown) => toast.error(serverError(err, 'adminPlugins.errors.trial_failed')),
  })

  return (
    <div className="glass-card p-5 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Package className="w-4 h-4 text-primary-400 shrink-0" />
            <span className="text-base font-semibold text-white">{pickText(plugin.name, lang)}</span>
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-200">
              {installedVersion ? `v${installedVersion}` : `v${plugin.latest_version}`}
            </span>
            {plugin.channel === 'dev' && (
              <span
                className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-300"
                title={t('adminPlugins.dev_channel_hint')}
              >
                dev
              </span>
            )}
            <StateBadge ent={entitlement} />
            {updateAvailable && (
              <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300">
                {t('adminPlugins.update_available', { version: plugin.latest_version })}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-sm text-dark-300">{pickText(plugin.summary, lang)}</p>
        </div>
        {salePaused ? (
          <div className="text-right shrink-0">
            <span className="inline-block text-[11px] uppercase tracking-wider px-2 py-1 rounded bg-amber-500/15 text-amber-300">
              {saleNote}
            </span>
          </div>
        ) : tariff ? (
          <div className="text-right shrink-0">
            {isTrial ? (
              <div className="text-lg font-bold text-emerald-300 leading-tight">
                {t('adminPlugins.free')}
              </div>
            ) : (
              <>
                <div className="text-lg font-bold text-white leading-tight">
                  {tariff.price.rub.toLocaleString('ru-RU')} ₽
                </div>
                <div className="text-xs text-dark-400">
                  {tariff.price.usdt} USDT / {t('adminPlugins.per_month')}
                </div>
              </>
            )}
            {tariff.limits.ai_calls != null && (
              <div className="mt-0.5 text-[11px] text-dark-400">
                {t('adminPlugins.ai_calls_limit', { n: tariff.limits.ai_calls })}
              </div>
            )}
          </div>
        ) : null}
      </div>

      {plugin.tariffs.length > 1 && (
        <div>
          <div className="flex items-center gap-1 p-1 rounded-lg bg-[var(--glass-bg)] border border-[var(--glass-border)] w-fit max-w-full flex-wrap">
            {plugin.tariffs.map((x) => {
              const selected = x.code === tariff?.code
              return (
                <button
                  key={x.code}
                  type="button"
                  onClick={() => setPickedTariff(x.code)}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    selected
                      ? 'bg-primary-500/25 text-white'
                      : 'text-dark-300 hover:text-white hover:bg-white/5'
                  }`}
                >
                  {pickText(x.title ?? {}, lang) || x.code}
                  {entitlement?.tier === x.code && <span className="ml-1 text-emerald-400">•</span>}
                </button>
              )
            })}
          </div>
          {tariff && pickText(tariff.note ?? {}, lang) && (
            <p className="mt-2 text-[11px] text-dark-300">{pickText(tariff.note ?? {}, lang)}</p>
          )}
        </div>
      )}

      <ul className="space-y-1.5">
        {plugin.features.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-dark-200">
            <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-[1px]" />
            <span>{pickText(f, lang)}</span>
          </li>
        ))}
      </ul>

      <div className="rounded-lg border border-[var(--glass-border)]">
        <button
          type="button"
          onClick={() => setDataSentOpen((v) => !v)}
          className="w-full flex items-center gap-2 p-2.5 text-xs text-dark-300 hover:text-white transition-colors"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span className="flex-1 text-left">{t('adminPlugins.data_sent')}</span>
          {dataSentOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
        {dataSentOpen && (
          <p className="px-2.5 pb-2.5 text-[11px] leading-relaxed text-dark-300">
            {pickText(plugin.data_sent_to_cloud, lang)}
          </p>
        )}
      </div>

      {entitlement?.quota && <QuotaBar quota={entitlement.quota} />}
      {entitlement?.paid_until && (
        <div className="text-[11px] text-dark-400">
          {t('adminPlugins.paid_until')}: <span className="text-dark-200">{formatTs(entitlement.paid_until, lang)}</span>
        </div>
      )}

      <div className="mt-auto flex items-center gap-2 flex-wrap">
        {salePaused ? (
          // Покупка и пробный период закрыты на сервере — не показываем кнопки,
          // которые гарантированно вернут ошибку. Установка, обновление и
          // удаление ниже остаются: у оплативших плагин продолжает работать.
          <span className="text-xs text-dark-300">{t('adminPlugins.sale_paused_hint')}</span>
        ) : !entitlement ? (
          <>
            {isTrial ? (
              // Пробный план выбран кнопкой выше — покупать нечего, активируем.
              <Button
                size="sm"
                onClick={() => trialMutation.mutate()}
                disabled={trialMutation.isPending}
              >
                {trialMutation.isPending ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4 mr-2" />
                )}
                {t('adminPlugins.trial')}
              </Button>
            ) : (
              <Button size="sm" onClick={() => onBuy('subscription', tariff)}>
                <CreditCard className="w-4 h-4 mr-2" />
                {t('adminPlugins.buy')}
              </Button>
            )}
            {/* Пробного плана нет в каталоге — кнопка всё равно нужна: сервер
                может раздавать триал, просто не показывая его отдельным тарифом. */}
            {!trialInCatalog && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => trialMutation.mutate()}
                disabled={trialMutation.isPending}
              >
                {trialMutation.isPending ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4 mr-2" />
                )}
                {t('adminPlugins.trial')}
              </Button>
            )}
          </>
        ) : (
          <>
            <Button
              size="sm"
              variant={entitlement.state === 'active' ? 'outline' : 'default'}
              onClick={() => onBuy('subscription', tariff)}
              disabled={isTrial}
            >
              <CreditCard className="w-4 h-4 mr-2" />
              {/* Выбран пробный план — продлевать его нельзя, только сменить на платный. */}
              {isTrial ? t('adminPlugins.pick_paid') : t('adminPlugins.renew')}
            </Button>
            {topup && (
              <Button size="sm" variant="outline" onClick={() => onBuy('topup')}>
                <Zap className="w-4 h-4 mr-2" />
                {t('adminPlugins.buy_topup')}
              </Button>
            )}
          </>
        )}
        {usable && (!installedVersion || updateAvailable) && (
          <Button
            size="sm"
            variant={installedVersion ? 'outline' : 'default'}
            onClick={() => installMutation.mutate()}
            disabled={installMutation.isPending}
          >
            {installMutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Download className="w-4 h-4 mr-2" />
            )}
            {installedVersion ? t('adminPlugins.update') : t('adminPlugins.install')}
          </Button>
        )}
        {installedVersion && (
          <Button size="sm" variant="outline" onClick={onUninstall} className="ml-auto">
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>
    </div>
  )
}


/** Installed plugins that are absent from the catalog (e.g. air-gapped
 * uploads or plugins pulled from the store) still need an uninstall path. */
function ExtraInstalled({
  status,
  catalog,
  onUninstall,
}: {
  status: StoreStatus | undefined
  catalog: CatalogPlugin[]
  onUninstall: (v: { id: string; name: string }) => void
}) {
  const { t } = useTranslation()
  if (!status) return null
  const catalogIds = new Set(catalog.map((p) => p.id))
  const extras = Object.entries(status.installed).filter(([id]) => !catalogIds.has(id))
  if (extras.length === 0) return null
  return (
    <div className="glass-card p-5">
      <h2 className="text-sm font-semibold text-white uppercase tracking-wider mb-3">
        {t('adminPlugins.extra_installed')}
      </h2>
      <ul className="divide-y divide-[var(--glass-border)]">
        {extras.map(([id, version]) => (
          <li key={id} className="py-2.5 flex items-center justify-between gap-3">
            <div className="text-sm text-white font-mono">
              {id} <span className="text-dark-400">v{version}</span>
            </div>
            <Button size="sm" variant="outline" onClick={() => onUninstall({ id, name: id })}>
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}


function PurchaseDialog({
  plugin,
  mode,
  tariff: pickedTariff,
  lang,
  onClose,
}: {
  plugin: CatalogPlugin
  mode: 'subscription' | 'topup'
  tariff?: CatalogTariff
  lang: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const serverError = useServerError()
  const [months, setMonths] = useState(1)
  const [order, setOrder] = useState<PurchaseResponse | null>(null)
  const [orderState, setOrderState] = useState<'configuring' | 'waiting' | 'polling' | 'paid' | 'expired'>(
    'configuring',
  )
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const tariff = pickedTariff ?? plugin.tariffs[0]
  const topup = plugin.topups[0]

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current)
  }, [])

  const createMutation = useMutation({
    mutationFn: () => {
      const item: PurchaseItem =
        mode === 'subscription'
          ? { type: 'subscription', plugin_id: plugin.id, tariff: tariff.code, months }
          : { type: 'topup', plugin_id: plugin.id, pack: topup.code }
      return purchase([item])
    },
    onSuccess: (res) => {
      setOrder(res)
      setOrderState('waiting')
    },
    onError: (err: unknown) => toast.error(serverError(err, 'adminPlugins.errors.purchase_failed')),
  })

  const checkOrder = async (orderId: string) => {
    try {
      const res = await fetchOrderStatus(orderId)
      if (res.status === 'paid') {
        if (pollRef.current) clearInterval(pollRef.current)
        setOrderState('paid')
      } else if (res.status === 'expired' || res.status === 'cancelled') {
        if (pollRef.current) clearInterval(pollRef.current)
        setOrderState('expired')
      }
    } catch {
      // сервер мигнул — следующий тик поллинга повторит проверку
    }
  }

  const startPolling = () => {
    if (!order) return
    setOrderState('polling')
    void checkOrder(order.order_id)
    pollRef.current = setInterval(() => void checkOrder(order.order_id), 15_000)
  }

  const total =
    mode === 'subscription'
      ? { rub: tariff.price.rub * months, usdt: +(tariff.price.usdt * months).toFixed(2) }
      : { rub: topup.price.rub, usdt: topup.price.usdt }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {mode === 'subscription'
              ? t('adminPlugins.purchase.title_sub', { name: pickText(plugin.name, lang) })
              : t('adminPlugins.purchase.title_topup', { name: pickText(plugin.name, lang) })}
          </DialogTitle>
          <DialogDescription>
            {orderState === 'configuring'
              ? mode === 'subscription'
                ? t('adminPlugins.purchase.subtitle_sub')
                : t('adminPlugins.purchase.subtitle_topup', { n: topup?.ai_calls ?? 0 })
              : t('adminPlugins.purchase.subtitle_pay')}
          </DialogDescription>
        </DialogHeader>

        {orderState === 'configuring' && (
          <div className="space-y-4 py-2">
            {mode === 'subscription' && (
              // Планов несколько — покупатель должен видеть, за какой платит.
              <div className="rounded-lg border border-[var(--glass-border)] p-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm text-white font-medium">
                    {pickText(tariff.title ?? {}, lang) || tariff.code}
                  </div>
                  {pickText(tariff.note ?? {}, lang) && (
                    <div className="text-[11px] text-dark-300 mt-0.5">
                      {pickText(tariff.note ?? {}, lang)}
                    </div>
                  )}
                </div>
                {tariff.limits.ai_calls != null && (
                  <span className="text-[11px] text-dark-400 shrink-0">
                    {t('adminPlugins.ai_calls_limit', { n: tariff.limits.ai_calls })}
                  </span>
                )}
              </div>
            )}
            {mode === 'subscription' && (
              <div className="space-y-1.5">
                <Label>{t('adminPlugins.purchase.months')}</Label>
                <div className="flex gap-2">
                  {[1, 3, 6, 12].map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMonths(m)}
                      className={`flex-1 py-2 rounded-lg border text-sm transition-colors ${
                        months === m
                          ? 'border-primary-400 bg-primary-500/15 text-white'
                          : 'border-[var(--glass-border)] text-dark-300 hover:text-white'
                      }`}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="rounded-lg border border-[var(--glass-border)] p-3 flex items-center justify-between">
              <span className="text-sm text-dark-300">{t('adminPlugins.purchase.total')}</span>
              <span className="text-white font-semibold">
                {total.rub.toLocaleString('ru-RU')} ₽ · {total.usdt} USDT
              </span>
            </div>
          </div>
        )}

        {order && (orderState === 'waiting' || orderState === 'polling') && (
          <div className="space-y-3 py-2">
            <PaymentRow label={t('adminPlugins.purchase.address')} value={order.payment.address} mono />
            <PaymentRow
              label={t('adminPlugins.purchase.amount')}
              value={`${order.payment.amount} USDT`}
              copyValue={order.payment.amount}
            />
            <PaymentRow label={t('adminPlugins.purchase.memo')} value={order.payment.memo} mono />
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-100">
              {t('adminPlugins.purchase.memo_warning')}
            </div>
            <div className="text-[11px] text-dark-400">
              {t('adminPlugins.purchase.expires')}: {formatTs(order.expires_at, lang)}
            </div>
            {orderState === 'polling' && (
              <div className="flex items-center gap-2 text-sm text-dark-200">
                <Loader2 className="w-4 h-4 animate-spin text-primary-400" />
                {t('adminPlugins.purchase.polling')}
              </div>
            )}
            <p className="text-[11px] text-dark-400">{t('adminPlugins.purchase.manual_note')}</p>
          </div>
        )}

        {orderState === 'paid' && (
          <div className="py-6 flex flex-col items-center gap-3 text-center">
            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
            <div className="text-white font-semibold">{t('adminPlugins.purchase.paid_title')}</div>
            <p className="text-sm text-dark-300">{t('adminPlugins.purchase.paid_body')}</p>
          </div>
        )}

        {orderState === 'expired' && (
          <div className="py-6 flex flex-col items-center gap-3 text-center">
            <AlertTriangle className="w-10 h-10 text-amber-400" />
            <div className="text-white font-semibold">{t('adminPlugins.purchase.expired_title')}</div>
            <p className="text-sm text-dark-300">{t('adminPlugins.purchase.expired_body')}</p>
          </div>
        )}

        <DialogFooter>
          {orderState === 'configuring' && (
            <>
              <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
              <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                {createMutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {t('adminPlugins.purchase.create')}
              </Button>
            </>
          )}
          {orderState === 'waiting' && (
            <>
              <Button variant="outline" onClick={onClose}>{t('common.close')}</Button>
              <Button onClick={startPolling}>
                <Check className="w-4 h-4 mr-2" />
                {t('adminPlugins.purchase.i_paid')}
              </Button>
            </>
          )}
          {orderState === 'polling' && (
            <Button variant="outline" onClick={onClose}>{t('common.close')}</Button>
          )}
          {(orderState === 'paid' || orderState === 'expired') && (
            <Button onClick={onClose}>{t('common.close')}</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function PaymentRow({
  label,
  value,
  copyValue,
  mono,
}: {
  label: string
  value: string
  copyValue?: string
  mono?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1">
      <div className="text-[11px] uppercase tracking-wider text-dark-400">{label}</div>
      <div className="flex items-center gap-2">
        <div
          className={`flex-1 rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2 text-sm text-white break-all ${
            mono ? 'font-mono text-xs' : ''
          }`}
        >
          {value}
        </div>
        <Button variant="outline" size="sm" onClick={() => copyWithToast(t, copyValue ?? value)}>
          <Copy className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  )
}


function RedeemDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const serverError = useServerError()
  const [code, setCode] = useState('')

  const mutation = useMutation({
    mutationFn: () => redeemCode(code.trim()),
    onSuccess: () => {
      toast.success(t('adminPlugins.redeem_ok'))
      onClose()
    },
    onError: (err: unknown) => toast.error(serverError(err, 'adminPlugins.errors.redeem_failed')),
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('adminPlugins.redeem_dialog.title')}</DialogTitle>
          <DialogDescription>{t('adminPlugins.redeem_dialog.subtitle')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 py-2">
          <Label htmlFor="redeem-code">{t('adminPlugins.redeem_dialog.code')}</Label>
          <Input
            id="redeem-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="TRF-XXXX-XXXX"
            className="font-mono"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutation.mutate()} disabled={code.trim().length < 6 || mutation.isPending}>
            {mutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {t('adminPlugins.redeem_dialog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function TransferDialog({ onClose, lang }: { onClose: () => void; lang: string }) {
  const { t } = useTranslation()
  const serverError = useServerError()
  const [result, setResult] = useState<TransferOutResponse | null>(null)

  const mutation = useMutation({
    mutationFn: transferOut,
    onSuccess: setResult,
    onError: (err: unknown) => toast.error(serverError(err, 'adminPlugins.errors.transfer_failed')),
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('adminPlugins.transfer.title')}</DialogTitle>
          <DialogDescription>
            {result ? t('adminPlugins.transfer.done_subtitle') : t('adminPlugins.transfer.subtitle')}
          </DialogDescription>
        </DialogHeader>

        {!result ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-200">
            {t('adminPlugins.transfer.warning')}
          </div>
        ) : (
          <div className="space-y-3 py-2">
            <PaymentRow label={t('adminPlugins.transfer.code')} value={result.transfer_code} mono />
            <div className="text-[11px] text-dark-400">
              {t('adminPlugins.transfer.valid_until')}: {formatTs(result.valid_until, lang)}
            </div>
          </div>
        )}

        <DialogFooter>
          {!result ? (
            <>
              <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
              <Button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className="bg-red-500 hover:bg-red-600 text-white"
              >
                {mutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {t('adminPlugins.transfer.confirm')}
              </Button>
            </>
          ) : (
            <Button onClick={onClose}>{t('common.close')}</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function UploadDialog({ onClose }: { onClose: (installed: boolean) => void }) {
  const { t } = useTranslation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [hasFile, setHasFile] = useState(false)

  const mutation = useMutation({
    mutationFn: () => {
      const file = fileRef.current?.files?.[0]
      if (!file) throw new Error('no file')
      return uploadWheel(file)
    },
    onSuccess: (res) => {
      toast.success(res.message || t('adminPlugins.upload_ok'))
      onClose(true)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail
      toast.error(detail?.message || t('adminPlugins.errors.upload_failed'))
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose(false)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('adminPlugins.upload_dialog.title')}</DialogTitle>
          <DialogDescription>{t('adminPlugins.upload_dialog.subtitle')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 py-2">
          <Label>{t('adminPlugins.upload_dialog.wheel')}</Label>
          <input
            ref={fileRef}
            type="file"
            accept=".whl"
            onChange={() => setHasFile(!!fileRef.current?.files?.length)}
            className="text-xs file:mr-3 file:px-3 file:py-1.5 file:rounded file:border file:border-[var(--glass-border)] file:bg-[var(--glass-bg)] file:text-white"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)}>{t('common.cancel')}</Button>
          <Button onClick={() => mutation.mutate()} disabled={!hasFile || mutation.isPending}>
            {mutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Upload className="w-4 h-4 mr-2" />
            )}
            {t('adminPlugins.upload_dialog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function UninstallDialog({
  plugin,
  onClose,
}: {
  plugin: { id: string; name: string }
  onClose: (removed: boolean) => void
}) {
  const { t } = useTranslation()
  const mutation = useMutation({
    mutationFn: () => uninstallPlugin(plugin.id),
    onSuccess: (res) => {
      toast.success(res.message || t('adminPlugins.uninstall_success'))
      onClose(true)
    },
    onError: () => {
      toast.error(t('adminPlugins.errors.uninstall_failed'))
    },
  })
  return (
    <AlertDialog open onOpenChange={(open) => !open && onClose(false)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('adminPlugins.uninstall_dialog.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('adminPlugins.uninstall_dialog.subtitle', { name: plugin.name })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => mutation.mutate()}
            className="bg-red-500 hover:bg-red-600 text-white"
          >
            {t('adminPlugins.uninstall_dialog.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}


function RestartDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const mutation = useMutation({
    mutationFn: restartBackend,
    onSuccess: () => {
      toast.success(t('adminPlugins.restart_started'))
      onClose()
      // The server is going down — the next refetch fails until docker
      // brings it back. No page reload so the operator can read the toast.
    },
    onError: () => {
      toast.error(t('adminPlugins.errors.restart_failed'))
    },
  })
  return (
    <AlertDialog open onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('adminPlugins.restart_dialog.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('adminPlugins.restart_dialog.subtitle')}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => mutation.mutate()}
            className="bg-amber-500 hover:bg-amber-600 text-white"
          >
            {t('adminPlugins.restart_dialog.confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
