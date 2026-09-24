/**
 * Значения одной категории из ответа GET /settings: { key: value }.
 *
 * Ответ кэшируется под общим ключом ['settings'] — страницы кладут туда
 * полный ответ и берут свой кусок через select этой функцией.
 */
export function settingsOf(data: unknown, category: string): Record<string, string> {
  const items = (data as { categories?: Record<string, { key: string; value?: string | null; default_value?: string | null }[]> })
    ?.categories?.[category] || []
  const result: Record<string, string> = {}
  for (const item of items) result[item.key] = item.value ?? item.default_value ?? ''
  return result
}
