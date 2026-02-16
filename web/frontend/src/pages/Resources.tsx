import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Plus,
  Trash2,
  Copy,
  Eye,
  EyeOff,
  FileText,
  Code,
  Settings,
  RefreshCw,
} from 'lucide-react'
import { resourcesApi, Template, Snippet, ConfigProfile } from '../api/resources'
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
import { useHasPermission } from '@/components/PermissionGate'
import { cn } from '@/lib/utils'
import { useFormatters } from '@/lib/useFormatters'

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

export default function Resources({ embedded }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()
  const queryClient = useQueryClient()

  // Permissions
  const canCreate = useHasPermission('resources', 'create')
  const canUpdate = useHasPermission('resources', 'update')
  const canDelete = useHasPermission('resources', 'delete')

  // Tab state
  const [activeTab, setActiveTab] = useState('tokens')

  // ── API Tokens ──────────────────────────────────────────────────
  const [tokenDialogOpen, setTokenDialogOpen] = useState(false)
  const [tokenName, setTokenName] = useState('')
  const [createdToken, setCreatedToken] = useState<{ token: string; tokenName: string } | null>(null)
  const [deleteTokenConfirm, setDeleteTokenConfirm] = useState<string | null>(null)
  const [revealedTokens, setRevealedTokens] = useState<Set<string>>(new Set())

  const { data: tokens = [], isLoading: tokensLoading, refetch: refetchTokens } = useQuery({
    queryKey: ['tokens'],
    queryFn: resourcesApi.getTokens,
  })

  const createTokenMutation = useMutation({
    mutationFn: (name: string) => resourcesApi.createToken(name),
    onSuccess: (data) => {
      setCreatedToken(data)
      setTokenDialogOpen(false)
      setTokenName('')
      queryClient.invalidateQueries({ queryKey: ['tokens'] })
      toast.success(t('resources.tokens.created'))
    },
    onError: () => {
      toast.error(t('resources.tokens.createError'))
    },
  })

  const deleteTokenMutation = useMutation({
    mutationFn: (uuid: string) => resourcesApi.deleteToken(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tokens'] })
      toast.success(t('resources.tokens.deleted'))
      setDeleteTokenConfirm(null)
    },
    onError: () => {
      toast.error(t('resources.tokens.deleteError'))
    },
  })

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success(t('common.copied'))
  }

  const toggleTokenReveal = (uuid: string) => {
    setRevealedTokens((prev) => {
      const next = new Set(prev)
      if (next.has(uuid)) {
        next.delete(uuid)
      } else {
        next.add(uuid)
      }
      return next
    })
  }

  const maskToken = (token: string) => {
    if (token.length <= 8) return '••••••••'
    return token.slice(0, 4) + '••••••••' + token.slice(-4)
  }

  // ── Templates ───────────────────────────────────────────────────
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false)
  const [editTemplateDialogOpen, setEditTemplateDialogOpen] = useState(false)
  const [templateFormData, setTemplateFormData] = useState({ name: '', templateType: 'XRAY_JSON' })
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null)
  const [editTemplateForm, setEditTemplateForm] = useState({ name: '', templateJson: '' })
  const [deleteTemplateConfirm, setDeleteTemplateConfirm] = useState<string | null>(null)

  const { data: templates = [], isLoading: templatesLoading, refetch: refetchTemplates } = useQuery({
    queryKey: ['templates'],
    queryFn: resourcesApi.getTemplates,
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

  const updateTemplateMutation = useMutation({
    mutationFn: (data: { uuid: string; name?: string; templateJson?: Record<string, unknown> }) =>
      resourcesApi.updateTemplate(data.uuid, { name: data.name, templateJson: data.templateJson }),
    onSuccess: () => {
      setEditTemplateDialogOpen(false)
      setEditingTemplate(null)
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      toast.success(t('resources.templates.updated'))
    },
    onError: () => {
      toast.error(t('resources.templates.updateError'))
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

  const openEditTemplate = (template: Template) => {
    setEditingTemplate(template)
    setEditTemplateForm({
      name: template.name,
      templateJson: JSON.stringify(template.templateJson, null, 2),
    })
    setEditTemplateDialogOpen(true)
  }

  const handleUpdateTemplate = () => {
    if (!editingTemplate) return
    try {
      const json = JSON.parse(editTemplateForm.templateJson)
      updateTemplateMutation.mutate({
        uuid: editingTemplate.uuid,
        name: editTemplateForm.name,
        templateJson: json,
      })
    } catch {
      toast.error(t('resources.templates.invalidJson'))
    }
  }

  // ── Snippets ────────────────────────────────────────────────────
  const [snippetDialogOpen, setSnippetDialogOpen] = useState(false)
  const [editSnippetDialogOpen, setEditSnippetDialogOpen] = useState(false)
  const [snippetFormData, setSnippetFormData] = useState({ name: '', snippet: '' })
  const [editingSnippet, setEditingSnippet] = useState<Snippet | null>(null)
  const [editSnippetForm, setEditSnippetForm] = useState({ name: '', snippet: '' })
  const [deleteSnippetConfirm, setDeleteSnippetConfirm] = useState<string | null>(null)

  const { data: snippets = [], isLoading: snippetsLoading, refetch: refetchSnippets } = useQuery({
    queryKey: ['snippets'],
    queryFn: resourcesApi.getSnippets,
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
  const [viewConfigDialogOpen, setViewConfigDialogOpen] = useState(false)
  const [viewingProfile, setViewingProfile] = useState<ConfigProfile | null>(null)
  const [computedConfig, setComputedConfig] = useState<unknown>(null)

  const { data: configProfiles = [], isLoading: profilesLoading, refetch: refetchProfiles } = useQuery({
    queryKey: ['config-profiles'],
    queryFn: resourcesApi.getConfigProfiles,
  })

  const viewComputedConfig = async (profile: ConfigProfile) => {
    try {
      const data = await resourcesApi.getComputedConfig(profile.uuid)
      setViewingProfile(profile)
      setComputedConfig(data)
      setViewConfigDialogOpen(true)
    } catch {
      toast.error(t('resources.profiles.loadError'))
    }
  }

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-6'}>
      {!embedded && (
        <div className="page-header">
          <div>
            <h1 className="page-header-title">{t('resources.title')}</h1>
            <p className="text-dark-200 mt-1">{t('resources.subtitle')}</p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="tokens">
            <FileText className="w-4 h-4 mr-2" />
            {t('resources.tabs.tokens')}
          </TabsTrigger>
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
        </TabsList>

        {/* ── Tab 1: API Tokens ────────────────────────────────── */}
        <TabsContent value="tokens" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('resources.tokens.description')}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchTokens()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => setTokenDialogOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  {t('resources.tokens.create')}
                </Button>
              )}
            </div>
          </div>

          {tokensLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : tokens.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <FileText className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('resources.tokens.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {tokens.map((token) => {
                const isRevealed = revealedTokens.has(token.uuid)
                return (
                  <Card key={token.uuid} className="border-dark-600 bg-dark-800 hover:border-dark-500 transition-colors">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 space-y-2">
                          <div className="flex items-center gap-3">
                            <h3 className="font-medium text-white">{token.tokenName}</h3>
                            <Badge variant="outline" className="text-xs">
                              {formatDate(token.createdAt)}
                            </Badge>
                          </div>
                          <div className="flex items-center gap-2">
                            <code className="px-2 py-1 bg-dark-700 rounded text-xs font-mono text-dark-100 flex-1">
                              {isRevealed ? token.token : maskToken(token.token)}
                            </code>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => toggleTokenReveal(token.uuid)}
                              className="h-7 px-2"
                            >
                              {isRevealed ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => copyToClipboard(token.token)}
                              className="h-7 px-2"
                            >
                              <Copy className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                        {canDelete && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleteTokenConfirm(token.uuid)}
                            className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </TabsContent>

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
          ) : templates.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <Code className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('resources.templates.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {templates.map((template) => (
                <Card
                  key={template.uuid}
                  className="border-dark-600 bg-dark-800 hover:border-dark-500 transition-colors cursor-pointer"
                  onClick={() => canUpdate && openEditTemplate(template)}
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
                        <div>Position: {template.viewPosition}</div>
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
          ) : snippets.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <Code className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('resources.snippets.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {snippets.map((snippet) => (
                <Card
                  key={snippet.name}
                  className="border-dark-600 bg-dark-800 hover:border-dark-500 transition-colors cursor-pointer"
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
                        <pre className="text-xs text-dark-300 bg-dark-700 p-2 rounded overflow-x-auto max-h-20">
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
            <Button variant="outline" size="sm" onClick={() => refetchProfiles()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>

          {profilesLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : configProfiles.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <Settings className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('resources.profiles.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {configProfiles.map((profile) => (
                <Card
                  key={profile.uuid}
                  className="border-dark-600 bg-dark-800 hover:border-dark-500 transition-colors cursor-pointer"
                  onClick={() => viewComputedConfig(profile)}
                >
                  <CardContent className="p-4">
                    <div className="space-y-3">
                      <h3 className="font-medium text-white">{profile.name}</h3>
                      <div className="text-xs text-dark-300 space-y-1">
                        <div>UUID: {profile.uuid.slice(0, 8)}...</div>
                        <div>Position: {profile.viewPosition}</div>
                        <div>{formatDate(profile.updatedAt)}</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* ── Dialogs ────────────────────────────────────────────── */}

      {/* Create Token Dialog */}
      <Dialog open={tokenDialogOpen} onOpenChange={setTokenDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('resources.tokens.createTitle')}</DialogTitle>
            <DialogDescription>{t('resources.tokens.createDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="tokenName">{t('resources.tokens.nameLabel')}</Label>
              <Input
                id="tokenName"
                value={tokenName}
                onChange={(e) => setTokenName(e.target.value)}
                placeholder={t('resources.tokens.namePlaceholder')}
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTokenDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => createTokenMutation.mutate(tokenName)}
              disabled={!tokenName.trim() || createTokenMutation.isPending}
            >
              {createTokenMutation.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Show Created Token Dialog */}
      <Dialog open={!!createdToken} onOpenChange={() => setCreatedToken(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('resources.tokens.tokenCreated')}</DialogTitle>
            <DialogDescription>{t('resources.tokens.tokenCreatedDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('resources.tokens.nameLabel')}</Label>
              <Input value={createdToken?.tokenName || ''} readOnly className="mt-1" />
            </div>
            <div>
              <Label>{t('resources.tokens.tokenLabel')}</Label>
              <div className="flex gap-2 mt-1">
                <Input value={createdToken?.token || ''} readOnly className="font-mono" />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => createdToken && copyToClipboard(createdToken.token)}
                >
                  <Copy className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setCreatedToken(null)}>{t('common.close')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Token Confirm */}
      <ConfirmDialog
        open={!!deleteTokenConfirm}
        onOpenChange={(open) => !open && setDeleteTokenConfirm(null)}
        title={t('resources.tokens.deleteTitle')}
        description={t('resources.tokens.deleteDescription')}
        variant="destructive"
        onConfirm={() => deleteTokenConfirm && deleteTokenMutation.mutate(deleteTokenConfirm)}
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

      {/* Edit Template Dialog */}
      <Dialog open={editTemplateDialogOpen} onOpenChange={setEditTemplateDialogOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t('resources.templates.editTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="editTemplateName">{t('resources.templates.nameLabel')}</Label>
              <Input
                id="editTemplateName"
                value={editTemplateForm.name}
                onChange={(e) => setEditTemplateForm({ ...editTemplateForm, name: e.target.value })}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="editTemplateJson">{t('resources.templates.jsonLabel')}</Label>
              <textarea
                id="editTemplateJson"
                value={editTemplateForm.templateJson}
                onChange={(e) => setEditTemplateForm({ ...editTemplateForm, templateJson: e.target.value })}
                className="mt-1 w-full h-64 px-3 py-2 bg-dark-700 border border-dark-600 rounded-md text-sm font-mono text-dark-50 focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="{}"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTemplateDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleUpdateTemplate}
              disabled={!editTemplateForm.name.trim() || updateTemplateMutation.isPending}
            >
              {updateTemplateMutation.isPending ? t('common.saving') : t('common.save')}
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
        <DialogContent className="max-w-3xl">
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
              <textarea
                id="snippetJson"
                value={snippetFormData.snippet}
                onChange={(e) => setSnippetFormData({ ...snippetFormData, snippet: e.target.value })}
                className="mt-1 w-full h-64 px-3 py-2 bg-dark-700 border border-dark-600 rounded-md text-sm font-mono text-dark-50 focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="{}"
              />
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
        <DialogContent className="max-w-3xl">
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
              <textarea
                id="editSnippetJson"
                value={editSnippetForm.snippet}
                onChange={(e) => setEditSnippetForm({ ...editSnippetForm, snippet: e.target.value })}
                className="mt-1 w-full h-64 px-3 py-2 bg-dark-700 border border-dark-600 rounded-md text-sm font-mono text-dark-50 focus:outline-none focus:ring-2 focus:ring-primary-500"
                placeholder="{}"
              />
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

      {/* View Computed Config Dialog */}
      <Dialog open={viewConfigDialogOpen} onOpenChange={setViewConfigDialogOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {t('resources.profiles.viewTitle')}: {viewingProfile?.name}
            </DialogTitle>
            <DialogDescription>{t('resources.profiles.viewDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <pre className="w-full max-h-96 overflow-auto px-3 py-2 bg-dark-700 border border-dark-600 rounded-md text-xs font-mono text-dark-50">
              {JSON.stringify(computedConfig, null, 2)}
            </pre>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => computedConfig && copyToClipboard(JSON.stringify(computedConfig, null, 2))}
            >
              <Copy className="w-4 h-4 mr-2" />
              {t('common.copy')}
            </Button>
            <Button onClick={() => setViewConfigDialogOpen(false)}>{t('common.close')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
