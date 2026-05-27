import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Database,
  Settings2,
  Download,
  Trash2,
  RotateCcw,
  Upload,
  FileJson,
  Users,
  HardDrive,
  Clock,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Shield,
  Archive,
  Send,
  Search,
  Recycle,
} from 'lucide-react'
import { backupApi } from '../api/backup'
import { useAuthStore } from '../store/authStore'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { PermissionGate } from '@/components/PermissionGate'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { useFormatters } from '@/lib/useFormatters'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function timeAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return 'только что'
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`
  return `${Math.floor(diff / 86400)} дн назад`
}

function FileIcon({ filename }: { filename: string }) {
  if (filename.endsWith('.sql.gz')) return <Database className="w-5 h-5 text-emerald-400" />
  if (filename.startsWith('config_backup_')) return <Settings2 className="w-5 h-5 text-cyan-400" />
  return <FileJson className="w-5 h-5 text-primary-400" />
}


// ── Backups Tab ─────────────────────────────────────────────────

function BackupsTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const token = useAuthStore((s) => s.accessToken)

  const [telegramDialog, setTelegramDialog] = useState<{ filename: string; chatId: string; topicId: string } | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [importStrategy, setImportStrategy] = useState<'skip' | 'overwrite'>('skip')

  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [confirmRestore, setConfirmRestore] = useState<string | null>(null)

  const { data: files = [], isLoading } = useQuery({
    queryKey: ['backup-files'],
    queryFn: backupApi.listFiles,
  })

  const sorted = [...files]
    .filter((f) => !searchQuery || f.filename.toLowerCase().includes(searchQuery.toLowerCase()))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  const createDbBackup = useMutation({
    mutationFn: backupApi.createDatabaseBackup,
    onSuccess: (data) => {
      toast.success(t('backup.created', { filename: data.filename }))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || t('backup.createFailed'), { duration: 8000 }),
  })

  const createConfigBackup = useMutation({
    mutationFn: backupApi.createConfigBackup,
    onSuccess: (data) => {
      toast.success(t('backup.created', { filename: data.filename }))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || t('backup.createFailed'), { duration: 8000 }),
  })

  const deleteBackup = useMutation({
    mutationFn: backupApi.deleteBackup,
    onSuccess: () => {
      toast.success(t('backup.deleted'))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
    },
    onError: () => toast.error(t('backup.deleteFailed')),
  })

  const restoreDb = useMutation({
    mutationFn: backupApi.restoreDatabase,
    onSuccess: () => {
      toast.success(t('backup.restored'))
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || t('backup.restoreFailed'), { duration: 8000 }),
  })

  const { data: diskUsage } = useQuery({
    queryKey: ['backup-disk-usage'],
    queryFn: backupApi.getDiskUsage,
    refetchInterval: 60_000,
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => backupApi.uploadFile(file),
    onSuccess: (data) => {
      toast.success(t('backup.uploaded', { defaultValue: `Uploaded: ${data.filename}` }))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
      queryClient.invalidateQueries({ queryKey: ['backup-disk-usage'] })
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Upload failed', { duration: 8000 }),
  })

  const rotateMutation = useMutation({
    mutationFn: () => backupApi.rotateBackups(10, 30),
    onSuccess: (data) => {
      toast.success(t('backup.rotated', { defaultValue: `Deleted ${data.deleted} old backups` }))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
      queryClient.invalidateQueries({ queryKey: ['backup-disk-usage'] })
    },
    onError: () => toast.error('Rotation failed'),
  })

  const telegramMutation = useMutation({
    mutationFn: ({ filename, chatId, topicId }: { filename: string; chatId?: string; topicId?: number }) =>
      backupApi.sendToTelegram(filename, chatId, topicId),
    onSuccess: (data) => {
      toast.success(t('backup.sentToTelegram', { defaultValue: `Sent ${data.parts_sent} part(s) to Telegram` }))
      setTelegramDialog(null)
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Send failed', { duration: 8000 }),
  })

  const handleUpload = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.sql.gz,.json'
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) uploadMutation.mutate(file)
    }
    input.click()
  }

  const handleDownload = (filename: string) => {
    const url = backupApi.downloadBackup(filename)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    if (token) {
      fetch(url, { headers: { Authorization: `Bearer ${token}` } })
        .then((r) => r.blob())
        .then((blob) => {
          const blobUrl = URL.createObjectURL(blob)
          a.href = blobUrl
          a.click()
          URL.revokeObjectURL(blobUrl)
        })
    } else {
      a.click()
    }
  }

  const handleExportFullConfig = async () => {
    try {
      const config = await backupApi.exportFullConfig()
      const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `remnawave-config-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(t('backup.fullConfigExported', { defaultValue: 'Full config exported' }))
    } catch {
      toast.error(t('backup.fullConfigExportFailed', { defaultValue: 'Export failed' }))
    }
  }

  const handleImportFullConfig = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      try {
        const text = await file.text()
        const config = JSON.parse(text)
        const result = await backupApi.importFullConfig(config, importStrategy)
        toast.success(t('backup.fullConfigImported', { defaultValue: `Imported: ${JSON.stringify(result.imported)} (strategy: ${importStrategy})` }))
        queryClient.invalidateQueries()
      } catch {
        toast.error(t('backup.fullConfigImportFailed', { defaultValue: 'Import failed' }))
      }
    }
    input.click()
  }

  return (
    <div className="space-y-6">
      {/* Actions — grouped into cards */}
      <PermissionGate resource="backups" action="create">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <button
            onClick={() => createDbBackup.mutate()}
            disabled={createDbBackup.isPending}
            className="group flex items-center gap-3 p-4 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] hover:border-emerald-500/30 hover:bg-emerald-500/5 transition-all text-left"
          >
            <div className="p-2.5 rounded-lg bg-emerald-500/10 group-hover:bg-emerald-500/20 transition-colors">
              {createDbBackup.isPending ? <Loader2 className="w-5 h-5 text-emerald-400 animate-spin" /> : <Database className="w-5 h-5 text-emerald-400" />}
            </div>
            <div>
              <p className="text-sm font-medium text-white">{t('backup.createDatabase')}</p>
              <p className="text-xs text-dark-300">PostgreSQL dump</p>
            </div>
          </button>

          <button
            onClick={() => createConfigBackup.mutate()}
            disabled={createConfigBackup.isPending}
            className="group flex items-center gap-3 p-4 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] hover:border-cyan-500/30 hover:bg-cyan-500/5 transition-all text-left"
          >
            <div className="p-2.5 rounded-lg bg-cyan-500/10 group-hover:bg-cyan-500/20 transition-colors">
              {createConfigBackup.isPending ? <Loader2 className="w-5 h-5 text-cyan-400 animate-spin" /> : <Settings2 className="w-5 h-5 text-cyan-400" />}
            </div>
            <div>
              <p className="text-sm font-medium text-white">{t('backup.createConfig')}</p>
              <p className="text-xs text-dark-300">{t('backup.configDesc', { defaultValue: 'Settings & rules' })}</p>
            </div>
          </button>

          <button
            onClick={handleExportFullConfig}
            className="group flex items-center gap-3 p-4 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] hover:border-primary/30 hover:bg-primary/5 transition-all text-left"
          >
            <div className="p-2.5 rounded-lg bg-primary/10 group-hover:bg-primary/20 transition-colors">
              <Download className="w-5 h-5 text-primary-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">{t('backup.exportFullConfig', { defaultValue: 'Export Config' })}</p>
              <p className="text-xs text-dark-300">JSON</p>
            </div>
          </button>

          <button
            onClick={handleImportFullConfig}
            className="group flex items-center gap-3 p-4 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] hover:border-amber-500/30 hover:bg-amber-500/5 transition-all text-left"
          >
            <div className="p-2.5 rounded-lg bg-amber-500/10 group-hover:bg-amber-500/20 transition-colors">
              <Upload className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">{t('backup.importFullConfig', { defaultValue: 'Import Config' })}</p>
              <p className="text-xs text-dark-300">
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setImportStrategy(importStrategy === 'skip' ? 'overwrite' : 'skip') }}
                  className="underline decoration-dotted hover:text-dark-100 transition-colors"
                >
                  {importStrategy === 'skip' ? 'skip existing' : 'overwrite'}
                </button>
              </p>
            </div>
          </button>
        </div>
      </PermissionGate>

      {/* Disk usage + tools */}
      <div className="flex flex-wrap items-center gap-3">
        {diskUsage && (
          <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl bg-[var(--glass-bg)] border border-[var(--glass-border)] flex-1 min-w-[200px]">
            <HardDrive className="w-4 h-4 text-dark-300" />
            <div className="flex-1">
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-dark-200">{formatBytes(diskUsage.backup_size_bytes)} / {formatBytes(diskUsage.disk_total_bytes)}</span>
                <span className="text-dark-400">{diskUsage.file_count} {t('backup.filesCount', { defaultValue: 'files' })}</span>
              </div>
              <div className="h-1.5 rounded-full bg-dark-700 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-primary-500 to-primary-400 transition-all"
                  style={{ width: `${Math.min(100, (diskUsage.backup_size_bytes / Math.max(1, diskUsage.disk_total_bytes)) * 100)}%` }}
                />
              </div>
            </div>
          </div>
        )}

        <PermissionGate resource="backups" action="create">
          <Button variant="outline" size="sm" onClick={handleUpload} disabled={uploadMutation.isPending} className="gap-1.5">
            {uploadMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            {t('backup.upload', { defaultValue: 'Upload' })}
          </Button>
        </PermissionGate>

        <PermissionGate resource="backups" action="delete">
          <Button variant="outline" size="sm" onClick={() => rotateMutation.mutate()} disabled={rotateMutation.isPending} className="gap-1.5">
            {rotateMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Recycle className="w-3.5 h-3.5" />}
            {t('backup.rotate', { defaultValue: 'Rotate' })}
          </Button>
        </PermissionGate>

        <div className="relative ml-auto">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-dark-400" />
          <Input
            placeholder={t('backup.search', { defaultValue: 'Search...' })}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 w-40 text-xs bg-[var(--glass-bg)]"
          />
        </div>
      </div>

      {/* Files list */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <Archive className="w-4 h-4 text-primary-400" />
            {t('backup.files')}
            <Badge variant="secondary" className="ml-auto font-mono">{files.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </div>
          ) : sorted.length === 0 ? (
            <EmptyState
              icon={HardDrive}
              title={t('backup.noFiles')}
              description={t('backup.noFilesDesc', { defaultValue: 'Create your first backup using the buttons above' })}
            />
          ) : (
            <div className="space-y-1.5">
              {sorted.map((file, i) => (
                <div
                  key={file.filename}
                  className="flex items-center gap-3 px-3 py-3 rounded-xl bg-[var(--glass-bg)] hover:bg-[var(--glass-bg-hover)] transition-colors animate-fade-in-up"
                  style={{ animationDelay: `${i * 0.03}s` }}
                >
                  <FileIcon filename={file.filename} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate font-mono">{file.filename}</p>
                    <p className="text-xs text-dark-300 mt-0.5">
                      <span className="text-dark-200">{formatBytes(file.size_bytes)}</span>
                      <span className="mx-1.5 text-dark-400">&middot;</span>
                      {formatDate(file.created_at)}
                      <span className="mx-1.5 text-dark-400">&middot;</span>
                      <span className="text-dark-400">{timeAgo(file.created_at)}</span>
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-dark-200 hover:text-white"
                      onClick={() => handleDownload(file.filename)}
                      aria-label={t('backup.download', { defaultValue: 'Download' })}
                    >
                      <Download className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-dark-200 hover:text-blue-400"
                      onClick={() => setTelegramDialog({ filename: file.filename, chatId: '', topicId: '' })}
                      aria-label={t('backup.sendTelegram', { defaultValue: 'Send to Telegram' })}
                    >
                      <Send className="w-4 h-4" />
                    </Button>

                    {file.filename.endsWith('.sql.gz') && (
                      <PermissionGate resource="backups" action="create">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-emerald-400 hover:text-emerald-300"
                          onClick={() => setConfirmRestore(file.filename)}
                          aria-label={t('backup.restore', { defaultValue: 'Restore' })}
                        >
                          <RotateCcw className="w-4 h-4" />
                        </Button>
                      </PermissionGate>
                    )}

                    <PermissionGate resource="backups" action="delete">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-dark-300 hover:text-red-400"
                        onClick={() => setConfirmDelete(file.filename)}
                        aria-label={t('common.delete')}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </PermissionGate>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(open) => !open && setConfirmDelete(null)}
        title={t('backup.confirmDelete')}
        description={t('backup.confirmDeleteDesc', { filename: confirmDelete })}
        confirmLabel={t('common.delete')}
        variant="destructive"
        onConfirm={() => {
          if (confirmDelete) deleteBackup.mutate(confirmDelete, { onSuccess: () => setConfirmDelete(null) })
        }}
      />

      <ConfirmDialog
        open={!!confirmRestore}
        onOpenChange={(open) => !open && setConfirmRestore(null)}
        title={t('backup.confirmRestore')}
        description={t('backup.confirmRestoreDesc', { filename: confirmRestore })}
        confirmLabel={t('backup.restore')}
        variant="destructive"
        onConfirm={() => {
          if (confirmRestore) restoreDb.mutate(confirmRestore, { onSuccess: () => setConfirmRestore(null) })
        }}
      />

      {/* Telegram send dialog */}
      <Dialog open={!!telegramDialog} onOpenChange={(open) => !open && setTelegramDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('backup.sendToTelegram', { defaultValue: 'Send to Telegram' })}</DialogTitle>
            <DialogDescription className="text-dark-300 text-xs font-mono truncate">{telegramDialog?.filename}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-dark-200 mb-1 block">Chat ID <span className="text-dark-400">({t('backup.leaveEmptyDefault', { defaultValue: 'leave empty for default' })})</span></label>
              <Input
                placeholder="-100123456789"
                value={telegramDialog?.chatId || ''}
                onChange={(e) => setTelegramDialog((p) => p ? { ...p, chatId: e.target.value } : null)}
              />
            </div>
            <div>
              <label className="text-xs text-dark-200 mb-1 block">Topic ID <span className="text-dark-400">({t('common.optional', { defaultValue: 'optional' })})</span></label>
              <Input
                placeholder="42"
                value={telegramDialog?.topicId || ''}
                onChange={(e) => setTelegramDialog((p) => p ? { ...p, topicId: e.target.value } : null)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTelegramDialog(null)}>{t('common.cancel')}</Button>
            <Button
              onClick={() => {
                if (!telegramDialog) return
                telegramMutation.mutate({
                  filename: telegramDialog.filename,
                  chatId: telegramDialog.chatId || undefined,
                  topicId: telegramDialog.topicId ? parseInt(telegramDialog.topicId) : undefined,
                })
              }}
              disabled={telegramMutation.isPending}
              className="gap-1.5"
            >
              {telegramMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              {t('backup.send', { defaultValue: 'Send' })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}


// ── Import Tab ──────────────────────────────────────────────────

function ImportTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const { data: files = [] } = useQuery({
    queryKey: ['backup-files'],
    queryFn: backupApi.listFiles,
  })

  const configFiles = files.filter((f) => f.filename.startsWith('config_backup_'))
  const userFiles = files.filter(
    (f) => f.filename.endsWith('.json') && !f.filename.startsWith('config_backup_'),
  )

  const importConfig = useMutation({
    mutationFn: ({ filename, overwrite }: { filename: string; overwrite: boolean }) =>
      backupApi.importConfig(filename, overwrite),
    onSuccess: (data) => {
      toast.success(t('backup.importConfigSuccess', { imported: data.imported_count, skipped: data.skipped_count }))
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || t('backup.importFailed')),
  })

  const importUsers = useMutation({
    mutationFn: backupApi.importUsers,
    onSuccess: (data) => {
      toast.success(t('backup.importUsersSuccess', { imported: data.imported_count, skipped: data.skipped_count }))
      if (data.errors.length > 0) toast.warning(t('backup.importUsersErrors', { count: data.errors.length }))
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || t('backup.importFailed')),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-cyan-400" />
            {t('backup.importConfig')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {configFiles.length === 0 ? (
            <EmptyState icon={Settings2} title={t('backup.noConfigFiles')} size="sm" />
          ) : (
            <div className="space-y-2">
              {configFiles.map((file) => (
                <div key={file.filename} className="flex items-center gap-3 px-3 py-3 rounded-xl bg-[var(--glass-bg)]">
                  <FileJson className="w-5 h-5 text-cyan-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate font-mono">{file.filename}</p>
                    <p className="text-xs text-dark-300">{formatBytes(file.size_bytes)}</p>
                  </div>
                  <div className="flex gap-1.5 flex-shrink-0">
                    <Button
                      size="sm" variant="outline" className="gap-1.5 text-xs"
                      disabled={importConfig.isPending}
                      onClick={() => importConfig.mutate({ filename: file.filename, overwrite: false })}
                    >
                      {importConfig.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                      {t('backup.importMissing')}
                    </Button>
                    <Button
                      size="sm" variant="destructive" className="gap-1.5 text-xs"
                      disabled={importConfig.isPending}
                      onClick={() => importConfig.mutate({ filename: file.filename, overwrite: true })}
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      {t('backup.importOverwrite')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <Users className="w-4 h-4 text-amber-400" />
            {t('backup.importUsers')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2.5 mb-4 p-3 rounded-xl bg-amber-500/5 border border-amber-500/15">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-200/80">{t('backup.importUsersWarning')}</p>
          </div>
          {userFiles.length === 0 ? (
            <EmptyState icon={Users} title={t('backup.noUserFiles')} size="sm" />
          ) : (
            <div className="space-y-2">
              {userFiles.map((file) => (
                <div key={file.filename} className="flex items-center gap-3 px-3 py-3 rounded-xl bg-[var(--glass-bg)]">
                  <FileJson className="w-5 h-5 text-amber-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate font-mono">{file.filename}</p>
                    <p className="text-xs text-dark-300">{formatBytes(file.size_bytes)}</p>
                  </div>
                  <Button
                    size="sm" className="gap-1.5 text-xs flex-shrink-0"
                    disabled={importUsers.isPending}
                    onClick={() => importUsers.mutate(file.filename)}
                  >
                    {importUsers.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                    {t('backup.importStart')}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}


// ── History Tab ─────────────────────────────────────────────────

function HistoryTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()

  const { data: log = [], isLoading } = useQuery({
    queryKey: ['backup-log'],
    queryFn: () => backupApi.getLog(),
  })

  const typeColor: Record<string, string> = {
    database: 'text-emerald-400',
    config: 'text-cyan-400',
    restore: 'text-amber-400',
    config_import: 'text-primary-400',
    user_import: 'text-amber-400',
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
          <Clock className="w-4 h-4 text-primary-400" />
          {t('backup.history')}
          <Badge variant="secondary" className="ml-auto font-mono">{log.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-14 w-full rounded-lg" />)}
          </div>
        ) : log.length === 0 ? (
          <EmptyState icon={Clock} title={t('backup.noHistory')} />
        ) : (
          <div className="space-y-1.5">
            {log.map((entry, i) => (
              <div
                key={entry.id}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-[var(--glass-bg)] animate-fade-in-up"
                style={{ animationDelay: `${i * 0.02}s` }}
              >
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${entry.backup_type === 'restore' ? 'bg-amber-400' : 'bg-emerald-400'}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm text-white truncate font-mono">{entry.filename}</p>
                    <span className={`text-[10px] font-medium uppercase tracking-wider ${typeColor[entry.backup_type] || 'text-dark-300'}`}>
                      {entry.backup_type}
                    </span>
                  </div>
                  <p className="text-xs text-dark-400 mt-0.5">
                    {entry.created_by_username && <><span className="text-dark-300">{entry.created_by_username}</span> &middot; </>}
                    {formatDate(entry.created_at)}
                    {entry.notes && <> &middot; {entry.notes}</>}
                  </p>
                </div>
                {entry.size_bytes > 0 && (
                  <span className="text-xs text-dark-400 font-mono flex-shrink-0">{formatBytes(entry.size_bytes)}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}


// ── Main Page ───────────────────────────────────────────────────

export default function Backup() {
  const { t } = useTranslation()

  return (
    <PermissionGate resource="backups" action="view" fallback={null}>
      <div className="space-y-6 animate-fade-in">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10">
            <Shield className="w-6 h-6 text-primary-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">{t('backup.title')}</h1>
            <p className="text-sm text-dark-300 mt-0.5">{t('backup.subtitle')}</p>
          </div>
        </div>

        <Tabs defaultValue="backups">
          <TabsList>
            <TabsTrigger value="backups" className="gap-1.5">
              <Archive className="w-3.5 h-3.5" />
              {t('backup.tabs.backups')}
            </TabsTrigger>
            <TabsTrigger value="import" className="gap-1.5">
              <Upload className="w-3.5 h-3.5" />
              {t('backup.tabs.import')}
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              {t('backup.tabs.history')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="backups" className="mt-4">
            <BackupsTab />
          </TabsContent>
          <TabsContent value="import" className="mt-4">
            <ImportTab />
          </TabsContent>
          <TabsContent value="history" className="mt-4">
            <HistoryTab />
          </TabsContent>
        </Tabs>
      </div>
    </PermissionGate>
  )
}
