import client from '@/api/client'

const BASE = '/admin/plugins'

export interface InstalledPluginInfo {
  plugin_id: string
  name?: string | null
  version?: string | null
  license_state?: 'valid' | 'expired' | 'missing' | 'not_required' | null
  license_set: boolean
  wheel_name?: string | null
  installed_at?: string | null
  updated_at?: string | null
}

export interface WheelFileInfo {
  filename: string
  package_name: string
  version: string
}

export interface PluginInventoryResponse {
  installed: InstalledPluginInfo[]
  pending_wheels: WheelFileInfo[]
  plugins_dir: string
  requires_restart: boolean
}

export interface InstallResponse {
  plugin_id?: string | null
  wheel_name: string
  version: string
  requires_restart: boolean
  message: string
}

export interface MasterLicenseResponse {
  plugin_ids: string[]
  expires_at?: string | null
  tier?: string | null
  sub?: string | null
  requires_restart: boolean
}

export interface SimpleResponse {
  ok: boolean
  requires_restart: boolean
  message?: string | null
}

export async function fetchPluginsInventory(): Promise<PluginInventoryResponse> {
  const { data } = await client.get<PluginInventoryResponse>(BASE)
  return data
}

export async function uploadPlugin(args: {
  file: File
  pluginId: string
  jwtToken: string
}): Promise<InstallResponse> {
  const fd = new FormData()
  fd.append('file', args.file)
  fd.append('plugin_id', args.pluginId)
  fd.append('jwt_token', args.jwtToken)
  const { data } = await client.post<InstallResponse>(`${BASE}/upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export async function applyMasterLicense(jwtToken: string): Promise<MasterLicenseResponse> {
  const { data } = await client.post<MasterLicenseResponse>(`${BASE}/master-license`, {
    jwt_token: jwtToken,
  })
  return data
}

export async function updateLicense(args: {
  pluginId: string
  jwtToken: string
}): Promise<SimpleResponse> {
  const { data } = await client.put<SimpleResponse>(`${BASE}/license`, {
    plugin_id: args.pluginId,
    jwt_token: args.jwtToken,
  })
  return data
}

export async function uninstallPlugin(pluginId: string): Promise<SimpleResponse> {
  const { data } = await client.delete<SimpleResponse>(`${BASE}/${pluginId}`)
  return data
}

export async function restartBackend(): Promise<SimpleResponse> {
  const { data } = await client.post<SimpleResponse>(`${BASE}/restart`)
  return data
}
