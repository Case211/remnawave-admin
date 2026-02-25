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
import { useFormatters } from '@/lib/useFormatters'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function BackupTypeIcon({ type }: { type: string }) {
  const iconClass = "w-4 h-4 text-primary-400"
  switch (type) {
    case 'database':
      return <Database className={iconClass} />
    case 'config':
      return <Settings2 className={iconClass} />
    case 'restore':
      return <RotateCcw className={iconClass} />
    case 'config_import':
      return <Upload className={iconClass} />
    case 'user_import':
      return <Users className={iconClass} />
    default:
      return <HardDrive className="w-4 h-4 text-muted-foreground" />
  }
}

function BackupTypeBadge({ type }: { type: string }) {
  const accentCls = 'bg-primary/15 text-primary-400 border-primary/20'
  const colorMap: Record<string, string> = {
    database: accentCls,
    config: accentCls,
    restore: accentCls,
    config_import: accentCls,
    user_import: accentCls,
  }
  const cls = colorMap[type] || 'bg-muted text-muted-foreground border-border'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      <BackupTypeIcon type={type} />
      {type}
    </span>
  )
}


// ── Backups Tab ─────────────────────────────────────────────────

function BackupsTab() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const token = useAuthStore((s) => s.accessToken)

  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [confirmRestore, setConfirmRestore] = useState<string | null>(null)

  const { data: files = [], isLoading } = useQuery({
    queryKey: ['backup-files'],
    queryFn: backupApi.listFiles,
  })

  const createDbBackup = useMutation({
    mutationFn: backupApi.createDatabaseBackup,
    onSuccess: (data) => {
      toast.success(t('backup.created', { filename: data.filename }))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || t('backup.createFailed'))
    },
  })

  const createConfigBackup = useMutation({
    mutationFn: backupApi.createConfigBackup,
    onSuccess: (data) => {
      toast.success(t('backup.created', { filename: data.filename }))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || t('backup.createFailed'))
    },
  })

  const deleteBackup = useMutation({
    mutationFn: backupApi.deleteBackup,
    onSuccess: () => {
      toast.success(t('backup.deleted'))
      queryClient.invalidateQueries({ queryKey: ['backup-files'] })
    },
    onError: () => {
      toast.error(t('backup.deleteFailed'))
    },
  })

  const restoreDb = useMutation({
    mutationFn: backupApi.restoreDatabase,
    onSuccess: () => {
      toast.success(t('backup.restored'))
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || t('backup.restoreFailed'))
    },
  })

  const handleDownload = (filename: string) => {
    const url = backupApi.downloadBackup(filename)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    if (token) {
      // Use fetch with auth header to download
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

  return (
    <div className="space-y-6">
      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <PermissionGate resource="backups" action="create">
          <Button
            onClick={() => createDbBackup.mutate()}
            disabled={createDbBackup.isPending}
            className="gap-2"
          >
            <Database className="w-4 h-4" />
            {createDbBackup.isPending ? t('backup.creating') : t('backup.createDatabase')}
          </Button>
          <Button
            variant="outline"
            onClick={() => createConfigBackup.mutate()}
            disabled={createConfigBackup.isPending}
            className="gap-2"
          >
            <Settings2 className="w-4 h-4" />
            {createConfigBackup.isPending ? t('backup.creating') : t('backup.createConfig')}
          </Button>
        </PermissionGate>
      </div>

      {/* Files list */}
      <Card className="border-dark-600 bg-dark-800/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <HardDrive className="w-4 h-4" />
            {t('backup.files')}
            <Badge variant="secondary" className="ml-auto">{files.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-14 w-full rounded-lg" />
              ))}
            </div>
          ) : files.length === 0 ? (
            <div className="text-center py-8 text-dark-300">
              <HardDrive className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p>{t('backup.noFiles')}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {files.map((file) => (
                <div
                  key={file.filename}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-dark-700/50 hover:bg-dark-700 transition-colors"
                >
                  {file.filename.endsWith('.sql.gz') ? (
                    <Database className="w-5 h-5 text-primary-400 flex-shrink-0" />
                  ) : (
                    <FileJson className="w-5 h-5 text-primary-400 flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{file.filename}</p>
                    <p className="text-xs text-dark-300">
                      {formatBytes(file.size_bytes)} &middot; {formatDate(file.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-dark-200 hover:text-white"
                      onClick={() => handleDownload(file.filename)}
                      title={t('backup.download')}
                    >
                      <Download className="w-4 h-4" />
                    </Button>

                    {file.filename.endsWith('.sql.gz') && (
                      <PermissionGate resource="backups" action="create">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-primary-400 hover:text-primary-300"
                          onClick={() => setConfirmRestore(file.filename)}
                          title={t('backup.restore')}
                        >
                          <RotateCcw className="w-4 h-4" />
                        </Button>
                      </PermissionGate>
                    )}

                    <PermissionGate resource="backups" action="delete">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-red-400 hover:text-red-300"
                        onClick={() => setConfirmDelete(file.filename)}
                        title={t('backup.delete')}
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

      {/* Confirm delete dialog */}
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

      {/* Confirm restore dialog */}
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
      toast.success(
        t('backup.importConfigSuccess', {
          imported: data.imported_count,
          skipped: data.skipped_count,
        }),
      )
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || t('backup.importFailed'))
    },
  })

  const importUsers = useMutation({
    mutationFn: backupApi.importUsers,
    onSuccess: (data) => {
      toast.success(
        t('backup.importUsersSuccess', {
          imported: data.imported_count,
          skipped: data.skipped_count,
        }),
      )
      if (data.errors.length > 0) {
        toast.warning(t('backup.importUsersErrors', { count: data.errors.length }))
      }
      queryClient.invalidateQueries({ queryKey: ['backup-log'] })
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || t('backup.importFailed'))
    },
  })

  return (
    <div className="space-y-6">
      {/* Config import */}
      <Card className="border-dark-600 bg-dark-800/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <Settings2 className="w-4 h-4 text-primary-400" />
            {t('backup.importConfig')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {configFiles.length === 0 ? (
            <p className="text-sm text-dark-300 py-4 text-center">{t('backup.noConfigFiles')}</p>
          ) : (
            <div className="space-y-2">
              {configFiles.map((file) => (
                <div
                  key={file.filename}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-dark-700/50"
                >
                  <FileJson className="w-5 h-5 text-primary-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{file.filename}</p>
                    <p className="text-xs text-dark-300">{formatBytes(file.size_bytes)}</p>
                  </div>
                  <div className="flex gap-1.5 flex-shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5 text-xs"
                      disabled={importConfig.isPending}
                      onClick={() => importConfig.mutate({ filename: file.filename, overwrite: false })}
                    >
                      <Upload className="w-3.5 h-3.5" />
                      {t('backup.importMissing')}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      className="gap-1.5 text-xs"
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

      {/* User import */}
      <Card className="border-dark-600 bg-dark-800/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
            <Users className="w-4 h-4 text-primary-400" />
            {t('backup.importUsers')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2 mb-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-amber-300">{t('backup.importUsersWarning')}</p>
          </div>
          {userFiles.length === 0 ? (
            <p className="text-sm text-dark-300 py-4 text-center">{t('backup.noUserFiles')}</p>
          ) : (
            <div className="space-y-2">
              {userFiles.map((file) => (
                <div
                  key={file.filename}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-dark-700/50"
                >
                  <FileJson className="w-5 h-5 text-primary-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{file.filename}</p>
                    <p className="text-xs text-dark-300">{formatBytes(file.size_bytes)}</p>
                  </div>
                  <Button
                    size="sm"
                    className="gap-1.5 text-xs flex-shrink-0"
                    disabled={importUsers.isPending}
                    onClick={() => importUsers.mutate(file.filename)}
                  >
                    <Upload className="w-3.5 h-3.5" />
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

  return (
    <Card className="border-dark-600 bg-dark-800/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-dark-100 flex items-center gap-2">
          <Clock className="w-4 h-4" />
          {t('backup.history')}
          <Badge variant="secondary" className="ml-auto">{log.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : log.length === 0 ? (
          <div className="text-center py-8 text-dark-300">
            <Clock className="w-10 h-10 mx-auto mb-2 opacity-30" />
            <p>{t('backup.noHistory')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {log.map((entry) => (
              <div
                key={entry.id}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-dark-700/50"
              >
                <BackupTypeIcon type={entry.backup_type} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm text-white truncate">{entry.filename}</p>
                    <BackupTypeBadge type={entry.backup_type} />
                  </div>
                  <p className="text-xs text-dark-300">
                    {entry.created_by_username && `${entry.created_by_username} · `}
                    {formatDate(entry.created_at)}
                    {entry.notes && ` · ${entry.notes}`}
                  </p>
                </div>
                {entry.size_bytes > 0 && (
                  <span className="text-xs text-dark-300 flex-shrink-0">{formatBytes(entry.size_bytes)}</span>
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
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('backup.title')}</h1>
          <p className="text-sm text-dark-300 mt-1">{t('backup.subtitle')}</p>
        </div>

        <Tabs defaultValue="backups">
          <TabsList>
            <TabsTrigger value="backups">{t('backup.tabs.backups')}</TabsTrigger>
            <TabsTrigger value="import">{t('backup.tabs.import')}</TabsTrigger>
            <TabsTrigger value="history">{t('backup.tabs.history')}</TabsTrigger>
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
