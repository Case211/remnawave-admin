import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTabParam } from '@/lib/useTabParam'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Plus,
  Trash2,
  Code,
  Settings,
  RefreshCw,
  FileJson,
  UsersRound,
  Globe,
} from '@/components/brand/icons'
import { resourcesApi, Template, Snippet, ConfigProfile } from '../api/resources'
import { ProfileEditorDialog } from '@/components/code/ProfileEditorDialog'
import { TemplateEditorDialog } from '@/components/code/TemplateEditorDialog'
import { CodeEditor } from '@/components/code/CodeEditor'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { QueryError } from '@/components/QueryError'
import { useHasPermission } from '@/components/PermissionGate'
import { cn } from '@/lib/utils'
import { useFormatters } from '@/lib/useFormatters'
import { SquadsPanel } from '@/components/squads/SquadsPanel'
import { HostsPanel } from '@/components/hosts/HostsPanel'

type ResourcesTab = 'hosts' | 'templates' | 'snippets' | 'profiles' | 'squads'

// Вкладки конфигурации — их данные грузит сама страница
const CONFIG_TABS: ResourcesTab[] = ['templates', 'snippets', 'profiles']

// Template type options
const TEMPLATE_TYPES = [
  'XRAY_JSON',
  'XRAY_BASE64',
  'MIHOMO',
  'STASH',
  'CLASH',
  'SINGBOX',
] as const

// Template type badge colors
const TEMPLATE_TYPE_COLORS: Record<string, string> = {
  XRAY_JSON: 'bg-blue-500/15 text-blue-400 border-blue-500/20',
  XRAY_BASE64: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/20',
  MIHOMO: 'bg-purple-500/15 text-purple-400 border-purple-500/20',
  STASH: 'bg-pink-500/15 text-pink-400 border-pink-500/20',
  CLASH: 'bg-red-500/15 text-red-400 border-red-500/20',
  SINGBOX: 'bg-orange-500/15 text-orange-400 border-orange-500/20',
}

