import { describe, expect, it } from 'vitest'
import { parsePorts, toForm, toSettings, type ShaperForm } from '@/components/nodes/NodeShaperDialog'

const base: ShaperForm = {
  enabled: true,
  ports: '443, 8443',
  down: '50',
  up: '20',
  penaltyEnabled: false,
  penaltyMb: '2048',
  penaltyWindow: '300',
  penaltyRate: '10',
  penaltyMinutes: '15',
}

describe('parsePorts', () => {
  it('accepts commas, spaces and duplicates', () => {
    expect(parsePorts('8443, 443 443;2053')).toEqual([443, 2053, 8443])
  })

  it('rejects anything that is not a port', () => {
    expect(parsePorts('443, abc')).toBeNull()
    expect(parsePorts('0')).toBeNull()
    expect(parsePorts('70000')).toBeNull()
    expect(parsePorts('443.5')).toBeNull()
  })

  it('treats an empty field as no ports', () => {
    expect(parsePorts('  ')).toEqual([])
  })
})

describe('toSettings', () => {
  it('converts Mbit/s to kbit/s', () => {
    const { settings, error } = toSettings({ ...base, down: '0,5', up: '1.25' })
    expect(error).toBeNull()
    expect(settings?.down_kbit).toBe(500)
    expect(settings?.up_kbit).toBe(1250)
  })

  it('requires a port when enabled', () => {
    expect(toSettings({ ...base, ports: '' }).error).toBe('portsRequired')
  })

  it('lets a disabled shaper keep empty ports', () => {
    expect(toSettings({ ...base, enabled: false, ports: '' }).error).toBeNull()
  })

  it('refuses to enable a shaper that limits nothing', () => {
    expect(toSettings({ ...base, down: '0', up: '0' }).error).toBe('nothingToLimit')
  })

  it('accepts the penalty alone', () => {
    const { settings, error } = toSettings({ ...base, down: '0', up: '0', penaltyEnabled: true })
    expect(error).toBeNull()
    expect(settings?.penalty).toEqual({ enabled: true, mb: 2048, window_sec: 300, kbit: 10000, minutes: 15 })
  })

  it('checks the penalty against the agent limits', () => {
    expect(toSettings({ ...base, penaltyEnabled: true, penaltyWindow: '5' }).error).toBe('penaltyInvalid')
    expect(toSettings({ ...base, penaltyEnabled: true, penaltyRate: '0.01' }).error).toBe('penaltyInvalid')
  })

  it('keeps typed penalty values while it is switched off', () => {
    const { settings } = toSettings(base)
    expect(settings?.penalty).toEqual({ enabled: false, mb: 2048, window_sec: 300, kbit: 10000, minutes: 15 })
  })

  it('round-trips through the form', () => {
    const { settings } = toSettings({ ...base, penaltyEnabled: true })
    expect(toSettings(toForm(settings!)).settings).toEqual(settings)
  })
})
