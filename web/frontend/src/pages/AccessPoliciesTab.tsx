import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Shield, Users, Save } from 'lucide-react'
import {
  accessPoliciesApi,
  type PolicyDetail,
  type PolicyRule,
  type ResourceType,
  type ScopeType,
  type PolicyAction,
} from '@/api/accessPolicies'
import { squadsApi } from '@/api/squads'
import client from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { toast } from 'sonner'

interface Role {
  id: number
  name: string
  display_name?: string
}

interface ResourceOption {
  uuid: string
  label: string
}

const RESOURCE_TYPES: ResourceType[] = ['node', 'host', 'squad']
const SCOPE_TYPES: ScopeType[] = ['uuid', 'tag']
const ALL_ACTIONS: PolicyAction[] = ['view', 'edit', 'delete']


function useResourceOptions() {
  const nodesQ = useQuery({
    queryKey: ['nodes-options'],
    queryFn: async () => {
      const { data } = await client.get('/nodes', { params: { per_page: 500 } })
      const items = Array.isArray(data?.items) ? data.items : []
      return items.map((n: any) => ({ uuid: n.uuid, label: n.name || n.uuid })) as ResourceOption[]
    },
    staleTime: 60_000,
  })
  const hostsQ = useQuery({
    queryKey: ['hosts-options'],
    queryFn: async () => {
      const { data } = await client.get('/hosts')
      const items = Array.isArray(data?.items) ? data.items : []
      return items.map((h: any) => ({
        uuid: h.uuid,
        label: h.remark || h.address || h.uuid,
      })) as ResourceOption[]
    },
    staleTime: 60_000,
  })
  const squadsQ = useQuery({
    queryKey: ['squads-options'],
    queryFn: async () => {
      const [internal, external] = await Promise.all([
        squadsApi.listInternal().catch(() => []),
        squadsApi.listExternal().catch(() => []),
      ])
      return [
        ...internal.map((s: any) => ({ uuid: s.uuid, label: `${s.name} (internal)` })),
        ...external.map((s: any) => ({ uuid: s.uuid, label: `${s.name} (external)` })),
      ] as ResourceOption[]
    },
    staleTime: 60_000,
  })
  return {
    node: nodesQ.data || [],
    host: hostsQ.data || [],
    squad: squadsQ.data || [],
    loading: nodesQ.isLoading || hostsQ.isLoading || squadsQ.isLoading,
  }
}


