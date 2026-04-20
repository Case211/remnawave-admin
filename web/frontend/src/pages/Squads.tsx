import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Plus, Trash2, UsersRound, Globe, Hash, Pencil } from 'lucide-react'
import { squadsApi, type InternalSquad, type ExternalSquad } from '@/api/squads'
import { usePermissionStore } from '@/store/permissionStore'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { QueryError } from '@/components/QueryError'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useTabParam } from '@/lib/useTabParam'

const VALID_TABS = ['internal', 'external'] as const

function InternalSquadsTab() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const canCreate = hasPermission('users', 'create')
  const canEdit = hasPermission('users', 'edit')
  const canDelete = hasPermission('users', 'delete')

  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newInbounds, setNewInbounds] = useState<string[]>([])
  const [deleteUuid, setDeleteUuid] = useState<string | null>(null)
  const [editSquad, setEditSquad] = useState<InternalSquad | null>(null)
  const [editName, setEditName] = useState('')
  const [editInbounds, setEditInbounds] = useState<string[]>([])

  const { data: squads = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['squads-internal'],
    queryFn: squadsApi.listInternal,
  })

  const { data: allInbounds = [] } = useQuery({
    queryKey: ['squads-inbounds'],
    queryFn: squadsApi.listInbounds,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['squads-internal'] })
    qc.invalidateQueries({ queryKey: ['internal-squads'] })
  }

  const createMut = useMutation({
    mutationFn: () => squadsApi.createInternal(newName.trim(), newInbounds),
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      setNewName('')
      setNewInbounds([])
      toast.success(t('squads.created'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateMut = useMutation({
    mutationFn: () => squadsApi.updateInternal(editSquad!.uuid, { name: editName.trim(), inbounds: editInbounds }),
    onSuccess: () => {
      invalidate()
      setEditSquad(null)
      toast.success(t('squads.updated', { defaultValue: 'Squad updated' }))
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMut = useMutation({
    mutationFn: (uuid: string) => squadsApi.deleteInternal(uuid),
    onSuccess: () => {
      invalidate()
      setDeleteUuid(null)
      toast.success(t('squads.deleted'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const openEdit = (sq: InternalSquad) => {
    setEditSquad(sq)
    setEditName(sq.name)
    setEditInbounds(sq.inbounds?.map((ib) => ib.uuid) || [])
  }

  const toggleInbound = (uuid: string, list: string[], setList: (v: string[]) => void) => {
    setList(list.includes(uuid) ? list.filter((id) => id !== uuid) : [...list, uuid])
  }

  if (isLoading) return <Skeleton className="h-64 w-full" />
  if (isError) return <QueryError onRetry={refetch} />

  return (
    <div className="space-y-4">
      {canCreate && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5">
            <Plus className="w-4 h-4" />
            {t('squads.createInternal')}
          </Button>
        </div>
      )}

      {!squads.length ? (
        <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
          {t('squads.noInternal')}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {squads.map((sq) => {
            const scopeAllowsEdit = sq.allowed_actions == null || sq.allowed_actions.includes('edit')
            const scopeAllowsDelete = sq.allowed_actions == null || sq.allowed_actions.includes('delete')
            const effectiveCanEdit = canEdit && scopeAllowsEdit
            const effectiveCanDelete = canDelete && scopeAllowsDelete
            return (
            <Card key={sq.uuid} className="animate-fade-in-up">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <UsersRound className="w-4 h-4 text-primary-400 shrink-0" />
                    <span className="font-medium text-white truncate">{sq.name}</span>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {effectiveCanEdit && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-primary-400"
                        onClick={() => openEdit(sq)}
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                    )}
                    {effectiveCanDelete && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-red-400"
                        onClick={() => setDeleteUuid(sq.uuid)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
                <div className="flex gap-3 mt-2 text-xs text-muted-foreground">
                  {sq.info && (
                    <>
                      <span className="flex items-center gap-1">
                        <UsersRound className="w-3 h-3" />
                        {sq.info.membersCount}
                      </span>
                      <span className="flex items-center gap-1">
                        <Hash className="w-3 h-3" />
                        {sq.info.inboundsCount} inbounds
                      </span>
                    </>
                  )}
                </div>
                {sq.inbounds && sq.inbounds.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {sq.inbounds.map((ib) => (
                      <Badge key={ib.uuid} variant="outline" className="text-[10px]">
                        {ib.tag}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )})}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) { setNewName(''); setNewInbounds([]) } }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('squads.createInternal')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              placeholder={t('squads.name')}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              maxLength={30}
            />
            {allInbounds.length > 0 && (
              <div>
                <Label className="text-sm text-muted-foreground mb-2 block">
                  Inbounds
                </Label>
                <div className="max-h-48 overflow-y-auto space-y-1.5">
                  {allInbounds.map((ib) => (
                    <label
                      key={ib.uuid}
                      className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[var(--glass-bg)] cursor-pointer"
                    >
                      <Checkbox
                        checked={newInbounds.includes(ib.uuid)}
                        onCheckedChange={() => toggleInbound(ib.uuid, newInbounds, setNewInbounds)}
                      />
                      <span className="text-sm text-white">{ib.tag}</span>
                      <span className="text-[10px] text-muted-foreground ml-auto">{ib.type}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
            <Button
              onClick={() => createMut.mutate()}
              disabled={!newName.trim() || createMut.isPending}
            >
              {t('common.create', { defaultValue: 'Create' })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editSquad} onOpenChange={(open) => !open && setEditSquad(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('squads.editInternal', { defaultValue: 'Edit Internal Squad' })}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              placeholder={t('squads.name')}
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              maxLength={30}
            />
            {allInbounds.length > 0 && (
              <div>
                <Label className="text-sm text-muted-foreground mb-2 block">
                  Inbounds
                </Label>
                <div className="max-h-48 overflow-y-auto space-y-1.5">
                  {allInbounds.map((ib) => (
                    <label
                      key={ib.uuid}
                      className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[var(--glass-bg)] cursor-pointer"
                    >
                      <Checkbox
                        checked={editInbounds.includes(ib.uuid)}
                        onCheckedChange={() => toggleInbound(ib.uuid, editInbounds, setEditInbounds)}
                      />
                      <span className="text-sm text-white">{ib.tag}</span>
                      <span className="text-[10px] text-muted-foreground ml-auto">{ib.type}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditSquad(null)}>{t('common.cancel')}</Button>
            <Button
              onClick={() => updateMut.mutate()}
              disabled={!editName.trim() || updateMut.isPending}
            >
              {t('common.save', { defaultValue: 'Save' })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteUuid}
        onOpenChange={(open) => !open && setDeleteUuid(null)}
        onConfirm={() => deleteUuid && deleteMut.mutate(deleteUuid)}
        title={t('squads.deleteConfirm')}
        description={t('squads.deleteDescription')}
        variant="destructive"
      />
    </div>
  )
}

function ExternalSquadsTab() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const canCreate = hasPermission('users', 'create')
  const canEdit = hasPermission('users', 'edit')
  const canDelete = hasPermission('users', 'delete')

  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [deleteUuid, setDeleteUuid] = useState<string | null>(null)
  const [editSquad, setEditSquad] = useState<ExternalSquad | null>(null)
  const [editName, setEditName] = useState('')

  const { data: squads = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['squads-external'],
    queryFn: squadsApi.listExternal,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['squads-external'] })
    qc.invalidateQueries({ queryKey: ['external-squads'] })
  }

  const createMut = useMutation({
    mutationFn: () => squadsApi.createExternal(newName.trim()),
    onSuccess: () => {
      invalidate()
      setCreateOpen(false)
      setNewName('')
      toast.success(t('squads.created'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateMut = useMutation({
    mutationFn: () => squadsApi.updateExternal(editSquad!.uuid, { name: editName.trim() }),
    onSuccess: () => {
      invalidate()
      setEditSquad(null)
      toast.success(t('squads.updated', { defaultValue: 'Squad updated' }))
    },
    onError: () => toast.error(t('common.error')),
  })

  const deleteMut = useMutation({
    mutationFn: (uuid: string) => squadsApi.deleteExternal(uuid),
    onSuccess: () => {
      invalidate()
      setDeleteUuid(null)
      toast.success(t('squads.deleted'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const openEdit = (sq: ExternalSquad) => {
    setEditSquad(sq)
    setEditName(sq.name)
  }

  if (isLoading) return <Skeleton className="h-64 w-full" />
  if (isError) return <QueryError onRetry={refetch} />

  return (
    <div className="space-y-4">
      {canCreate && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5">
            <Plus className="w-4 h-4" />
            {t('squads.createExternal')}
          </Button>
        </div>
      )}

      {!squads.length ? (
        <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
          {t('squads.noExternal')}
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {squads.map((sq) => {
            const scopeAllowsEdit = sq.allowed_actions == null || sq.allowed_actions.includes('edit')
            const scopeAllowsDelete = sq.allowed_actions == null || sq.allowed_actions.includes('delete')
            const effectiveCanEdit = canEdit && scopeAllowsEdit
            const effectiveCanDelete = canDelete && scopeAllowsDelete
            return (
            <Card key={sq.uuid} className="animate-fade-in-up">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <Globe className="w-4 h-4 text-cyan-400 shrink-0" />
                    <span className="font-medium text-white truncate">{sq.name}</span>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {effectiveCanEdit && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-primary-400"
                        onClick={() => openEdit(sq)}
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                    )}
                    {effectiveCanDelete && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-red-400"
                        onClick={() => setDeleteUuid(sq.uuid)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
                {sq.info && (
                  <div className="flex gap-3 mt-2 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <UsersRound className="w-3 h-3" />
                      {sq.info.membersCount} {t('squads.members')}
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          )})}
        </div>
      )}

      {/* Create dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('squads.createExternal')}</DialogTitle>
          </DialogHeader>
          <Input
            placeholder={t('squads.name')}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={30}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
            <Button
              onClick={() => createMut.mutate()}
              disabled={!newName.trim() || createMut.isPending}
            >
              {t('common.create', { defaultValue: 'Create' })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog */}
      <Dialog open={!!editSquad} onOpenChange={(open) => !open && setEditSquad(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('squads.editExternal', { defaultValue: 'Edit External Squad' })}</DialogTitle>
          </DialogHeader>
          <Input
            placeholder={t('squads.name')}
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            maxLength={30}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditSquad(null)}>{t('common.cancel')}</Button>
            <Button
              onClick={() => updateMut.mutate()}
              disabled={!editName.trim() || updateMut.isPending}
            >
              {t('common.save', { defaultValue: 'Save' })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteUuid}
        onOpenChange={(open) => !open && setDeleteUuid(null)}
        onConfirm={() => deleteUuid && deleteMut.mutate(deleteUuid)}
        title={t('squads.deleteConfirm')}
        description={t('squads.deleteDescription')}
        variant="destructive"
      />
    </div>
  )
}

export default function Squads() {
  const { t } = useTranslation()
  const hasPermission = usePermissionStore((s) => s.hasPermission)
  const [tab, setTab] = useTabParam('internal', [...VALID_TABS])

  if (!hasPermission('users', 'view')) {
    return (
      <div className="p-4 md:p-6 flex items-center justify-center min-h-[400px]">
        <p className="text-muted-foreground">{t('common.noPermission', { defaultValue: 'No permission' })}</p>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white">{t('squads.title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t('squads.subtitle')}
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList>
          <TabsTrigger value="internal" className="gap-1.5">
            <UsersRound className="w-4 h-4" />
            {t('squads.internal')}
          </TabsTrigger>
          <TabsTrigger value="external" className="gap-1.5">
            <Globe className="w-4 h-4" />
            {t('squads.external')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="internal">
          <InternalSquadsTab />
        </TabsContent>

        <TabsContent value="external">
          <ExternalSquadsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
