import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Plus,
  Trash2,
  Pencil,
  RefreshCw,
  CreditCard,
  Building2,
  History,
  Server,
  ExternalLink,
  Calendar,
} from 'lucide-react'
import { billingApi, Provider } from '../api/billing'
import client from '../api/client'
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
import { useFormatters } from '@/lib/useFormatters'

interface Node {
  uuid: string
  name: string
  countryCode: string
}

export default function Billing({ embedded }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  const { formatDate, formatCurrency } = useFormatters()
  const queryClient = useQueryClient()

  // Permissions
  const canCreate = useHasPermission('billing', 'create')
  const canUpdate = useHasPermission('billing', 'update')
  const canDelete = useHasPermission('billing', 'delete')

  // Tab state
  const [activeTab, setActiveTab] = useState('providers')

  // ── Providers ───────────────────────────────────────────────────
  const [providerDialogOpen, setProviderDialogOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null)
  const [providerFormData, setProviderFormData] = useState({ name: '', faviconLink: '', loginUrl: '' })
  const [deleteProviderConfirm, setDeleteProviderConfirm] = useState<string | null>(null)

  const { data: providers = [], isLoading: providersLoading, refetch: refetchProviders } = useQuery({
    queryKey: ['billing-providers'],
    queryFn: billingApi.getProviders,
  })

  const createProviderMutation = useMutation({
    mutationFn: (data: { name: string; faviconLink?: string; loginUrl?: string }) =>
      billingApi.createProvider(data),
    onSuccess: () => {
      setProviderDialogOpen(false)
      setProviderFormData({ name: '', faviconLink: '', loginUrl: '' })
      setEditingProvider(null)
      queryClient.invalidateQueries({ queryKey: ['billing-providers'] })
      toast.success(t('billing.providers.created'))
    },
    onError: () => {
      toast.error(t('billing.providers.createError'))
    },
  })

  const updateProviderMutation = useMutation({
    mutationFn: (data: { uuid: string; name?: string; faviconLink?: string; loginUrl?: string }) =>
      billingApi.updateProvider(data),
    onSuccess: () => {
      setProviderDialogOpen(false)
      setProviderFormData({ name: '', faviconLink: '', loginUrl: '' })
      setEditingProvider(null)
      queryClient.invalidateQueries({ queryKey: ['billing-providers'] })
      toast.success(t('billing.providers.updated'))
    },
    onError: () => {
      toast.error(t('billing.providers.updateError'))
    },
  })

  const deleteProviderMutation = useMutation({
    mutationFn: (uuid: string) => billingApi.deleteProvider(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['billing-providers'] })
      toast.success(t('billing.providers.deleted'))
      setDeleteProviderConfirm(null)
    },
    onError: () => {
      toast.error(t('billing.providers.deleteError'))
    },
  })

  const openProviderDialog = (provider?: Provider) => {
    if (provider) {
      setEditingProvider(provider)
      setProviderFormData({
        name: provider.name,
        faviconLink: provider.faviconLink || '',
        loginUrl: provider.loginUrl || '',
      })
    } else {
      setEditingProvider(null)
      setProviderFormData({ name: '', faviconLink: '', loginUrl: '' })
    }
    setProviderDialogOpen(true)
  }

  const handleSaveProvider = () => {
    if (editingProvider) {
      updateProviderMutation.mutate({
        uuid: editingProvider.uuid,
        name: providerFormData.name,
        faviconLink: providerFormData.faviconLink || undefined,
        loginUrl: providerFormData.loginUrl || undefined,
      })
    } else {
      createProviderMutation.mutate({
        name: providerFormData.name,
        faviconLink: providerFormData.faviconLink || undefined,
        loginUrl: providerFormData.loginUrl || undefined,
      })
    }
  }

  // ── Billing History ─────────────────────────────────────────────
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false)
  const [historyFormData, setHistoryFormData] = useState({ providerUuid: '', amount: '', billedAt: '' })
  const [deleteHistoryConfirm, setDeleteHistoryConfirm] = useState<string | null>(null)

  const { data: history = [], isLoading: historyLoading, refetch: refetchHistory } = useQuery({
    queryKey: ['billing-history'],
    queryFn: billingApi.getHistory,
  })

  const createHistoryMutation = useMutation({
    mutationFn: (data: { providerUuid: string; amount: number; billedAt: string }) =>
      billingApi.createRecord(data),
    onSuccess: () => {
      setHistoryDialogOpen(false)
      setHistoryFormData({ providerUuid: '', amount: '', billedAt: '' })
      queryClient.invalidateQueries({ queryKey: ['billing-history'] })
      queryClient.invalidateQueries({ queryKey: ['billing-providers'] })
      toast.success(t('billing.history.created'))
    },
    onError: () => {
      toast.error(t('billing.history.createError'))
    },
  })

  const deleteHistoryMutation = useMutation({
    mutationFn: (uuid: string) => billingApi.deleteRecord(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['billing-history'] })
      queryClient.invalidateQueries({ queryKey: ['billing-providers'] })
      toast.success(t('billing.history.deleted'))
      setDeleteHistoryConfirm(null)
    },
    onError: () => {
      toast.error(t('billing.history.deleteError'))
    },
  })

  const handleCreateHistory = () => {
    createHistoryMutation.mutate({
      providerUuid: historyFormData.providerUuid,
      amount: parseFloat(historyFormData.amount),
      billedAt: historyFormData.billedAt,
    })
  }

  // Calculate total stats
  const totalAmount = history.reduce((sum, record) => sum + record.amount, 0)
  const totalRecords = history.length

  // ── Billing Nodes ───────────────────────────────────────────────
  const [nodeDialogOpen, setNodeDialogOpen] = useState(false)
  const [nodeFormData, setNodeFormData] = useState({ providerUuid: '', nodeUuid: '', nextBillingAt: '' })
  const [deleteNodeConfirm, setDeleteNodeConfirm] = useState<string | null>(null)

  const { data: nodesData, isLoading: nodesLoading, refetch: refetchNodes } = useQuery({
    queryKey: ['billing-nodes'],
    queryFn: billingApi.getNodes,
  })

  const { data: availableNodes = { items: [] } } = useQuery<{ items: Node[] }>({
    queryKey: ['nodes-list'],
    queryFn: async () => {
      const { data } = await client.get('/nodes')
      return data
    },
  })

  const createNodeMutation = useMutation({
    mutationFn: (data: { providerUuid: string; nodeUuid: string; nextBillingAt?: string }) =>
      billingApi.createNode(data),
    onSuccess: () => {
      setNodeDialogOpen(false)
      setNodeFormData({ providerUuid: '', nodeUuid: '', nextBillingAt: '' })
      queryClient.invalidateQueries({ queryKey: ['billing-nodes'] })
      queryClient.invalidateQueries({ queryKey: ['billing-providers'] })
      toast.success(t('billing.nodes.created'))
    },
    onError: () => {
      toast.error(t('billing.nodes.createError'))
    },
  })

  const deleteNodeMutation = useMutation({
    mutationFn: (uuid: string) => billingApi.deleteNode(uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['billing-nodes'] })
      queryClient.invalidateQueries({ queryKey: ['billing-providers'] })
      toast.success(t('billing.nodes.deleted'))
      setDeleteNodeConfirm(null)
    },
    onError: () => {
      toast.error(t('billing.nodes.deleteError'))
    },
  })

  const handleCreateNode = () => {
    createNodeMutation.mutate({
      providerUuid: nodeFormData.providerUuid,
      nodeUuid: nodeFormData.nodeUuid,
      nextBillingAt: nodeFormData.nextBillingAt || undefined,
    })
  }

  const billingNodes = Array.isArray(nodesData?.billingNodes) ? nodesData.billingNodes : []
  const stats = nodesData?.stats

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-6'}>
      {!embedded && (
        <div className="page-header">
          <div>
            <h1 className="page-header-title">{t('billing.title')}</h1>
            <p className="text-dark-200 mt-1">{t('billing.subtitle')}</p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="providers">
            <Building2 className="w-4 h-4 mr-2" />
            {t('billing.tabs.providers')}
          </TabsTrigger>
          <TabsTrigger value="history">
            <History className="w-4 h-4 mr-2" />
            {t('billing.tabs.history')}
          </TabsTrigger>
          <TabsTrigger value="nodes">
            <Server className="w-4 h-4 mr-2" />
            {t('billing.tabs.nodes')}
          </TabsTrigger>
        </TabsList>

        {/* ── Tab 1: Providers ────────────────────────────────── */}
        <TabsContent value="providers" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('billing.providers.description')}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchProviders()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => openProviderDialog()}>
                  <Plus className="w-4 h-4 mr-2" />
                  {t('billing.providers.create')}
                </Button>
              )}
            </div>
          </div>

          {providersLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : providers.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <Building2 className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('billing.providers.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {providers.map((provider) => (
                <Card
                  key={provider.uuid}
                  className="border-dark-600 bg-dark-800 hover:border-dark-500 transition-colors"
                >
                  <CardContent className="p-4">
                    <div className="space-y-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          {provider.faviconLink && (
                            <img
                              src={provider.faviconLink}
                              alt={provider.name}
                              className="w-8 h-8 rounded flex-shrink-0"
                              onError={(e) => {
                                e.currentTarget.style.display = 'none'
                              }}
                            />
                          )}
                          <h3 className="font-medium text-white truncate">{provider.name}</h3>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {canUpdate && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openProviderDialog(provider)}
                              className="h-7 px-2"
                            >
                              <Pencil className="w-4 h-4" />
                            </Button>
                          )}
                          {canDelete && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setDeleteProviderConfirm(provider.uuid)}
                              className="text-red-400 hover:text-red-300 hover:bg-red-500/10 h-7 px-2"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          )}
                        </div>
                      </div>
                      {provider.loginUrl && (
                        <a
                          href={provider.loginUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 text-xs text-primary-400 hover:text-primary-300 transition-colors"
                        >
                          <ExternalLink className="w-3 h-3" />
                          {t('billing.providers.openPanel')}
                        </a>
                      )}
                      {provider.billingHistory && (
                        <div className="text-xs text-dark-300 space-y-1">
                          <div>
                            {t('billing.providers.totalSpent')}: {formatCurrency(provider.billingHistory.totalAmount)}
                          </div>
                          <div>
                            {t('billing.providers.totalBills')}: {provider.billingHistory.totalBills}
                          </div>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Tab 2: Billing History ──────────────────────────── */}
        <TabsContent value="history" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('billing.history.description')}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchHistory()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => setHistoryDialogOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  {t('billing.history.create')}
                </Button>
              )}
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-dark-400">{t('billing.history.totalAmount')}</p>
                    <p className="text-2xl font-bold text-white mt-1">{formatCurrency(totalAmount)}</p>
                  </div>
                  <CreditCard className="w-8 h-8 text-primary-400" />
                </div>
              </CardContent>
            </Card>
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-dark-400">{t('billing.history.totalRecords')}</p>
                    <p className="text-2xl font-bold text-white mt-1">{totalRecords}</p>
                  </div>
                  <History className="w-8 h-8 text-primary-400" />
                </div>
              </CardContent>
            </Card>
          </div>

          {historyLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : history.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <History className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('billing.history.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b border-dark-600">
                      <tr>
                        <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">
                          {t('billing.history.provider')}
                        </th>
                        <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">
                          {t('billing.history.amount')}
                        </th>
                        <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">
                          {t('billing.history.billedAt')}
                        </th>
                        {canDelete && (
                          <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">
                            {t('common.actions')}
                          </th>
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dark-600">
                      {history.map((record) => (
                        <tr key={record.uuid} className="hover:bg-dark-700/50 transition-colors">
                          <td className="px-4 py-3 text-sm text-white">{record.provider.name}</td>
                          <td className="px-4 py-3 text-sm text-white font-medium">
                            {formatCurrency(record.amount)}
                          </td>
                          <td className="px-4 py-3 text-sm text-dark-200">{formatDate(record.billedAt)}</td>
                          {canDelete && (
                            <td className="px-4 py-3 text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setDeleteHistoryConfirm(record.uuid)}
                                className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Tab 3: Billing Nodes ─────────────────────────────── */}
        <TabsContent value="nodes" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('billing.nodes.description')}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchNodes()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => setNodeDialogOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  {t('billing.nodes.create')}
                </Button>
              )}
            </div>
          </div>

          {/* Stats Cards */}
          {stats && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card className="border-dark-600 bg-dark-800">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-dark-400">{t('billing.nodes.upcoming')}</p>
                      <p className="text-2xl font-bold text-white mt-1">{stats.upcomingNodesCount}</p>
                    </div>
                    <Calendar className="w-8 h-8 text-yellow-400" />
                  </div>
                </CardContent>
              </Card>
              <Card className="border-dark-600 bg-dark-800">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-dark-400">{t('billing.nodes.currentMonth')}</p>
                      <p className="text-2xl font-bold text-white mt-1">{formatCurrency(Number(stats.currentMonthPayments))}</p>
                    </div>
                    <CreditCard className="w-8 h-8 text-primary-400" />
                  </div>
                </CardContent>
              </Card>
              <Card className="border-dark-600 bg-dark-800">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-dark-400">{t('billing.nodes.totalSpent')}</p>
                      <p className="text-2xl font-bold text-white mt-1">{formatCurrency(Number(stats.totalSpent))}</p>
                    </div>
                    <History className="w-8 h-8 text-green-400" />
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {nodesLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : billingNodes.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <Server className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('billing.nodes.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b border-dark-600">
                      <tr>
                        <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">
                          {t('billing.nodes.node')}
                        </th>
                        <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">
                          {t('billing.nodes.provider')}
                        </th>
                        <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">
                          {t('billing.nodes.nextBilling')}
                        </th>
                        {canDelete && (
                          <th className="text-right text-xs font-medium text-dark-300 px-4 py-3">
                            {t('common.actions')}
                          </th>
                        )}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-dark-600">
                      {billingNodes.map((node) => (
                        <tr key={node.uuid} className="hover:bg-dark-700/50 transition-colors">
                          <td className="px-4 py-3 text-sm">
                            <div className="flex items-center gap-2">
                              <span className="text-lg">{node.node.countryCode}</span>
                              <span className="text-white">{node.node.name}</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-sm text-white">{node.provider.name}</td>
                          <td className="px-4 py-3 text-sm">
                            <Badge variant="outline" className="text-xs">
                              {formatDate(node.nextBillingAt)}
                            </Badge>
                          </td>
                          {canDelete && (
                            <td className="px-4 py-3 text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setDeleteNodeConfirm(node.uuid)}
                                className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* ── Dialogs ────────────────────────────────────────────── */}

      {/* Provider Dialog */}
      <Dialog open={providerDialogOpen} onOpenChange={setProviderDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingProvider ? t('billing.providers.editTitle') : t('billing.providers.createTitle')}
            </DialogTitle>
            <DialogDescription>
              {editingProvider ? t('billing.providers.editDescription') : t('billing.providers.createDescription')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="providerName">{t('billing.providers.nameLabel')}</Label>
              <Input
                id="providerName"
                value={providerFormData.name}
                onChange={(e) => setProviderFormData({ ...providerFormData, name: e.target.value })}
                placeholder={t('billing.providers.namePlaceholder')}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="faviconLink">{t('billing.providers.faviconLabel')}</Label>
              <Input
                id="faviconLink"
                value={providerFormData.faviconLink}
                onChange={(e) => setProviderFormData({ ...providerFormData, faviconLink: e.target.value })}
                placeholder={t('billing.providers.faviconPlaceholder')}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="loginUrl">{t('billing.providers.loginUrlLabel')}</Label>
              <Input
                id="loginUrl"
                value={providerFormData.loginUrl}
                onChange={(e) => setProviderFormData({ ...providerFormData, loginUrl: e.target.value })}
                placeholder={t('billing.providers.loginUrlPlaceholder')}
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setProviderDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleSaveProvider}
              disabled={!providerFormData.name.trim() || createProviderMutation.isPending || updateProviderMutation.isPending}
            >
              {createProviderMutation.isPending || updateProviderMutation.isPending ? t('common.saving') : t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Provider Confirm */}
      <ConfirmDialog
        open={!!deleteProviderConfirm}
        onOpenChange={(open) => !open && setDeleteProviderConfirm(null)}
        title={t('billing.providers.deleteTitle')}
        description={t('billing.providers.deleteDescription')}
        variant="destructive"
        onConfirm={() => deleteProviderConfirm && deleteProviderMutation.mutate(deleteProviderConfirm)}
      />

      {/* History Dialog */}
      <Dialog open={historyDialogOpen} onOpenChange={setHistoryDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('billing.history.createTitle')}</DialogTitle>
            <DialogDescription>{t('billing.history.createDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="historyProvider">{t('billing.history.providerLabel')}</Label>
              <Select
                value={historyFormData.providerUuid}
                onValueChange={(value) => setHistoryFormData({ ...historyFormData, providerUuid: value })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t('billing.history.providerPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.uuid} value={provider.uuid}>
                      {provider.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="amount">{t('billing.history.amountLabel')}</Label>
              <Input
                id="amount"
                type="number"
                step="0.01"
                value={historyFormData.amount}
                onChange={(e) => setHistoryFormData({ ...historyFormData, amount: e.target.value })}
                placeholder={t('billing.history.amountPlaceholder')}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="billedAt">{t('billing.history.billedAtLabel')}</Label>
              <Input
                id="billedAt"
                type="datetime-local"
                value={historyFormData.billedAt}
                onChange={(e) => setHistoryFormData({ ...historyFormData, billedAt: e.target.value })}
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setHistoryDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleCreateHistory}
              disabled={!historyFormData.providerUuid || !historyFormData.amount || !historyFormData.billedAt || createHistoryMutation.isPending}
            >
              {createHistoryMutation.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete History Confirm */}
      <ConfirmDialog
        open={!!deleteHistoryConfirm}
        onOpenChange={(open) => !open && setDeleteHistoryConfirm(null)}
        title={t('billing.history.deleteTitle')}
        description={t('billing.history.deleteDescription')}
        variant="destructive"
        onConfirm={() => deleteHistoryConfirm && deleteHistoryMutation.mutate(deleteHistoryConfirm)}
      />

      {/* Node Dialog */}
      <Dialog open={nodeDialogOpen} onOpenChange={setNodeDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('billing.nodes.createTitle')}</DialogTitle>
            <DialogDescription>{t('billing.nodes.createDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="nodeProvider">{t('billing.nodes.providerLabel')}</Label>
              <Select
                value={nodeFormData.providerUuid}
                onValueChange={(value) => setNodeFormData({ ...nodeFormData, providerUuid: value })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t('billing.nodes.providerPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((provider) => (
                    <SelectItem key={provider.uuid} value={provider.uuid}>
                      {provider.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="nodeSelect">{t('billing.nodes.nodeLabel')}</Label>
              <Select
                value={nodeFormData.nodeUuid}
                onValueChange={(value) => setNodeFormData({ ...nodeFormData, nodeUuid: value })}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t('billing.nodes.nodePlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {Array.isArray(availableNodes?.items) && availableNodes.items.map((node) => (
                    <SelectItem key={node.uuid} value={node.uuid}>
                      <span className="flex items-center gap-2">
                        <span>{node.countryCode}</span>
                        <span>{node.name}</span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="nextBillingAt">{t('billing.nodes.nextBillingLabel')}</Label>
              <Input
                id="nextBillingAt"
                type="datetime-local"
                value={nodeFormData.nextBillingAt}
                onChange={(e) => setNodeFormData({ ...nodeFormData, nextBillingAt: e.target.value })}
                className="mt-1"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNodeDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleCreateNode}
              disabled={!nodeFormData.providerUuid || !nodeFormData.nodeUuid || createNodeMutation.isPending}
            >
              {createNodeMutation.isPending ? t('common.creating') : t('common.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Node Confirm */}
      <ConfirmDialog
        open={!!deleteNodeConfirm}
        onOpenChange={(open) => !open && setDeleteNodeConfirm(null)}
        title={t('billing.nodes.deleteTitle')}
        description={t('billing.nodes.deleteDescription')}
        variant="destructive"
        onConfirm={() => deleteNodeConfirm && deleteNodeMutation.mutate(deleteNodeConfirm)}
      />
    </div>
  )
}