export default function AccessPoliciesTab({ roles }: { roles: Role[] }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const listQ = useQuery({
    queryKey: ['access-policies'],
    queryFn: accessPoliciesApi.list,
  })

  const detailQ = useQuery({
    queryKey: ['access-policy', selectedId],
    queryFn: () => selectedId ? accessPoliciesApi.get(selectedId) : Promise.resolve(null),
    enabled: selectedId !== null,
  })

  const create = useMutation({
    mutationFn: (body: { name: string; description: string; rules: PolicyRule[] }) =>
      accessPoliciesApi.create(body),
    onSuccess: (p) => {
      toast.success(t('accessPolicies.createdOk'))
      qc.invalidateQueries({ queryKey: ['access-policies'] })
      setSelectedId(p.id)
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('accessPolicies.createFailed')),
  })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: any }) =>
      accessPoliciesApi.update(id, body),
    onSuccess: () => {
      toast.success(t('accessPolicies.savedOk'))
      qc.invalidateQueries({ queryKey: ['access-policies'] })
      qc.invalidateQueries({ queryKey: ['access-policy', selectedId] })
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail || t('accessPolicies.saveFailed')),
  })

  const remove = useMutation({
    mutationFn: (id: number) => accessPoliciesApi.remove(id),
    onSuccess: () => {
      toast.success(t('accessPolicies.deletedOk'))
      qc.invalidateQueries({ queryKey: ['access-policies'] })
      setSelectedId(null)
    },
  })

  const handleCreate = () => {
    const name = prompt(t('accessPolicies.promptName') || 'Policy name')
    if (!name) return
    create.mutate({ name: name.trim(), description: '', rules: [] })
  }

  const handleDelete = () => {
    if (!selectedId) return
    if (!confirm(t('accessPolicies.confirmDelete') || 'Delete this policy?')) return
    remove.mutate(selectedId)
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
      {/* Left: list */}
      <div className="md:col-span-1 space-y-2">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold">{t('accessPolicies.listTitle')}</h3>
          <Button size="sm" variant="outline" onClick={handleCreate}>
            <Plus className="w-4 h-4 mr-1" /> {t('accessPolicies.create')}
          </Button>
        </div>
        {listQ.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (listQ.data?.length ?? 0) === 0 ? (
          <Card className="glass-card">
            <CardContent className="p-4 text-sm text-muted-foreground text-center">
              {t('accessPolicies.empty')}
            </CardContent>
          </Card>
        ) : (
          listQ.data!.map((p) => (
            <Card
              key={p.id}
              className={`glass-card cursor-pointer transition ${
                selectedId === p.id ? 'ring-2 ring-primary-500' : ''
              }`}
              onClick={() => setSelectedId(p.id)}
            >
              <CardContent className="p-3">
                <div className="flex items-center gap-2 mb-1">
                  <Shield className="w-4 h-4 text-primary-400" />
                  <span className="font-medium text-sm truncate">{p.name}</span>
                </div>
                {p.description && (
                  <p className="text-xs text-muted-foreground truncate mb-1">{p.description}</p>
                )}
                <div className="flex gap-1 flex-wrap text-[10px]">
                  <Badge variant="outline">{p.rules_count} rules</Badge>
                  <Badge variant="outline">{p.roles_count} roles</Badge>
                  <Badge variant="outline">{p.admins_count} admins</Badge>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Right: editor */}
      <div className="md:col-span-2">
        {!selectedId ? (
          <Card className="glass-card">
            <CardContent className="p-8 text-center text-muted-foreground">
              {t('accessPolicies.selectHint')}
            </CardContent>
          </Card>
        ) : detailQ.isLoading || !detailQ.data ? (
          <Skeleton className="h-96 w-full" />
        ) : (
          <PolicyEditor
            policy={detailQ.data}
            roles={roles}
            onSave={(body) => update.mutate({ id: detailQ.data!.id, body })}
            onDelete={handleDelete}
            saving={update.isPending}
          />
        )}
      </div>
    </div>
  )
}


function PolicyEditor({
  policy,
  roles,
  onSave,
  onDelete,
  saving,
}: {
  policy: PolicyDetail
  roles: Role[]
  onSave: (body: any) => void
  onDelete: () => void
  saving: boolean
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(policy.name)
  const [description, setDescription] = useState(policy.description || '')
  const [rules, setRules] = useState<PolicyRule[]>(policy.rules)
  const [selectedRoles, setSelectedRoles] = useState<Set<number>>(new Set(policy.role_ids))

  useEffect(() => {
    setName(policy.name)
    setDescription(policy.description || '')
    setRules(policy.rules)
    setSelectedRoles(new Set(policy.role_ids))
  }, [policy.id])

  const options = useResourceOptions()

  const addRule = () => {
    setRules([...rules, {
      resource_type: 'node', scope_type: 'uuid', scope_value: '', actions: ['view'],
    }])
  }

  const updateRule = (i: number, patch: Partial<PolicyRule>) => {
    setRules(rules.map((r, idx) => idx === i ? { ...r, ...patch } : r))
  }

  const removeRule = (i: number) => {
    setRules(rules.filter((_, idx) => idx !== i))
  }

  const toggleRole = (id: number) => {
    const next = new Set(selectedRoles)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedRoles(next)
  }

  const handleSave = async () => {
    for (const r of rules) {
      if (!r.scope_value.trim()) {
        toast.error(t('accessPolicies.errNoScopeValue'))
        return
      }
      if (r.actions.length === 0) {
        toast.error(t('accessPolicies.errNoAction'))
        return
      }
    }

    // Save policy itself (name/description/rules)
    onSave({ name: name.trim(), description, rules })

    // Sync role attachments: update each role that was added or removed
    const originalRoles = new Set(policy.role_ids)
    const changedRoles = new Set<number>()
    for (const rid of selectedRoles) if (!originalRoles.has(rid)) changedRoles.add(rid)
    for (const rid of originalRoles) if (!selectedRoles.has(rid)) changedRoles.add(rid)
    if (changedRoles.size === 0) return

    try {
      const attachments = await getRolePoliciesMap()
      for (const rid of changedRoles) {
        const current = new Set(attachments[rid] || [])
        if (selectedRoles.has(rid)) current.add(policy.id)
        else current.delete(policy.id)
        await accessPoliciesApi.attachToRole(rid, [...current])
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || t('accessPolicies.roleAttachFailed'))
    }
  }

  return (
    <Card className="glass-card">
      <CardContent className="p-4 space-y-4">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-primary-400" />
          <h3 className="text-base font-semibold">{t('accessPolicies.editorTitle')}</h3>
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="destructive" onClick={onDelete}>
              <Trash2 className="w-4 h-4 mr-1" /> {t('common.delete')}
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              <Save className="w-4 h-4 mr-1" /> {t('common.save')}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <Label>{t('accessPolicies.name')}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <Label>{t('accessPolicies.description')}</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>

        {/* Rules */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <Label>{t('accessPolicies.rules')}</Label>
            <Button size="sm" variant="outline" onClick={addRule}>
              <Plus className="w-4 h-4 mr-1" /> {t('accessPolicies.addRule')}
            </Button>
          </div>
          <div className="space-y-2">
            {rules.length === 0 && (
              <p className="text-xs text-muted-foreground italic">
                {t('accessPolicies.noRules')}
              </p>
            )}
            {rules.map((rule, i) => {
              const resOptions = options[rule.resource_type] || []
              return (
                <div key={i} className="grid grid-cols-12 gap-2 items-start p-2 rounded-lg border border-white/5 bg-white/[0.02]">
                  <div className="col-span-12 md:col-span-2">
                    <Label className="text-[10px]">{t('accessPolicies.resourceType')}</Label>
                    <Select
                      value={rule.resource_type}
                      onValueChange={(v) => updateRule(i, { resource_type: v as ResourceType, scope_value: '' })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {RESOURCE_TYPES.map(rt => (
                          <SelectItem key={rt} value={rt}>{t(`accessPolicies.resource.${rt}`)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-12 md:col-span-2">
                    <Label className="text-[10px]">{t('accessPolicies.scopeType')}</Label>
                    <Select
                      value={rule.scope_type}
                      onValueChange={(v) => updateRule(i, { scope_type: v as ScopeType, scope_value: '' })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {SCOPE_TYPES.map(st => (
                          <SelectItem key={st} value={st}>{t(`accessPolicies.scope.${st}`)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-12 md:col-span-4">
                    <Label className="text-[10px]">{t('accessPolicies.scopeValue')}</Label>
                    {rule.scope_type === 'uuid' ? (
                      <Select
                        value={rule.scope_value}
                        onValueChange={(v) => updateRule(i, { scope_value: v })}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder={t('accessPolicies.pickResource') || 'Pick...'} />
                        </SelectTrigger>
                        <SelectContent>
                          {resOptions.map((o) => (
                            <SelectItem key={o.uuid} value={o.uuid}>{o.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input
                        placeholder="tag name"
                        value={rule.scope_value}
                        onChange={(e) => updateRule(i, { scope_value: e.target.value })}
                      />
                    )}
                  </div>
                  <div className="col-span-10 md:col-span-3">
                    <Label className="text-[10px]">{t('accessPolicies.actions')}</Label>
                    <div className="flex gap-3 items-center pt-2">
                      {ALL_ACTIONS.map((a) => (
                        <label key={a} className="flex items-center gap-1 text-xs">
                          <Checkbox
                            checked={rule.actions.includes(a)}
                            onCheckedChange={(ch) => {
                              const set = new Set(rule.actions)
                              if (ch) set.add(a); else set.delete(a)
                              updateRule(i, { actions: [...set] as PolicyAction[] })
                            }}
                          />
                          {t(`accessPolicies.action.${a}`)}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="col-span-2 md:col-span-1 pt-5">
                    <Button size="sm" variant="ghost" onClick={() => removeRule(i)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Role attachments */}
        <div>
          <Label className="mb-2 block flex items-center gap-1">
            <Users className="w-4 h-4" /> {t('accessPolicies.attachedRoles')}
          </Label>
          <div className="flex flex-wrap gap-2">
            {roles.map((r) => (
              <Badge
                key={r.id}
                variant={selectedRoles.has(r.id) ? 'default' : 'outline'}
                className="cursor-pointer"
                onClick={() => toggleRole(r.id)}
              >
                {r.display_name || r.name}
              </Badge>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {t('accessPolicies.roleHint')}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}


async function getRolePoliciesMap(): Promise<Record<number, number[]>> {
  // Build {role_id -> [policy_id,...]} by walking all policies.
  // Backend has no bulk endpoint for this, but it's fine for a handful of policies.
  const all = await accessPoliciesApi.list()
  const map: Record<number, number[]> = {}
  for (const p of all) {
    try {
      const detail = await accessPoliciesApi.get(p.id)
      for (const rid of detail.role_ids) {
        if (!map[rid]) map[rid] = []
        map[rid].push(detail.id)
      }
    } catch { /* skip */ }
  }
  return map
}