export default function Resources() {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()

  // Permissions: у каждой вкладки своё право, как у бывших отдельных страниц
  const canViewHosts = useHasPermission('hosts', 'view')
  const canViewConfig = useHasPermission('resources', 'view')
  const canViewSquads = useHasPermission('users', 'view')
  const canCreate = useHasPermission('resources', 'create')
  const canUpdate = useHasPermission('resources', 'edit')
  const canDelete = useHasPermission('resources', 'delete')

  // Tab state — управление API-токенами панели убрано (только в самой Remnawave)
  const tabs: ResourcesTab[] = [
    ...(canViewHosts ? (['hosts'] as const) : []),
    ...(canViewConfig ? (['templates', 'snippets', 'profiles'] as const) : []),
    ...(canViewSquads ? (['squads'] as const) : []),
  ]
  const [activeTab, setActiveTab] = useTabParam<ResourcesTab>(tabs[0] ?? 'templates', tabs)

  // ── Templates ───────────────────────────────────────────────────
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false)
  const [templateFormData, setTemplateFormData] = useState({ name: '', templateType: 'XRAY_JSON' })
  // редактирование шаблона — вынесено во встроенный редактор (секции/дифф/история)
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null)
  const [deleteTemplateConfirm, setDeleteTemplateConfirm] = useState<string | null>(null)

  const { data: templates = [], isLoading: templatesLoading, isError: isTemplatesError, refetch: refetchTemplates } = useQuery({
    queryKey: ['templates'],
    queryFn: resourcesApi.getTemplates,
    enabled: canViewConfig,
  })

  const createTemplateMutation = useMutation({
    mutationFn: (data: { name: string; templateType: string }) =>
      resourcesApi.createTemplate(data.name, data.templateType),
    onSuccess: () => {
      setTemplateDialogOpen(false)
      setTemplateFormData({ name: '', templateType: 'XRAY_JSON' })
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      toast.success(t('resources.templates.created'))
    },
    onError: () => {
      toast.error(t('resources.templates.createError'))
    },
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: (uuid: string) => resourcesApi.deleteTemplate(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      toast.success(t('resources.templates.deleted'))
      setDeleteTemplateConfirm(null)
    },
    onError: () => {
      toast.error(t('resources.templates.deleteError'))
    },
  })

  // ── Snippets ────────────────────────────────────────────────────
  const [snippetDialogOpen, setSnippetDialogOpen] = useState(false)
  const [editSnippetDialogOpen, setEditSnippetDialogOpen] = useState(false)
  const [snippetFormData, setSnippetFormData] = useState({ name: '', snippet: '' })
  const [editingSnippet, setEditingSnippet] = useState<Snippet | null>(null)
  const [editSnippetForm, setEditSnippetForm] = useState({ name: '', snippet: '' })
  const [deleteSnippetConfirm, setDeleteSnippetConfirm] = useState<string | null>(null)

  const { data: snippets = [], isLoading: snippetsLoading, isError: isSnippetsError, refetch: refetchSnippets } = useQuery({
    queryKey: ['snippets'],
    queryFn: resourcesApi.getSnippets,
    enabled: canViewConfig,
  })

  const createSnippetMutation = useMutation({
    mutationFn: (data: { name: string; snippet: unknown }) =>
      resourcesApi.createSnippet(data.name, data.snippet),
    onSuccess: () => {
      setSnippetDialogOpen(false)
      setSnippetFormData({ name: '', snippet: '' })
      queryClient.invalidateQueries({ queryKey: ['snippets'] })
      toast.success(t('resources.snippets.created'))
    },
    onError: () => {
      toast.error(t('resources.snippets.createError'))
    },
  })

  const updateSnippetMutation = useMutation({
    mutationFn: (data: { name: string; snippet: unknown }) =>
      resourcesApi.updateSnippet(data.name, data.snippet),
    onSuccess: () => {
      setEditSnippetDialogOpen(false)
      setEditingSnippet(null)
      queryClient.invalidateQueries({ queryKey: ['snippets'] })
      toast.success(t('resources.snippets.updated'))
    },
    onError: () => {
      toast.error(t('resources.snippets.updateError'))
    },
  })

  const deleteSnippetMutation = useMutation({
    mutationFn: (name: string) => resourcesApi.deleteSnippet(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['snippets'] })
      toast.success(t('resources.snippets.deleted'))
      setDeleteSnippetConfirm(null)
    },
    onError: () => {
      toast.error(t('resources.snippets.deleteError'))
    },
  })

  const openEditSnippet = (snippet: Snippet) => {
    setEditingSnippet(snippet)
    setEditSnippetForm({
      name: snippet.name,
      snippet: JSON.stringify(snippet.snippet, null, 2),
    })
    setEditSnippetDialogOpen(true)
  }

  const handleCreateSnippet = () => {
    try {
      const json = JSON.parse(snippetFormData.snippet)
      createSnippetMutation.mutate({ name: snippetFormData.name, snippet: json })
    } catch {
      toast.error(t('resources.snippets.invalidJson'))
    }
  }

  const handleUpdateSnippet = () => {
    if (!editingSnippet) return
    try {
      const json = JSON.parse(editSnippetForm.snippet)
      updateSnippetMutation.mutate({ name: editingSnippet.name, snippet: json })
    } catch {
      toast.error(t('resources.snippets.invalidJson'))
    }
  }

  // ── Config Profiles ─────────────────────────────────────────────
  // встроенный редактор профиля (исходник + вычисленный, история версий)
  const [editingProfile, setEditingProfile] = useState<ConfigProfile | null>(null)
  const [createProfileOpen, setCreateProfileOpen] = useState(false)
  const [newProfileName, setNewProfileName] = useState('')
  const [renameProfile, setRenameProfile] = useState<{ uuid: string; name: string } | null>(null)
  const [deleteProfileConfirm, setDeleteProfileConfirm] = useState<ConfigProfile | null>(null)

  const { data: configProfiles = [], isLoading: profilesLoading, isError: isProfilesError, refetch: refetchProfiles } = useQuery({
    queryKey: ['config-profiles'],
    queryFn: resourcesApi.getConfigProfiles,
    enabled: canViewConfig,
  })

  const createProfileMutation = useMutation({
    mutationFn: (name: string) => resourcesApi.createConfigProfile(name),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['config-profiles'] })
      setCreateProfileOpen(false)
      setNewProfileName('')
      toast.success(t('resources.profiles.created'))
      // сразу в редактор — заполнять конфиг
      if (created?.uuid) setEditingProfile(created)
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('common.error')),
  })

  const renameProfileMutation = useMutation({
    mutationFn: (p: { uuid: string; name: string }) => resourcesApi.renameConfigProfile(p.uuid, p.name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-profiles'] })
      setRenameProfile(null)
      toast.success(t('common.saved'))
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('common.saveError')),
  })

  const deleteProfileMutation = useMutation({
    mutationFn: (uuid: string) => resourcesApi.deleteConfigProfile(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-profiles'] })
      setDeleteProfileConfirm(null)
      toast.success(t('common.deleted'))
    },
    // панель откажет, если профиль привязан к нодам — показываем причину
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      toast.error(e.response?.data?.detail || t('common.error')),
  })

  const hasError = isTemplatesError || isSnippetsError || isProfilesError
  const handleRetry = () => { refetchTemplates(); refetchSnippets(); refetchProfiles() }

  if (!tabs.length) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <p className="text-muted-foreground">{t('common.noPermission')}</p>
      </div>
    )
  }

  if (hasError && CONFIG_TABS.includes(activeTab)) {
    return (
      <div className="space-y-6">
        <div className="page-header">
          <div>
            <h1 className="page-header-title">{t('resources.title')}</h1>
            <p className="text-dark-200 mt-1">{t('resources.subtitle')}</p>
          </div>
        </div>
        <QueryError onRetry={handleRetry} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="page-header">
        <div>
          <h1 className="page-header-title">{t('resources.title')}</h1>
          <p className="text-dark-200 mt-1">{t('resources.subtitle')}</p>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          {canViewHosts && (
            <TabsTrigger value="hosts">
              <Globe className="w-4 h-4 mr-2" />
              {t('resources.tabs.hosts')}
            </TabsTrigger>
          )}
          {canViewConfig && (
            <>
              <TabsTrigger value="templates">
                <Code className="w-4 h-4 mr-2" />
                {t('resources.tabs.templates')}
              </TabsTrigger>
              <TabsTrigger value="snippets">
                <Code className="w-4 h-4 mr-2" />
                {t('resources.tabs.snippets')}
              </TabsTrigger>
              <TabsTrigger value="profiles">
                <Settings className="w-4 h-4 mr-2" />
                {t('resources.tabs.profiles')}
              </TabsTrigger>
            </>
          )}
          {canViewSquads && (
            <TabsTrigger value="squads">
              <UsersRound className="w-4 h-4 mr-2" />
              {t('resources.tabs.squads')}
            </TabsTrigger>
          )}
        </TabsList>

        {/* ── Tab 2: Templates ─────────────────────────────────── */}
        <TabsContent value="templates" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('resources.templates.description')}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchTemplates()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => setTemplateDialogOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  {t('resources.templates.create')}
                </Button>
              )}
            </div>
          </div>

          {templatesLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : !Array.isArray(templates) || templates.length === 0 ? (
            <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
              <CardContent className="p-8 text-center">
                <Code className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('resources.templates.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(Array.isArray(templates) ? templates : []).map((template) => (
                <Card
                  key={template.uuid}
                  className="border-[var(--glass-border)] bg-[var(--glass-bg)] hover:border-[var(--glass-border)] transition-colors cursor-pointer"
                  onClick={() => canUpdate && setEditingTemplate(template)}
                >
                  <CardContent className="p-4">
                    <div className="space-y-3">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="font-medium text-white truncate flex-1">{template.name}</h3>
                        {canDelete && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteTemplateConfirm(template.uuid)
                            }}
                            className="text-red-400 hover:text-red-300 hover:bg-red-500/10 h-7 px-2"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                      <Badge
                        className={cn(
                          'text-xs',
                          TEMPLATE_TYPE_COLORS[template.templateType] || 'bg-gray-500/15 text-gray-400'
                        )}
                      >
                        {template.templateType}
                      </Badge>
                      <div className="text-xs text-dark-300 space-y-1">
                        <div>{t('resources.position')} {template.viewPosition}</div>
                        <div>{formatDate(template.updatedAt)}</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Tab 3: Snippets ──────────────────────────────────── */}
        <TabsContent value="snippets" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('resources.snippets.description')}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchSnippets()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => setSnippetDialogOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  {t('resources.snippets.create')}
                </Button>
              )}
            </div>
          </div>

          {snippetsLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : !Array.isArray(snippets) || snippets.length === 0 ? (
            <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
              <CardContent className="p-8 text-center">
                <Code className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('resources.snippets.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {(Array.isArray(snippets) ? snippets : []).map((snippet) => (
                <Card
                  key={snippet.name}
                  className="border-[var(--glass-border)] bg-[var(--glass-bg)] hover:border-[var(--glass-border)] transition-colors cursor-pointer"
                  onClick={() => canUpdate && openEditSnippet(snippet)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center gap-3">
                          <h3 className="font-medium text-white">{snippet.name}</h3>
                          <Badge variant="outline" className="text-xs">
                            {formatDate(snippet.updatedAt)}
                          </Badge>
                        </div>
                        <pre className="text-xs text-dark-300 bg-[var(--glass-bg)] p-2 rounded overflow-x-auto max-h-20">
                          {JSON.stringify(snippet.snippet, null, 2).slice(0, 200)}
                          {JSON.stringify(snippet.snippet).length > 200 ? '...' : ''}
                        </pre>
                      </div>
                      {canDelete && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteSnippetConfirm(snippet.name)
                          }}
                          className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Tab 4: Config Profiles ───────────────────────────── */}
        <TabsContent value="profiles" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('resources.profiles.description')}</p>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchProfiles()} aria-label={t('common.refresh')}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" className="gap-1.5" onClick={() => setCreateProfileOpen(true)}>
                  <Plus className="w-4 h-4" /> {t('resources.profiles.create')}
                </Button>
              )}
            </div>
          </div>

          {profilesLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : !Array.isArray(configProfiles) || configProfiles.length === 0 ? (
            <Card className="border-[var(--glass-border)] bg-[var(--glass-bg)]">
              <CardContent className="p-8 text-center">
                <Settings className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('resources.profiles.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(Array.isArray(configProfiles) ? configProfiles : []).map((profile) => (
                <Card
                  key={profile.uuid}
                  className="border-[var(--glass-border)] bg-[var(--glass-bg)] hover:border-[var(--glass-border)] transition-colors cursor-pointer"
                  onClick={() => setEditingProfile(profile)}
                >
                  <CardContent className="p-4">
                    <div className="space-y-3">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="font-medium text-white">{profile.name}</h3>
                        <div className="flex items-center shrink-0" onClick={(e) => e.stopPropagation()}>
                          <Button
                            variant="ghost" size="sm"
                            className="h-7 px-2 text-xs text-dark-200 hover:text-white"
                            title={t('resources.profiles.openInEditor')}
                            onClick={() => setEditingProfile(profile)}
                          >
                            <FileJson className="w-3.5 h-3.5 mr-1" />
                            {t('resources.profiles.openInEditor')}
                          </Button>
                          {canUpdate && (
                            <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-dark-200 hover:text-white"
                              title={t('resources.profiles.rename')} aria-label={t('resources.profiles.rename')}
                              onClick={() => setRenameProfile({ uuid: profile.uuid, name: profile.name })}>
                              <Settings className="w-3.5 h-3.5" />
                            </Button>
                          )}
                          {canDelete && (
                            <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-400 hover:text-red-300"
                              title={t('common.delete')} aria-label={t('common.delete')}
                              onClick={() => setDeleteProfileConfirm(profile)}>
                              <Trash2 className="w-3.5 h-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>
                      <div className="text-xs text-dark-300 space-y-1">
                        <div>{t('resources.uuid')} {profile.uuid.slice(0, 8)}...</div>
                        <div>{t('resources.position')} {profile.viewPosition}</div>
                        <div>{formatDate(profile.updatedAt)}</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {canViewHosts && (
          <TabsContent value="hosts">
            <HostsPanel />
          </TabsContent>
        )}

        {canViewSquads && (
          <TabsContent value="squads" className="space-y-4">
            <SquadsPanel />
          </TabsContent>
        )}
      </Tabs>

      {/* ── Dialogs ────────────────────────────────────────────── */}

      {/* Встроенный редактор профиля xray */}
      <ProfileEditorDialog profile={editingProfile} onClose={() => setEditingProfile(null)} />

      {/* Встроенный редактор шаблона (секции/дифф/история) */}
      <TemplateEditorDialog template={editingTemplate} onClose={() => setEditingTemplate(null)} />

      {/* Создание профиля */}
      <Dialog open={createProfileOpen} onOpenChange={setCreateProfileOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('resources.profiles.createTitle')}</DialogTitle>
            <DialogDescription>{t('resources.profiles.createDescription')}</DialogDescription>
          </DialogHeader>
          <div>
            <Label htmlFor="newProfileName">{t('resources.profiles.nameLabel')}</Label>
            <Input id="newProfileName" value={newProfileName} className="mt-1"
              placeholder="Germany-Reality" maxLength={30}
              onChange={(e) => setNewProfileName(e.target.value)} />
            <p className="text-[11px] text-dark-300 mt-1">{t('resources.profiles.nameHint')}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateProfileOpen(false)}>{t('common.cancel')}</Button>
            <Button
              disabled={newProfileName.trim().length < 2 || !/^[A-Za-z0-9_\s-]+$/.test(newProfileName.trim()) || createProfileMutation.isPending}
              onClick={() => createProfileMutation.mutate(newProfileName.trim())}>
              {createProfileMutation.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Переименование профиля */}
      <Dialog open={renameProfile !== null} onOpenChange={(o) => !o && setRenameProfile(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('resources.profiles.renameTitle')}</DialogTitle>
          </DialogHeader>
          <div>
            <Label htmlFor="renameProfileName">{t('resources.profiles.nameLabel')}</Label>
            <Input id="renameProfileName" value={renameProfile?.name || ''} className="mt-1" maxLength={30}
              onChange={(e) => renameProfile && setRenameProfile({ ...renameProfile, name: e.target.value })} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameProfile(null)}>{t('common.cancel')}</Button>
            <Button
              disabled={!renameProfile || renameProfile.name.trim().length < 2 || !/^[A-Za-z0-9_\s-]+$/.test(renameProfile.name.trim()) || renameProfileMutation.isPending}
              onClick={() => renameProfile && renameProfileMutation.mutate({ uuid: renameProfile.uuid, name: renameProfile.name.trim() })}>
              {renameProfileMutation.isPending ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Удаление профиля */}
      <ConfirmDialog
        open={deleteProfileConfirm !== null}
        onOpenChange={(open) => !open && setDeleteProfileConfirm(null)}
        title={t('resources.profiles.deleteTitle', { name: deleteProfileConfirm?.name })}
        description={t('resources.profiles.deleteDescription')}
        variant="destructive"
        onConfirm={() => deleteProfileConfirm && deleteProfileMutation.mutate(deleteProfileConfirm.uuid)}
      />

      {/* Create Template Dialog */}
      <Dialog open={templateDialogOpen} onOpenChange={setTemplateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('resources.templates.createTitle')}</DialogTitle>
            <DialogDescription>{t('resources.templates.createDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="templateName">{t('resources.templates.nameLabel')}</Label>
              <Input
                id="templateName"
                value={templateFormData.name}
                onChange={(e) => setTemplateFormData({ ...templateFormData, name: e.target.value })}
                placeholder={t('resources.templates.namePlaceholder')}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="templateType">{t('resources.templates.typeLabel')}</Label>
              <Select
                value={templateFormData.templateType}
                onValueChange={(value) => setTemplateFormData({ ...templateFormData, templateType: value })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.isArray(TEMPLATE_TYPES) && TEMPLATE_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTemplateDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => createTemplateMutation.mutate(templateFormData)}
              disabled={!templateFormData.name.trim() || createTemplateMutation.isPending}
            >
              {createTemplateMutation.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>


      {/* Delete Template Confirm */}
      <ConfirmDialog
        open={!!deleteTemplateConfirm}
        onOpenChange={(open) => !open && setDeleteTemplateConfirm(null)}
        title={t('resources.templates.deleteTitle')}
        description={t('resources.templates.deleteDescription')}
        variant="destructive"
        onConfirm={() => deleteTemplateConfirm && deleteTemplateMutation.mutate(deleteTemplateConfirm)}
      />

      {/* Create Snippet Dialog */}
      <Dialog open={snippetDialogOpen} onOpenChange={setSnippetDialogOpen}>
        <DialogContent className="w-[95vw] max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t('resources.snippets.createTitle')}</DialogTitle>
            <DialogDescription>{t('resources.snippets.createDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="snippetName">{t('resources.snippets.nameLabel')}</Label>
              <Input
                id="snippetName"
                value={snippetFormData.name}
                onChange={(e) => setSnippetFormData({ ...snippetFormData, name: e.target.value })}
                placeholder={t('resources.snippets.namePlaceholder')}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="snippetJson">{t('resources.snippets.jsonLabel')}</Label>
              <div className="mt-1 h-72">
                <CodeEditor
                  value={snippetFormData.snippet}
                  onChange={(v) => setSnippetFormData({ ...snippetFormData, snippet: v })}
                  schema="json"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSnippetDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleCreateSnippet}
              disabled={!snippetFormData.name.trim() || !snippetFormData.snippet.trim() || createSnippetMutation.isPending}
            >
              {createSnippetMutation.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Snippet Dialog */}
      <Dialog open={editSnippetDialogOpen} onOpenChange={setEditSnippetDialogOpen}>
        <DialogContent className="w-[95vw] max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t('resources.snippets.editTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="editSnippetName">{t('resources.snippets.nameLabel')}</Label>
              <Input
                id="editSnippetName"
                value={editSnippetForm.name}
                readOnly
                disabled
                className="mt-1 opacity-60"
              />
            </div>
            <div>
              <Label htmlFor="editSnippetJson">{t('resources.snippets.jsonLabel')}</Label>
              <div className="mt-1 h-72">
                <CodeEditor
                  value={editSnippetForm.snippet}
                  onChange={(v) => setEditSnippetForm({ ...editSnippetForm, snippet: v })}
                  schema="json"
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditSnippetDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleUpdateSnippet}
              disabled={!editSnippetForm.snippet.trim() || updateSnippetMutation.isPending}
            >
              {updateSnippetMutation.isPending ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Snippet Confirm */}
      <ConfirmDialog
        open={!!deleteSnippetConfirm}
        onOpenChange={(open) => !open && setDeleteSnippetConfirm(null)}
        title={t('resources.snippets.deleteTitle')}
        description={t('resources.snippets.deleteDescription')}
        variant="destructive"
        onConfirm={() => deleteSnippetConfirm && deleteSnippetMutation.mutate(deleteSnippetConfirm)}
      />

    </div>
  )
}
