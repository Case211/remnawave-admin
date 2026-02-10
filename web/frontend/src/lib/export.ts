import Papa from 'papaparse'

/**
 * Export data as CSV file and trigger download.
 */
export function exportCSV(data: Record<string, unknown>[], filename: string) {
  const csv = Papa.unparse(data)
  downloadBlob(csv, `${filename}.csv`, 'text/csv;charset=utf-8;')
}

/**
 * Export data as JSON file and trigger download.
 */
export function exportJSON(data: unknown, filename: string) {
  const json = JSON.stringify(data, null, 2)
  downloadBlob(json, `${filename}.json`, 'application/json;charset=utf-8;')
}

/**
 * Format bytes to human-readable string for export.
 */
export function formatBytesForExport(bytes: number | null | undefined): string {
  if (!bytes) return '0'
  const gb = bytes / (1024 * 1024 * 1024)
  if (gb >= 1) return `${gb.toFixed(2)} GB`
  const mb = bytes / (1024 * 1024)
  if (mb >= 1) return `${mb.toFixed(2)} MB`
  return `${(bytes / 1024).toFixed(2)} KB`
}

function downloadBlob(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
