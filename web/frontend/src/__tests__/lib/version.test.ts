import { describe, it, expect } from 'vitest'
import { cmpVersions } from '@/lib/version'

describe('cmpVersions', () => {
  it.each([
    ['1.8.1', '1.5.0', 1],
    ['1.5.0', '1.8.1', -1],
    ['1.8.1', '1.8.1', 0],
    ['v1.8.1', '1.8.1', 0],
    ['1.10.0', '1.9.9', 1],
    ['2.0', '2.0.0', 0],
    ['1.8.1-beta', '1.8.0', 1],
  ])('cmpVersions(%s, %s) = %i', (a, b, expected) => {
    expect(cmpVersions(a, b)).toBe(expected)
  })
})
