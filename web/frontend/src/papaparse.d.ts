declare module 'papaparse' {
  interface UnparseConfig {
    quotes?: boolean | boolean[]
    quoteChar?: string
    escapeChar?: string
    delimiter?: string
    header?: boolean
    newline?: string
    skipEmptyLines?: boolean | 'greedy'
    columns?: string[]
  }

  interface UnparseObject {
    fields: string[]
    data: unknown[][]
  }

  const Papa: {
    unparse(data: unknown[] | UnparseObject, config?: UnparseConfig): string
  }

  export default Papa
}
