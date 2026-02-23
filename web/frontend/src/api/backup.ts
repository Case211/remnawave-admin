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

export const backupApi = {
  listFiles: async (): Promise<BackupFile[]> => {
    const { data } = await client.get('/backups/')
    return Array.isArray(data) ? data : []
  },

  getLog: async (limit = 50): Promise<BackupLogItem[]> => {
    const { data } = await client.get('/backups/log', { params: { limit } })
    return Array.isArray(data) ? data : []
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
}
