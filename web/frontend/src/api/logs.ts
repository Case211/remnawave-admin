import client from './client'

export interface LogFile {
  key: string
  filename: string | null
  exists: boolean
  size_bytes: number
  modified_at: string | null
}

export interface LogEntry {
  timestamp: string | null
  level: string | null
  source: string | null
  message: string
  extra?: Record<string, unknown> | null
}

export interface LogLevels {
  backend: string
  bot: string
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

  getLogLevel: async (): Promise<LogLevels> => {
    const { data } = await client.get('/logs/level')
    return data
  },

  setLogLevel: async (component: string, level: string): Promise<void> => {
    await client.put('/logs/level', null, { params: { component, level } })
  },

  sendFrontendLogs: async (entries: unknown[]): Promise<void> => {
    await client.post('/logs/frontend', entries)
  },
}
