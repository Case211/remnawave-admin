/**
 * Вкладка «Репутация» BS-Check — числится ли IP ноды в фрод/абуз-базах,
 * помечен ли как VPN/proxy/hosting/tor (ip-api / ipinfo / IPQualityScore /
 * AbuseIPDB). Дополняет операторскую БС-проверку другим источником.
 *
 * Нюанс: для VPN-ноды флаги vpn/proxy/hosting ОЖИДАЕМЫ — реально важен
 * abuse-score / свежие жалобы (из-за них IP попадает в блок).
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { reputationApi, RepProvider, RepResult } from '@/api/reputation'
import { bscheckApi } from '@/api/bscheck'
import { usePermissionStore } from '@/store/permissionStore'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { ShieldCheck, ShieldAlert, Loader2, Key, Check, Globe, Crosshair } from '@/components/brand/icons'
import { cn } from '@/lib/utils'

function scoreTone(score: number): string {
  if (score >= 75) return 'bg-red-500/20 text-red-300'
  if (score >= 40) return 'bg-amber-500/20 text-amber-300'
  return 'bg-green-500/20 text-green-300'
}

/** Вердикт по IP — в основном по abuse (флаги vpn/hosting для ноды ожидаемы). */
function verdict(results: RepResult[], t: (k: string) => string): { label: string; tone: string } {
  const clean = results.filter((r) => !r.error)
  const blocked = clean.some((r) => r.blocked)
  const abuse = clean.some((r) => r.recent_abuse) ||
    clean.some((r) => r.provider === 'abuseipdb' && (r.score ?? 0) >= 25)
  const maxScore = Math.max(0, ...clean.map((r) => r.score ?? 0))
  if (blocked) return { label: t('reputation.verdictBlocked'), tone: 'bg-red-500/20 text-red-300' }
  if (abuse || maxScore >= 85) return { label: t('reputation.verdictDirty'), tone: 'bg-red-500/20 text-red-300' }
  if (maxScore >= 50) return { label: t('reputation.verdictSuspicious'), tone: 'bg-amber-500/20 text-amber-300' }
  return { label: t('reputation.verdictClean'), tone: 'bg-green-500/20 text-green-300' }
}

function Flag({ on, label, tone }: { on: boolean | null | undefined; label: string; tone: string }) {
  if (!on) return null
  return <Badge className={cn('text-[10px]', tone)}>{label}</Badge>
}

export function RepCard({ r }: { r: RepResult }) {
  const { t } = useTranslation()
  const providerName: Record<string, string> = {
    ipapi: 'ip-api', ipinfo: 'ipinfo', ipqs: 'IPQualityScore',
    abuseipdb: 'AbuseIPDB', cheburcheck: 'CheburCheck (РКН)', vpndetection: 'VPNDetection',
  }
  return (
    <div className="rounded-lg border border-[var(--glass-border)] p-3 space-y-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-medium">{providerName[r.provider] || r.provider}</span>
        {r.score != null && (
          <Badge className={cn('text-[10px]', scoreTone(r.score))}>
            {r.provider === 'abuseipdb' ? t('reputation.abuse') : t('reputation.fraud')}: {r.score}
          </Badge>
        )}
        {r.blocked != null && (
          <Badge className={cn('text-[10px]', r.blocked ? 'bg-red-500/20 text-red-300' : 'bg-green-500/20 text-green-300')}>
            {r.blocked ? t('reputation.blockedRkn') : t('reputation.notBlocked')}
          </Badge>
        )}
        {r.country && <span className="ml-auto text-[11px] text-muted-foreground">{r.country}</span>}
      </div>
      {r.error ? (
        <p className="text-xs text-red-300">{r.error}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5">
            <Flag on={r.recent_abuse} label={t('reputation.flagAbuse')} tone="bg-red-500/20 text-red-300" />
            <Flag on={r.is_tor} label="Tor" tone="bg-red-500/20 text-red-300" />
            <Flag on={r.is_vpn} label="VPN" tone="bg-amber-500/20 text-amber-300" />
            <Flag on={r.is_proxy} label="Proxy" tone="bg-amber-500/20 text-amber-300" />
            <Flag on={r.is_hosting} label="Hosting" tone="bg-white/10 text-muted-foreground" />
          </div>
          {r.rkn_domain && <p className="text-[11px] text-red-300">{t('reputation.rknDomain')}: {r.rkn_domain}</p>}
          {r.blocked_subnets && r.blocked_subnets.length > 0 && (
            <p className="text-[11px] text-muted-foreground truncate">{r.blocked_subnets.join(', ')}</p>
          )}
          {(r.asn || r.org) && (
            <p className="text-[11px] text-muted-foreground truncate">{[r.asn, r.org].filter(Boolean).join(' · ')}</p>
          )}
        </>
      )}
    </div>
  )
}

