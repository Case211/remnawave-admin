import client from './client'

export interface BackupFile {
  filename: string
  size_bytes: number
  created_at: string
}

export interface BackupResult {
  filename: string
  size_bytes: number
  backup_type: string
}

export interface BackupLogItem {
  id: number
  filename: string
  backup_type: string
  size_bytes: number
  status: string
  created_by_username: string | null
  notes: string | null
  created_at: string
}

export interface ImportConfigResult {
  imported_count: number
  skipped_count: number
}

export interface ImportUsersResult {
  imported_count: number
  skipped_count: number
  errors: Array<{ username: string; error: string }>
}

export interface BackupPreview {
  filename: string
  size_bytes: number
  created_at: string
  type: string
  exported_at?: string
  schema_version?: string
  settings_count?: number
  pg_version?: string
  error?: string
}

export interface BackupStatus {
  backup_size_bytes: number
  file_count: number
  disk_free_bytes: number
  disk_total_bytes: number
  last_backup: {
    filename: string
    backup_type: string
    size_bytes: number
    status: string
    created_at: string
  } | null
}

export interface S3Settings {
  endpoint: string
  bucket: string
  region: string
  prefix: string
  path_style: boolean
  auto_upload: boolean
  keep_count: number
  has_credentials: boolean
  access_key_masked: string
}

export interface S3SettingsPayload {
  endpoint: string
  bucket: string
  region: string
  prefix: string
  path_style: boolean
  auto_upload: boolean
  keep_count: number
  /** null — ключи не трогаем, пустая строка — стираем */
  access_key?: string | null
  secret_key?: string | null
}

export interface S3Object {
  key: string
  filename: string
  size: number
  last_modified: string
}

export const backupApi = {
  listFiles: async (): Promise<BackupFile[]> => {
    const { data } = await client.get('/backups/')
    return Array.isArray(data) ? data : []
  },

  getLog: async (
    limit = 50,
    search?: string,
    backupType?: string,
  ): Promise<BackupLogItem[]> => {
    const { data } = await client.get('/backups/log', {
      params: {
        limit,
        ...(search ? { search } : {}),
        ...(backupType ? { backup_type: backupType } : {}),
      },
    })
    return Array.isArray(data) ? data : []
  },

  previewBackup: async (filename: string): Promise<BackupPreview> => {
    const { data } = await client.get(`/backups/preview/${filename}`)
    return data
  },

  getStatus: async (): Promise<BackupStatus> => {
    const { data } = await client.get('/backups/status')
    return data
  },

  createDatabaseBackup: async (): Promise<BackupResult> => {
    const { data } = await client.post('/backups/database')
    return data
  },

  createConfigBackup: async (): Promise<BackupResult> => {
    const { data } = await client.post('/backups/config')
    return data
  },

  downloadBackup: (filename: string): string => {
    return `/api/v2/backups/download/${encodeURIComponent(filename)}`
  },

  deleteBackup: async (filename: string): Promise<void> => {
    await client.delete(`/backups/${encodeURIComponent(filename)}`)
  },

  restoreDatabase: async (filename: string): Promise<{ status: string; message: string }> => {
    const { data } = await client.post('/backups/restore', { filename })
    return data
  },

  importConfig: async (filename: string, overwrite = false): Promise<ImportConfigResult> => {
    const { data } = await client.post('/backups/import-config', { filename, overwrite })
    return data
  },

  importUsers: async (filename: string): Promise<ImportUsersResult> => {
    const { data } = await client.post('/backups/import-users', { filename })
    return data
  },

  // Full config export/import
  exportFullConfig: async () => {
    const { data } = await client.post('/backups/export-full-config')
    return data
  },
  importFullConfig: async (config: Record<string, unknown>, strategy = 'skip', sections?: string[]) => {
    const { data } = await client.post('/backups/import-full-config', { config, strategy, sections })
    return data
  },

  getDiskUsage: async () => {
    const { data } = await client.get('/backups/disk-usage')
    return data as { backup_size_bytes: number; file_count: number; disk_free_bytes: number; disk_total_bytes: number }
  },

  uploadFile: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await client.post('/backups/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  rotateBackups: async (keepCount = 10, keepDays = 30) => {
    const { data } = await client.post('/backups/rotate', null, { params: { keep_count: keepCount, keep_days: keepDays } })
    return data as { status: string; deleted: number }
  },

  sendToTelegram: async (filename: string, chatId?: string, topicId?: number) => {
    const { data } = await client.post('/backups/send-telegram', { filename, chat_id: chatId, topic_id: topicId })
    return data as { filename: string; parts_sent: number; size_bytes: number }
  },

  // S3-совместимое хранилище
  getS3Settings: async (): Promise<S3Settings> => {
    const { data } = await client.get('/backups/s3/settings')
    return data
  },

  updateS3Settings: async (payload: S3SettingsPayload): Promise<S3Settings> => {
    const { data } = await client.put('/backups/s3/settings', payload)
    return data
  },

  testS3: async () => {
    const { data } = await client.post('/backups/s3/test')
    return data as { success: boolean; bucket: string; endpoint: string }
  },

  uploadToS3: async (filename: string) => {
    const { data } = await client.post(`/backups/s3/upload/${encodeURIComponent(filename)}`)
    return data as { success: boolean; key: string; size: number }
  },

  listS3Objects: async (): Promise<S3Object[]> => {
    const { data } = await client.get('/backups/s3/objects')
    return Array.isArray(data) ? data : []
  },

  deleteS3Object: async (key: string) => {
    await client.delete(`/backups/s3/objects/${key.split('/').map(encodeURIComponent).join('/')}`)
  },
}
