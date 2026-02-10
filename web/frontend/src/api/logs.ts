import client from './client'

export interface LogFile {
  key: string
  filename: string
  exists: boolean
  size_bytes: number
  modified_at: string | null
}

export interface LogEntry {
  timestamp: string | null
  level: string | null
  source: string | null
  message: string
}

export const logsApi = {
  files: async (): Promise<LogFile[]> => {
    const { data } = await client.get('/logs/files')
    return data
  },

  tail: async (params: {
    file?: string
    lines?: number
    level?: string
    search?: string
  }): Promise<{ items: LogEntry[]; file: string; total: number }> => {
    const { data } = await client.get('/logs/tail', { params })
    return data
  },
}
