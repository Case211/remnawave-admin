/**
 * API client for the plugin store (keyless model, contract v1.1).
 *
 * The panel backend proxies the licensing server: the browser never talks
 * to license.nexuslink.ru directly. All endpoints are superadmin-only.
 */
import client from '@/api/client'

const BASE = '/admin/plugins'

/** Catalog texts arrive localized per language: ``{ru: "...", en: "..."}``. */
export type CatalogText = Record<string, string>

export interface CatalogPrice {
  rub: number
  usdt: number
}

export interface CatalogTariff {
  code: string
  period: string
  price: CatalogPrice
  limits: { ai_calls?: number | null }
  /** Витринное имя плана; пусто — показываем код. */
  title?: CatalogText | null
  /** Чем отличается от соседних планов (на каком ИИ считается разбор). */
  note?: CatalogText | null
  /** Порядок кнопок в карточке. */
  sort?: number
}

export interface CatalogTopup {
  code: string
  ai_calls: number
  price: CatalogPrice
}

export interface CatalogPlugin {
  id: string
  name: CatalogText
  summary: CatalogText
  features: CatalogText[]
  data_sent_to_cloud: CatalogText
  latest_version: string
  wheel_sha256?: string | null
  min_panel_version?: string | null
  /**
   * Плагин снят с продажи: карточка в витрине остаётся, но tariffs/topups
   * приходят пустыми и сервер отказывает в покупке и пробном периоде.
   * Оплаченное продолжает работать. Поля нет — сервер старой версии, продаётся.
   */
  purchasable?: boolean
  /** Чем заменить цену («временно недоступно»); пусто — свой текст. */
  sale_note?: CatalogText | null
  tariffs: CatalogTariff[]
  topups: CatalogTopup[]
}

export interface CatalogResponse {
  catalog_version: number
  plugins: CatalogPlugin[]
}

export type EntitlementState = 'active' | 'grace' | 'expired'

export interface EntitlementQuota {
  period_limit: number
  used: number
  topup_left: number
}

export interface PluginEntitlement {
  state: EntitlementState
  tier?: string | null
  paid_until?: number | null
  latest_version?: string | null
  quota?: EntitlementQuota | null
}

export interface StoreMessage {
  level: string
  text_i18n: string
  args?: Record<string, unknown>
}

export interface StoreStatus {
  registered: boolean
  instance_id?: string | null
  plugins: Record<string, PluginEntitlement>
  jwt_exp?: number | null
  last_sync_ok?: number | null
  last_error?: string | null
  messages: StoreMessage[]
  /** plugin_id → version of the code actually loaded into the process. */
  installed: Record<string, string>
}

export interface PurchaseItem {
  type: 'subscription' | 'topup'
  plugin_id: string
  tariff?: string
  months?: number
  pack?: string
}

export interface OrderPayment {
  method: string
  address: string
  amount: string
  memo: string
}

export interface PurchaseResponse {
  order_id: string
  payment: OrderPayment
  expires_at: number
}

export type OrderState = 'pending' | 'paid' | 'expired' | 'cancelled'

export interface OrderStatusResponse {
  status: OrderState
  amount?: string
  memo?: string
  expires_at?: number
}

export interface TransferOutResponse {
  transfer_code: string
  valid_until: number
}

export interface SimpleResponse {
  ok: boolean
  requires_restart: boolean
  message?: string | null
}

export async function fetchCatalog(): Promise<CatalogResponse> {
  const { data } = await client.get<CatalogResponse>(`${BASE}/catalog`)
  return data
}

export async function fetchStoreStatus(): Promise<StoreStatus> {
  const { data } = await client.get<StoreStatus>(`${BASE}/status`)
  return data
}

export async function syncNow(): Promise<SimpleResponse> {
  const { data } = await client.post<SimpleResponse>(`${BASE}/sync`)
  return data
}

export async function connectStore(): Promise<SimpleResponse> {
  const { data } = await client.post<SimpleResponse>(`${BASE}/connect`)
  return data
}

export async function disconnectStore(): Promise<SimpleResponse> {
  const { data } = await client.post<SimpleResponse>(`${BASE}/disconnect`)
  return data
}

export async function startTrial(): Promise<SimpleResponse> {
  const { data } = await client.post<SimpleResponse>(`${BASE}/trial`)
  return data
}

export async function purchase(items: PurchaseItem[]): Promise<PurchaseResponse> {
  const { data } = await client.post<PurchaseResponse>(`${BASE}/purchase`, { items })
  return data
}

export async function fetchOrderStatus(orderId: string): Promise<OrderStatusResponse> {
  const { data } = await client.get<OrderStatusResponse>(`${BASE}/order/${orderId}`)
  return data
}

export async function redeemCode(code: string): Promise<SimpleResponse> {
  const { data } = await client.post<SimpleResponse>(`${BASE}/redeem`, { code })
  return data
}

export async function transferOut(): Promise<TransferOutResponse> {
  const { data } = await client.post<TransferOutResponse>(`${BASE}/transfer-out`)
  return data
}

export async function installPlugin(pluginId: string): Promise<SimpleResponse> {
  const { data } = await client.post<SimpleResponse>(`${BASE}/install/${pluginId}`, null, {
    timeout: 180_000,
  })
  return data
}

export async function uploadWheel(file: File): Promise<SimpleResponse> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await client.post<SimpleResponse>(`${BASE}/upload`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
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

/**
 * Extract the structured licensing-server error code from an axios error
 * (backend raises ``HTTPException(detail={code, ...})``). Returns null for
 * network failures and non-structured errors so the caller can fall back
 * to a generic message.
 */
export function licenseErrorCode(err: unknown): string | null {
  if (typeof err !== 'object' || err === null) return null
  const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  if (typeof detail !== 'object' || detail === null) return null
  const code = (detail as { code?: unknown }).code
  return typeof code === 'string' ? code : null
}