function TokenDialog({ provider, onClose, onSaved }: {
  provider: RepProvider; onClose: () => void; onSaved: () => void
}) {
  const { t } = useTranslation()
  const [token, setToken] = useState('')
  const save = useMutation({
    mutationFn: () => reputationApi.setCreds(provider.slug, token.trim()),
    onSuccess: () => { toast.success(t('reputation.tokenSaved')); onSaved() },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })
  const del = useMutation({
    mutationFn: () => reputationApi.delCreds(provider.slug),
    onSuccess: () => { toast.success(t('reputation.tokenRemoved')); onSaved() },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle className="text-base flex items-center gap-2"><Key className="w-4 h-4 text-primary-400" />{provider.name}</DialogTitle></DialogHeader>
        <div className="space-y-2">
          <Label>{t('reputation.token')}</Label>
          <Input type="password" value={token} className="font-mono" placeholder="API token"
            onChange={(e) => setToken(e.target.value)} />
          {provider.signup_url && (
            <a href={provider.signup_url} target="_blank" rel="noreferrer" className="text-[11px] text-primary-400 hover:underline">
              {t('reputation.getToken')} ↗
            </a>
          )}
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          {provider.configured
            ? <Button variant="outline" className="text-red-400" disabled={del.isPending} onClick={() => del.mutate()}>{t('common.delete')}</Button>
            : <span />}
          <Button disabled={token.trim().length < 4 || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function ReputationTab() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const canCheck = usePermissionStore((s) => s.hasPermission)('reputation', 'check')
  const [ip, setIp] = useState('')
  const [current, setCurrent] = useState<{ target: string; results: RepResult[] } | null>(null)
  const [tokenProv, setTokenProv] = useState<RepProvider | null>(null)

  const { data: providers } = useQuery({ queryKey: ['rep-providers'], queryFn: reputationApi.providers })
  const { data: nodes } = useQuery({ queryKey: ['bscheck-nodes'], queryFn: bscheckApi.nodes })

  const lookup = useMutation({
    mutationFn: (target: string) => reputationApi.lookup(target),
    onSuccess: (d) => setCurrent(d),
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('common.error')),
  })

  const provs = providers || []
  const anyConfigured = provs.some((p) => p.configured)
  const v = current && current.results.length ? verdict(current.results, t) : null

  return (
    <div className="space-y-3">
      {/* Провайдеры */}
      <Card className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <ShieldCheck className="w-4 h-4 text-primary-400" />
          <span className="text-sm font-medium">{t('reputation.providers')}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {provs.map((p) => (
            <button key={p.slug} type="button" disabled={!p.needs_token || !canCheck}
              onClick={() => p.needs_token && canCheck && setTokenProv(p)}
              className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
                p.configured ? 'border-green-500/40 text-green-300' : 'border-[var(--glass-border)] text-muted-foreground',
                p.needs_token && canCheck && 'hover:text-white cursor-pointer')}>
              {p.configured ? <Check className="w-3 h-3" /> : p.needs_token ? <Key className="w-3 h-3" /> : <Globe className="w-3 h-3" />}
              {p.name}
              {!p.needs_token && <span className="text-[9px] text-muted-foreground">free</span>}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground mt-2">{t('reputation.providersHint')}</p>
      </Card>

      {/* Проверка IP */}
      <Card className="p-3 space-y-2">
        <Label>{t('reputation.checkIp')}</Label>
        <div className="flex items-center gap-2">
          <Input value={ip} className="font-mono" placeholder="1.2.3.4 или example.com"
            onChange={(e) => setIp(e.target.value)} />
          <Button className="gap-1.5 shrink-0" disabled={!ip.trim() || !anyConfigured || lookup.isPending}
            onClick={() => lookup.mutate(ip.trim())}>
            {lookup.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Crosshair className="w-4 h-4" />}
            {t('reputation.check')}
          </Button>
        </div>
        {!anyConfigured && <p className="text-[11px] text-amber-400">{t('reputation.noneConfigured')}</p>}

        {(nodes || []).length > 0 && (
          <div>
            <p className="text-[11px] text-muted-foreground mb-1">{t('reputation.orNode')}</p>
            <div className="flex flex-wrap gap-2">
              {(nodes || []).filter((n) => n.ip).map((n) => (
                <button key={n.uuid} type="button" disabled={!anyConfigured || lookup.isPending}
                  onClick={() => { setIp(n.ip as string); lookup.mutate(n.ip as string) }}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] border border-[var(--glass-border)] text-muted-foreground hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 disabled:opacity-50">
                  {n.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Результат */}
      {current && (
        <Card className="p-3 space-y-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm">{current.target}</span>
            {v && <Badge className={cn('gap-1', v.tone)}>{v.tone.includes('red') ? <ShieldAlert className="w-3.5 h-3.5" /> : <ShieldCheck className="w-3.5 h-3.5" />}{v.label}</Badge>}
          </div>
          {!current.results.length ? (
            <p className="text-sm text-muted-foreground">{t('reputation.noData')}</p>
          ) : (
            <>
              <div className="grid gap-2 sm:grid-cols-2">
                {current.results.map((r) => <RepCard key={r.provider} r={r} />)}
              </div>
              <p className="text-[11px] text-muted-foreground">{t('reputation.nodeNote')}</p>
            </>
          )}
        </Card>
      )}

      {!providers && <Skeleton className="h-24 w-full" />}

      {tokenProv && (
        <TokenDialog provider={tokenProv} onClose={() => setTokenProv(null)}
          onSaved={() => { setTokenProv(null); qc.invalidateQueries({ queryKey: ['rep-providers'] }) }} />
      )}
    </div>
  )
}
