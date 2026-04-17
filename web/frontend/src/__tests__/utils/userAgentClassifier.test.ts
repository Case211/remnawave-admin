import { describe, it, expect } from 'vitest'
import { classifyUserAgent, uaBadgeTone } from '@/utils/userAgentClassifier'

describe('classifyUserAgent', () => {
  describe('whitelist', () => {
    it.each([
      'Happ/4.7.2/ios/',
      'FlClash X/v0.2.1 Platform/android',
      'v2rayN/9.99',
      'koala-clash/v0.2.8',
      'Throne/1.0.13 (Prefer ClashMeta Format)',
      'sing-box/1.8.0',
      'HiddifyNext/2.0.0',
      'Clash Verge/1.5.0',
      'ClashMeta/2.0.0',
      'ShadowRocket/2.2.35',
    ])('accepts %s', (ua) => {
      expect(classifyUserAgent(ua)).toBe('valid')
    })
  })

  describe('link in UA', () => {
    it.each([
      'vless://25fd819e-4f1e-4f3b-85e7-658769db2b2d@host.com:443',
      'vmess://eyJhZGQiOiJ...',
      'trojan://password@host.com:443',
      'https://example.com/sub/foo',
      'hysteria2://host.com',
    ])('detects %s as link_in_ua', (ua) => {
      expect(classifyUserAgent(ua)).toBe('link_in_ua')
    })
  })

  describe('bot library', () => {
    it.each([
      'Go-http-client/2.0',
      'curl/8.0.1',
      'Wget/1.21.4',
      'python-requests/2.31.0',
      'PostmanRuntime/7.32.3',
    ])('detects %s as bot_library', (ua) => {
      expect(classifyUserAgent(ua)).toBe('bot_library')
    })
  })

  it('detects Mozilla/5.0 bare as stub', () => {
    expect(classifyUserAgent('Mozilla/5.0')).toBe('stub')
  })

  it('returns empty for null/empty/whitespace', () => {
    expect(classifyUserAgent(null)).toBe('empty')
    expect(classifyUserAgent(undefined)).toBe('empty')
    expect(classifyUserAgent('')).toBe('empty')
    expect(classifyUserAgent('   ')).toBe('empty')
  })

  it('returns unknown for okhttp (grey zone)', () => {
    expect(classifyUserAgent('okhttp/4.12.0')).toBe('unknown')
  })

  it('is case-insensitive', () => {
    expect(classifyUserAgent('HAPP/4.7.2')).toBe('valid')
    expect(classifyUserAgent('happ/4.7.2')).toBe('valid')
  })
})

describe('uaBadgeTone', () => {
  it('returns null for valid', () => {
    expect(uaBadgeTone('valid')).toBeNull()
  })

  it('returns red for link/bot', () => {
    expect(uaBadgeTone('link_in_ua')).toBe('red')
    expect(uaBadgeTone('bot_library')).toBe('red')
  })

  it('returns yellow for stub/empty', () => {
    expect(uaBadgeTone('stub')).toBe('yellow')
    expect(uaBadgeTone('empty')).toBe('yellow')
  })

  it('returns gray for unknown', () => {
    expect(uaBadgeTone('unknown')).toBe('gray')
  })
})
