/**
 * Сравнение версий по числовым сегментам: 1, если a > b; -1, если a < b; 0 при равенстве.
 * Ведущая «v» и суффиксы пре-релиза («-beta», «+build») не учитываются.
 */
export function cmpVersions(a: string, b: string): number {
  const parse = (v: string) =>
    v.trim().replace(/^v/i, '').split(/[-+]/)[0].split('.').map((s) => parseInt(s, 10) || 0)
  const pa = parse(a)
  const pb = parse(b)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (d !== 0) return d > 0 ? 1 : -1
  }
  return 0
}
