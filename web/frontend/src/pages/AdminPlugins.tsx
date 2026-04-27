import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  KeyRound,
  Loader2,
  PackagePlus,
  Power,
  RefreshCw,
  Trash2,
  Upload,
} from 'lucide-react'
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
import { Textarea } from '@/components/ui/textarea'

import {
  applyMasterLicense,
  fetchPluginsInventory,
  restartBackend,
  uninstallPlugin,
  updateLicense,
  uploadPlugin,
  type InstalledPluginInfo,
} from '@/api/adminPlugins'

/**
 * Admin → Plugins: install / license / uninstall paid plugins through
 * the panel UI. Only superadmins reach this page (RBAC enforced server-
 * side; sidebar entry hides it for everyone else).
 *
 * Three discrete flows:
 * 1. Upload — one wheel + one JWT, plugin gets pip-installed immediately
 *    and the JWT is stored. Restart afterwards to register routes.
 * 2. Master license — paste a bundle JWT, panel decodes the
 *    ``plugins`` claim and writes the JWT under each plugin id, so
 *    operators don't paste it once per plugin.
 * 3. Per-plugin manage — update license, uninstall.
 */
export default function AdminPlugins() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['admin-plugins-inventory'],
    queryFn: fetchPluginsInventory,
    retry: false,
    staleTime: 30_000,
  })

  const [uploadOpen, setUploadOpen] = useState(false)
  const [masterOpen, setMasterOpen] = useState(false)
  const [licenseEditing, setLicenseEditing] = useState<InstalledPluginInfo | null>(null)
  const [confirmingUninstall, setConfirmingUninstall] = useState<InstalledPluginInfo | null>(null)
  const [confirmingRestart, setConfirmingRestart] = useState(false)

  const refresh = () => qc.invalidateQueries({ queryKey: ['admin-plugins-inventory'] })

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('adminPlugins.title')}</h1>
          <p className="mt-1 text-sm text-dark-300">{t('adminPlugins.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 mr-2" />
            {t('adminPlugins.refresh')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setMasterOpen(true)}>
            <KeyRound className="w-4 h-4 mr-2" />
            {t('adminPlugins.master_license')}
          </Button>
          <Button onClick={() => setUploadOpen(true)}>
            <PackagePlus className="w-4 h-4 mr-2" />
            {t('adminPlugins.install')}
          </Button>
        </div>
      </div>

      {/* Restart strip — visible only when there's something to apply. */}
      <div className="glass-card border border-amber-500/40 bg-amber-500/5 p-4 flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
        <div className="flex-1 text-sm text-amber-100">
          {t('adminPlugins.restart_hint')}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setConfirmingRestart(true)}
        >
          <Power className="w-4 h-4 mr-2" />
          {t('adminPlugins.restart')}
        </Button>
      </div>

      <div className="glass-card p-5">
        {isLoading || !data ? (
          <p className="text-sm text-dark-300">{t('common.loading')}</p>
        ) : data.installed.length === 0 && data.pending_wheels.length === 0 ? (
          <p className="text-sm text-dark-400">{t('adminPlugins.empty')}</p>
        ) : (
          <ul className="divide-y divide-[var(--glass-border)]">
            {data.installed.map((p) => (
              <PluginRow
                key={p.plugin_id}
                p={p}
                onEditLicense={() => setLicenseEditing(p)}
                onUninstall={() => setConfirmingUninstall(p)}
              />
            ))}
            {data.pending_wheels.map((w) => (
              <li key={w.filename} className="py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm text-white">{w.package_name}@{w.version}</div>
                  <div className="text-xs text-amber-300">
                    {t('adminPlugins.pending_wheel')}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-4 text-[11px] text-dark-400">
          {t('adminPlugins.dir_label')}: <span className="font-mono">{data?.plugins_dir ?? '—'}</span>
        </div>
      </div>

      {uploadOpen && <UploadDialog onClose={() => { setUploadOpen(false); refresh() }} />}
      {masterOpen && <MasterLicenseDialog onClose={() => { setMasterOpen(false); refresh() }} />}
      {licenseEditing && (
        <LicenseDialog
          plugin={licenseEditing}
          onClose={() => { setLicenseEditing(null); refresh() }}
        />
      )}
      {confirmingUninstall && (
        <UninstallDialog
          plugin={confirmingUninstall}
          onClose={() => { setConfirmingUninstall(null); refresh() }}
        />
      )}
      {confirmingRestart && (
        <RestartDialog onClose={() => setConfirmingRestart(false)} />
      )}
    </div>
  )
}


function PluginRow({
  p,
  onEditLicense,
  onUninstall,
}: {
  p: InstalledPluginInfo
  onEditLicense: () => void
  onUninstall: () => void
}) {
  const { t } = useTranslation()
  return (
    <li className="py-3 flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-white">
            {p.name || p.plugin_id}
          </span>
          {p.version && (
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--glass-bg)] text-dark-200">
              v{p.version}
            </span>
          )}
          <LicenseBadge state={p.license_state} licenseSet={p.license_set} />
        </div>
        <div className="mt-0.5 text-xs text-dark-400 font-mono truncate">
          {p.plugin_id}
          {p.wheel_name ? ` · ${p.wheel_name}` : ''}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Button variant="outline" size="sm" onClick={onEditLicense}>
          <KeyRound className="w-3.5 h-3.5 mr-1.5" />
          {t('adminPlugins.update_license')}
        </Button>
        <Button variant="outline" size="sm" onClick={onUninstall}>
          <Trash2 className="w-3.5 h-3.5" />
        </Button>
      </div>
    </li>
  )
}


function LicenseBadge({
  state,
  licenseSet,
}: {
  state: InstalledPluginInfo['license_state']
  licenseSet: boolean
}) {
  const { t } = useTranslation()
  if (state === 'valid') {
    return (
      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300">
        {t('adminPlugins.license.valid')}
      </span>
    )
  }
  if (state === 'expired') {
    return (
      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">
        {t('adminPlugins.license.expired')}
      </span>
    )
  }
  if (state === 'not_required') {
    return null
  }
  return (
    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">
      {licenseSet ? t('adminPlugins.license.invalid') : t('adminPlugins.license.missing')}
    </span>
  )
}


function UploadDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const fileRef = useRef<HTMLInputElement>(null)
  const [pluginId, setPluginId] = useState('')
  const [jwtToken, setJwtToken] = useState('')

  const mutation = useMutation({
    mutationFn: () => {
      const file = fileRef.current?.files?.[0]
      if (!file) throw new Error('no file')
      return uploadPlugin({ file, pluginId: pluginId.trim(), jwtToken: jwtToken.trim() })
    },
    onSuccess: (res) => {
      toast.success(res.message)
      onClose()
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail
      toast.error(detail?.message || t('adminPlugins.errors.upload_failed'))
    },
  })

  const canSubmit = pluginId.trim() && jwtToken.trim() && fileRef.current?.files?.length

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('adminPlugins.install_dialog.title')}</DialogTitle>
          <DialogDescription>{t('adminPlugins.install_dialog.subtitle')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="plugin-id">{t('adminPlugins.install_dialog.plugin_id')}</Label>
            <Input
              id="plugin-id"
              value={pluginId}
              onChange={(e) => setPluginId(e.target.value)}
              placeholder="smart_support"
              className="font-mono"
            />
            <p className="text-[11px] text-dark-400">
              {t('adminPlugins.install_dialog.plugin_id_hint')}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>{t('adminPlugins.install_dialog.wheel')}</Label>
            <input
              ref={fileRef}
              type="file"
              accept=".whl"
              className="text-xs file:mr-3 file:px-3 file:py-1.5 file:rounded file:border file:border-[var(--glass-border)] file:bg-[var(--glass-bg)] file:text-white"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="jwt">{t('adminPlugins.install_dialog.jwt')}</Label>
            <Textarea
              id="jwt"
              value={jwtToken}
              onChange={(e) => setJwtToken(e.target.value)}
              rows={4}
              placeholder="eyJhbGciOiJFZERTQS..."
              className="font-mono text-[11px]"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Upload className="w-4 h-4 mr-2" />
            )}
            {t('adminPlugins.install_dialog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function MasterLicenseDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const [jwtToken, setJwtToken] = useState('')

  const mutation = useMutation({
    mutationFn: () => applyMasterLicense(jwtToken.trim()),
    onSuccess: (res) => {
      toast.success(t('adminPlugins.master_license_applied', { count: res.plugin_ids.length }))
      onClose()
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail
      toast.error(detail?.message || t('adminPlugins.errors.master_failed'))
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('adminPlugins.master_dialog.title')}</DialogTitle>
          <DialogDescription>{t('adminPlugins.master_dialog.subtitle')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 py-2">
          <Label htmlFor="master-jwt">{t('adminPlugins.master_dialog.jwt')}</Label>
          <Textarea
            id="master-jwt"
            value={jwtToken}
            onChange={(e) => setJwtToken(e.target.value)}
            rows={5}
            placeholder="eyJhbGciOiJFZERTQS..."
            className="font-mono text-[11px]"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!jwtToken.trim() || mutation.isPending}
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {t('adminPlugins.master_dialog.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


function LicenseDialog({
  plugin,
  onClose,
}: {
  plugin: InstalledPluginInfo
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [jwtToken, setJwtToken] = useState('')

  const mutation = useMutation({
    mutationFn: () => updateLicense({ pluginId: plugin.plugin_id, jwtToken: jwtToken.trim() }),
    onSuccess: (res) => {
      toast.success(res.message || t('adminPlugins.update_license_success'))
      onClose()
    },
    onError: () => {
      toast.error(t('adminPlugins.errors.update_license_failed'))
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('adminPlugins.license_dialog.title', { name: plugin.name || plugin.plugin_id })}</DialogTitle>
          <DialogDescription>{t('adminPlugins.license_dialog.subtitle')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 py-2">
          <Label>{t('adminPlugins.install_dialog.jwt')}</Label>
          <Textarea
            value={jwtToken}
            onChange={(e) => setJwtToken(e.target.value)}
            rows={5}
            placeholder="eyJhbGciOiJFZERTQS..."
            className="font-mono text-[11px]"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={!jwtToken.trim() || mutation.isPending}
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            {t('adminPlugins.license_dialog.submit')}
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
  plugin: InstalledPluginInfo
  onClose: () => void
}) {
  const { t } = useTranslation()
  const mutation = useMutation({
    mutationFn: () => uninstallPlugin(plugin.plugin_id),
    onSuccess: (res) => {
      toast.success(res.message || t('adminPlugins.uninstall_success'))
      onClose()
    },
    onError: () => {
      toast.error(t('adminPlugins.errors.uninstall_failed'))
    },
  })
  return (
    <AlertDialog open onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('adminPlugins.uninstall_dialog.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t('adminPlugins.uninstall_dialog.subtitle', {
              name: plugin.name || plugin.plugin_id,
            })}
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
    mutationFn: () => restartBackend(),
    onSuccess: () => {
      toast.success(t('adminPlugins.restart_started'))
      onClose()
      // The server is going down — eventually the next refetch will fail
      // until docker brings it back. We don't reload the page here so the
      // operator can read the toast.
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
