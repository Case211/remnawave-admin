import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  FileText,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  ShieldAlert,
  Eye as EyeIcon,
  Globe,
  Network,
  Search,
  Play,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { reportsApi, asnApi, ViolationReport, ASNRecord } from '../api/reports'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { useHasPermission } from '@/components/PermissionGate'
import { useFormatters } from '@/lib/useFormatters'

export default function Reports({ embedded }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  const { formatDate } = useFormatters()

  const canCreate = useHasPermission('reports', 'create')

  const [activeTab, setActiveTab] = useState('reports')
  const [reportFilter, setReportFilter] = useState<string>('')
  const [expandedReport, setExpandedReport] = useState<number | null>(null)
  const [generateDialogOpen, setGenerateDialogOpen] = useState(false)
  const [generateType, setGenerateType] = useState('daily')

  // ASN state
  const [asnSearch, setAsnSearch] = useState('')
  const [asnTypeFilter, setAsnTypeFilter] = useState<string>('')

  // ── Reports ───────────────────────────────────────────────────

  const { data: reports = [], isLoading: reportsLoading, refetch: refetchReports } = useQuery({
    queryKey: ['violation-reports', reportFilter],
    queryFn: () => reportsApi.getReports(reportFilter || undefined),
  })

  const generateMutation = useMutation({
    mutationFn: (type: string) => reportsApi.generateReport(type),
    onSuccess: () => {
      setGenerateDialogOpen(false)
      refetchReports()
      toast.success(t('reports.generated'))
    },
    onError: () => {
      toast.error(t('reports.generateError'))
    },
  })

  // ── ASN ───────────────────────────────────────────────────────

  const { data: asnStats, isLoading: asnStatsLoading } = useQuery({
    queryKey: ['asn-stats'],
    queryFn: asnApi.getStats,
    enabled: activeTab === 'asn',
  })

  const { data: asnSearchResults = [], isFetching: asnSearching } = useQuery({
    queryKey: ['asn-search', asnSearch],
    queryFn: () => asnApi.search(asnSearch),
    enabled: asnSearch.length >= 2,
  })

  const { data: asnTypeResults = [], isFetching: asnTypeLoading } = useQuery({
    queryKey: ['asn-by-type', asnTypeFilter],
    queryFn: () => asnApi.getByType(asnTypeFilter),
    enabled: !!asnTypeFilter,
  })

  const syncMutation = useMutation({
    mutationFn: () => asnApi.sync(100),
    onSuccess: (data) => {
      toast.success(t('reports.asn.syncSuccess', { count: data.success }))
    },
    onError: () => {
      toast.error(t('reports.asn.syncError'))
    },
  })

  const getTrendIcon = (report: ViolationReport) => {
    if (!report.trend_percent) return <Minus className="w-4 h-4 text-dark-400" />
    if (report.trend_percent > 0) return <TrendingUp className="w-4 h-4 text-red-400" />
    return <TrendingDown className="w-4 h-4 text-green-400" />
  }

  const getSeverityColor = (count: number, type: 'critical' | 'warning' | 'monitor') => {
    if (count === 0) return 'text-dark-400'
    if (type === 'critical') return 'text-red-400'
    if (type === 'warning') return 'text-yellow-400'
    return 'text-blue-400'
  }

  const providerTypes = [
    'mobile', 'mobile_isp', 'fixed', 'isp', 'regional_isp',
    'hosting', 'datacenter', 'vpn', 'business', 'infrastructure',
  ]

  return (
    <div className={embedded ? 'space-y-4' : 'space-y-6'}>
      {!embedded && (
        <div className="page-header">
          <div>
            <h1 className="page-header-title">{t('reports.title')}</h1>
            <p className="text-dark-200 mt-1">{t('reports.subtitle')}</p>
          </div>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="reports">
            <FileText className="w-4 h-4 mr-2" />
            {t('reports.tabs.reports')}
          </TabsTrigger>
          <TabsTrigger value="asn">
            <Network className="w-4 h-4 mr-2" />
            {t('reports.tabs.asn')}
          </TabsTrigger>
        </TabsList>

        {/* ── Tab 1: Reports ────────────────────────────────── */}
        <TabsContent value="reports" className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Select value={reportFilter} onValueChange={(v) => setReportFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder={t('reports.filterAll')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('reports.filterAll')}</SelectItem>
                  <SelectItem value="daily">{t('reports.filterDaily')}</SelectItem>
                  <SelectItem value="weekly">{t('reports.filterWeekly')}</SelectItem>
                  <SelectItem value="monthly">{t('reports.filterMonthly')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => refetchReports()}>
                <RefreshCw className="w-4 h-4" />
              </Button>
              {canCreate && (
                <Button size="sm" onClick={() => setGenerateDialogOpen(true)}>
                  <Play className="w-4 h-4 mr-2" />
                  {t('reports.generate')}
                </Button>
              )}
            </div>
          </div>

          {reportsLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </div>
          ) : reports.length === 0 ? (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <FileText className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('reports.empty')}</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {reports.map((report) => (
                <Card
                  key={report.id}
                  className="border-dark-600 bg-dark-800 hover:border-dark-500 transition-colors cursor-pointer"
                  onClick={() => setExpandedReport(expandedReport === report.id ? null : report.id)}
                >
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Badge variant="outline" className="text-xs capitalize">
                          {report.report_type}
                        </Badge>
                        <span className="text-sm text-dark-200">
                          {formatDate(report.period_start)} — {formatDate(report.period_end)}
                        </span>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                          {getTrendIcon(report)}
                          {report.trend_percent !== null && (
                            <span className={`text-xs ${report.trend_percent > 0 ? 'text-red-400' : 'text-green-400'}`}>
                              {report.trend_percent > 0 ? '+' : ''}{report.trend_percent.toFixed(1)}%
                            </span>
                          )}
                        </div>
                        <span className="text-white font-medium">{report.total_violations}</span>
                        {expandedReport === report.id ? (
                          <ChevronUp className="w-4 h-4 text-dark-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-dark-400" />
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-4 mt-2">
                      <span className={`text-xs ${getSeverityColor(report.critical_count, 'critical')}`}>
                        <ShieldAlert className="w-3 h-3 inline mr-1" />
                        {report.critical_count}
                      </span>
                      <span className={`text-xs ${getSeverityColor(report.warning_count, 'warning')}`}>
                        <AlertTriangle className="w-3 h-3 inline mr-1" />
                        {report.warning_count}
                      </span>
                      <span className={`text-xs ${getSeverityColor(report.monitor_count, 'monitor')}`}>
                        <EyeIcon className="w-3 h-3 inline mr-1" />
                        {report.monitor_count}
                      </span>
                      <span className="text-xs text-dark-300">
                        {t('reports.uniqueUsers')}: {report.unique_users}
                      </span>
                    </div>

                    {/* Expanded content */}
                    {expandedReport === report.id && (
                      <div className="mt-4 pt-4 border-t border-dark-600 space-y-4">
                        {/* Top violators */}
                        {report.top_violators && report.top_violators.length > 0 && (
                          <div>
                            <h4 className="text-xs font-medium text-dark-300 mb-2">{t('reports.topViolators')}</h4>
                            <div className="space-y-1">
                              {report.top_violators.slice(0, 5).map((v, i) => (
                                <div key={i} className="flex items-center justify-between text-xs">
                                  <span className="text-dark-100">{v.username || v.uuid?.slice(0, 8)}</span>
                                  <span className="text-dark-300">
                                    {t('reports.score')}: <span className="text-white">{v.score}</span>
                                    {' · '}
                                    {v.violations_count} {t('reports.violations')}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* By country */}
                        {report.by_country && Object.keys(report.by_country).length > 0 && (
                          <div>
                            <h4 className="text-xs font-medium text-dark-300 mb-2">{t('reports.byCountry')}</h4>
                            <div className="flex flex-wrap gap-2">
                              {Object.entries(report.by_country)
                                .sort(([, a], [, b]) => b - a)
                                .slice(0, 8)
                                .map(([country, count]) => (
                                  <Badge key={country} variant="outline" className="text-xs">
                                    {country}: {count}
                                  </Badge>
                                ))}
                            </div>
                          </div>
                        )}

                        {/* By ASN type */}
                        {report.by_asn_type && Object.keys(report.by_asn_type).length > 0 && (
                          <div>
                            <h4 className="text-xs font-medium text-dark-300 mb-2">{t('reports.byAsnType')}</h4>
                            <div className="flex flex-wrap gap-2">
                              {Object.entries(report.by_asn_type)
                                .sort(([, a], [, b]) => b - a)
                                .map(([type, count]) => (
                                  <Badge key={type} variant="outline" className="text-xs">
                                    {type}: {count}
                                  </Badge>
                                ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Tab 2: ASN Database ───────────────────────────── */}
        <TabsContent value="asn" className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-dark-200">{t('reports.asn.description')}</p>
            <div className="flex gap-2">
              {canCreate && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => syncMutation.mutate()}
                  disabled={syncMutation.isPending}
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                  {syncMutation.isPending ? t('reports.asn.syncing') : t('reports.asn.sync')}
                </Button>
              )}
            </div>
          </div>

          {/* ASN Stats */}
          {asnStatsLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : asnStats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Card className="border-dark-600 bg-dark-800">
                <CardContent className="p-3">
                  <p className="text-xs text-dark-400">{t('reports.asn.totalRecords')}</p>
                  <p className="text-xl font-bold text-white mt-1">{asnStats.total}</p>
                </CardContent>
              </Card>
              {Object.entries(asnStats.by_type)
                .filter(([, count]) => count > 0)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 3)
                .map(([type, count]) => (
                  <Card key={type} className="border-dark-600 bg-dark-800">
                    <CardContent className="p-3">
                      <p className="text-xs text-dark-400 capitalize">{type.replace('_', ' ')}</p>
                      <p className="text-xl font-bold text-white mt-1">{count}</p>
                    </CardContent>
                  </Card>
                ))}
            </div>
          )}

          {/* Search & Filter */}
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dark-400" />
              <Input
                value={asnSearch}
                onChange={(e) => { setAsnSearch(e.target.value); setAsnTypeFilter('') }}
                placeholder={t('reports.asn.searchPlaceholder')}
                className="pl-9"
              />
            </div>
            <Select value={asnTypeFilter || 'all'} onValueChange={(v) => { setAsnTypeFilter(v === 'all' ? '' : v); setAsnSearch('') }}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder={t('reports.asn.filterByType')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('reports.asn.allTypes')}</SelectItem>
                {(asnStats ? Object.entries(asnStats.by_type).sort(([,a],[,b]) => b - a).map(([pt]) => pt) : providerTypes).map((pt) => (
                  <SelectItem key={pt} value={pt}>
                    {pt.replace('_', ' ')}
                    {asnStats?.by_type[pt] ? ` (${asnStats.by_type[pt]})` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* ASN Results */}
          {(asnSearching || asnTypeLoading) ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : (asnSearch.length >= 2 || asnTypeFilter) ? (
            <ASNTable records={asnTypeFilter ? asnTypeResults : asnSearchResults} t={t} />
          ) : (
            <Card className="border-dark-600 bg-dark-800">
              <CardContent className="p-8 text-center">
                <Globe className="w-12 h-12 mx-auto mb-3 text-dark-400" />
                <p className="text-dark-200">{t('reports.asn.searchHint')}</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Generate Report Dialog */}
      <Dialog open={generateDialogOpen} onOpenChange={setGenerateDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t('reports.generateTitle')}</DialogTitle>
            <DialogDescription>{t('reports.generateDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>{t('reports.reportType')}</Label>
              <Select value={generateType} onValueChange={setGenerateType}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">{t('reports.filterDaily')}</SelectItem>
                  <SelectItem value="weekly">{t('reports.filterWeekly')}</SelectItem>
                  <SelectItem value="monthly">{t('reports.filterMonthly')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGenerateDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => generateMutation.mutate(generateType)}
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending ? t('reports.generating') : t('reports.generate')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ASNTable({ records, t }: { records: ASNRecord[]; t: (key: string, options?: Record<string, unknown>) => string }) {
  if (records.length === 0) {
    return (
      <Card className="border-dark-600 bg-dark-800">
        <CardContent className="p-8 text-center">
          <Network className="w-12 h-12 mx-auto mb-3 text-dark-400" />
          <p className="text-dark-200">{t('reports.asn.noResults')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-dark-600 bg-dark-800">
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-dark-600">
              <tr>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">ASN</th>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">{t('reports.asn.orgName')}</th>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">{t('reports.asn.type')}</th>
                <th className="text-left text-xs font-medium text-dark-300 px-4 py-3">{t('reports.asn.region')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-600">
              {records.slice(0, 50).map((record) => (
                <tr key={record.asn} className="hover:bg-dark-700/50 transition-colors">
                  <td className="px-4 py-3 text-sm font-mono text-white">AS{record.asn}</td>
                  <td className="px-4 py-3 text-sm text-dark-100">
                    <div>{record.org_name}</div>
                    {record.org_name_en && record.org_name_en !== record.org_name && (
                      <div className="text-xs text-dark-300">{record.org_name_en}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {record.provider_type && (
                      <Badge variant="outline" className="text-xs capitalize">
                        {record.provider_type.replace('_', ' ')}
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-dark-200">
                    {[record.region, record.city].filter(Boolean).join(', ') || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {records.length > 50 && (
          <div className="text-center text-xs text-dark-400 py-2 border-t border-dark-600">
            {t('reports.asn.showingOf', { shown: 50, total: records.length })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
