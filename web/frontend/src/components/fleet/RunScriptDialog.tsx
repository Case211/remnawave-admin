/**
 * RunScriptDialog — Select one or many target nodes, preview script, execute,
 * and view live per-node output. Automatically detects configurable
 * parameters (${VAR:-default}) and shows input fields shared across nodes.
 */
import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Play, RefreshCw, CheckCircle, XCircle, Clock, Server, Settings2 } from '@/components/brand/icons'
import client from '@/api/client'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { getFleetAgents, execScriptBulk } from '@/api/fleet'
import type { Script } from './ScriptCatalog'

interface RunScriptDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  script: Script | null
}

interface ScriptParam {
  name: string
  defaultValue: string
}

interface ExecResultRow {
  node_uuid: string
  node_name: string
  exec_id?: number
  error?: string
}

/** Parse ${VAR:-default} patterns from script content. */
function parseScriptParams(content: string): ScriptParam[] {
  const seen = new Set<string>()
  const params: ScriptParam[] = []
  const regex = /\$\{(\w+):-([^}]*)\}/g
  let match
  while ((match = regex.exec(content)) !== null) {
    const name = match[1]
    if (!seen.has(name)) {
      seen.add(name)
      params.push({ name, defaultValue: match[2] })
    }
  }
  return params
}

/** Single node's execution output — polls its own exec_id independently. */
function ExecResult({ execId, nodeName, error }: { execId?: number; nodeName: string; error?: string }) {
  const { t } = useTranslation()

  const { data: execStatus } = useQuery({
    queryKey: ['fleet-exec', execId],
    queryFn: async () => {
      if (!execId) return null
      const { data } = await client.get(`/fleet/exec/${execId}`)
      return data
    },
    enabled: !!execId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'error' || status === 'blocked') return false
      return 2000
    },
  })

  const running = !error && (execStatus?.status === 'running' || !execStatus)

  return (
    <div className="border border-[var(--glass-border)] rounded-md p-3">
      <div className="flex items-center gap-2 mb-2">
        <Server className="w-3 h-3 text-green-400 shrink-0" />
        <span className="text-xs font-medium text-white truncate">{nodeName}</span>
        {error ? (
          <Badge variant="destructive" className="text-[10px] gap-1">
            <XCircle className="w-2.5 h-2.5" />
            {error}
          </Badge>
        ) : running ? (
          <Badge variant="secondary" className="text-[10px] gap-1">
            <RefreshCw className="w-2.5 h-2.5 animate-spin" />
            {t('fleet.scripts.running')}
          </Badge>
        ) : execStatus?.status === 'completed' ? (
          <Badge variant="success" className="text-[10px] gap-1">
            <CheckCircle className="w-2.5 h-2.5" />
            {t('fleet.scripts.exitCode')}: {execStatus.exit_code}
          </Badge>
        ) : (
          <Badge variant="destructive" className="text-[10px] gap-1">
            <XCircle className="w-2.5 h-2.5" />
            {execStatus?.status}
          </Badge>
        )}
        {execStatus?.duration_ms != null && (
          <span className="text-[10px] text-dark-400 ml-auto flex items-center gap-1 shrink-0">
            <Clock className="w-2.5 h-2.5" />
            {(execStatus.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
      </div>
      {!error && (
        <pre className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-md p-2 text-xs font-mono text-dark-100 max-h-[200px] overflow-auto whitespace-pre-wrap">
          {execStatus?.output || (running ? t('fleet.scripts.waitingOutput') : '')}
        </pre>
      )}
    </div>
  )
}

export default function RunScriptDialog({ open, onOpenChange, script }: RunScriptDialogProps) {
  const { t } = useTranslation()
  const [selectedNodes, setSelectedNodes] = useState<string[]>([])
  const [nodeSearch, setNodeSearch] = useState('')
  const [execResults, setExecResults] = useState<ExecResultRow[] | null>(null)
  const [envVars, setEnvVars] = useState<Record<string, string>>({})

  // Fetch connected agents
  const { data: agents } = useQuery({
    queryKey: ['fleet-agents'],
    queryFn: getFleetAgents,
    enabled: open,
  })

  // Fetch script content
  const { data: scriptDetail } = useQuery({
    queryKey: ['fleet-script', script?.id],
    queryFn: async () => {
      if (!script) return null
      const { data } = await client.get(`/fleet/scripts/${script.id}`)
      return data
    },
    enabled: open && !!script,
  })

  // Parse configurable parameters from script
  const scriptParams = useMemo(() => {
    if (!scriptDetail?.script_content) return []
    return parseScriptParams(scriptDetail.script_content)
  }, [scriptDetail?.script_content])

  const connectedNodes = agents?.nodes?.filter((n) => n.agent_v2_connected) || []
  // Поиск по имени и адресу: когда нод десятки, глазами искать неудобно
  const needle = nodeSearch.trim().toLowerCase()
  const visibleNodes = needle
    ? connectedNodes.filter((n) => `${n.name} ${n.address}`.toLowerCase().includes(needle))
    : connectedNodes
  // «Выбрать все» работает с тем, что сейчас показано: с поиском — только с найденными
  const allSelected = visibleNodes.length > 0 && visibleNodes.every((n) => selectedNodes.includes(n.uuid))

  const toggleNode = (uuid: string) => {
    setSelectedNodes((prev) =>
      prev.includes(uuid) ? prev.filter((u) => u !== uuid) : [...prev, uuid],
    )
    setExecResults(null)
  }

  const toggleAll = () => {
    const visible = visibleNodes.map((n) => n.uuid)
    setSelectedNodes((prev) =>
      allSelected ? prev.filter((u) => !visible.includes(u)) : Array.from(new Set([...prev, ...visible])),
    )
    setExecResults(null)
  }

  // Execute script on all selected nodes
  const execMutation = useMutation({
    mutationFn: async () => {
      if (!script || selectedNodes.length === 0) return
      // Only send env_vars that differ from defaults
      const overrides: Record<string, string> = {}
      for (const param of scriptParams) {
        const val = envVars[param.name]
        if (val && val !== param.defaultValue) {
          overrides[param.name] = val
        }
      }
      return execScriptBulk(script.id, selectedNodes, overrides)
    },
    onSuccess: (data) => {
      if (!data?.results) return
      const nameByUuid = new Map(connectedNodes.map((n) => [n.uuid, n.name]))
      setExecResults(
        data.results.map((r) => ({
          node_uuid: r.node_uuid,
          node_name: nameByUuid.get(r.node_uuid) || r.node_uuid,
          exec_id: r.exec_id,
          error: r.error,
        })),
      )
      toast.success(t('fleet.scripts.executing'))
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message)
    },
  })

  const handleClose = () => {
    setSelectedNodes([])
    setNodeSearch('')
    setExecResults(null)
    setEnvVars({})
    onOpenChange(false)
  }

  useEffect(() => {
    if (open) {
      setSelectedNodes([])
      setNodeSearch('')
      setExecResults(null)
      setEnvVars({})
    }
  }, [script?.id, open])

  const isRunning = execMutation.isPending

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base">
            {t('fleet.scripts.run')}: {script?.display_name}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Node selection */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs text-dark-200">
                {t('fleet.scripts.selectNodes')}
                {selectedNodes.length > 0 && (
                  <span className="text-dark-400"> ({selectedNodes.length})</span>
                )}
              </label>
              {connectedNodes.length > 0 && (
                <button
                  type="button"
                  onClick={toggleAll}
                  disabled={isRunning}
                  className="text-[11px] text-primary-400 hover:text-primary-300 disabled:opacity-50"
                >
                  {allSelected ? t('fleet.scripts.deselectAll') : t('fleet.scripts.selectAll')}
                </button>
              )}
            </div>
            {connectedNodes.length > 5 && (
              <Input
                value={nodeSearch}
                onChange={(e) => setNodeSearch(e.target.value)}
                placeholder={t('fleet.searchPlaceholder')}
                aria-label={t('fleet.searchPlaceholder')}
                className="h-8 text-xs mb-1.5"
              />
            )}
            {connectedNodes.length === 0 ? (
              <p className="text-xs text-dark-400 py-2">{t('fleet.terminal.agentNotConnected')}</p>
            ) : (
              <div className="max-h-[180px] overflow-auto rounded-md border border-[var(--glass-border)] divide-y divide-[var(--glass-border)]">
                {visibleNodes.length === 0 && (
                  <p className="text-xs text-dark-400 px-3 py-2">{t('fleet.nothingFound')}</p>
                )}
                {visibleNodes.map((node) => (
                  <label
                    key={node.uuid}
                    className="flex items-center gap-2.5 px-3 py-2 hover:bg-[var(--glass-bg)] cursor-pointer"
                  >
                    <Checkbox
                      checked={selectedNodes.includes(node.uuid)}
                      onCheckedChange={() => toggleNode(node.uuid)}
                      disabled={isRunning}
                    />
                    <Server className="w-3 h-3 text-green-400 shrink-0" />
                    <span className="text-xs text-white truncate">{node.name}</span>
                    <span className="text-[10px] text-dark-400 truncate ml-auto">{node.address}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Script parameters */}
          {scriptParams.length > 0 && !execResults && (
            <div>
              <label className="text-xs text-dark-200 mb-1.5 flex items-center gap-1.5">
                <Settings2 className="w-3 h-3" />
                {t('fleet.scripts.parameters', 'Parameters')}
              </label>
              <div className="space-y-2">
                {scriptParams.map((param) => (
                  <div key={param.name} className="flex items-center gap-2">
                    <code className="text-xs text-teal-400 min-w-[120px] font-mono shrink-0">
                      {param.name}
                    </code>
                    <Input
                      className="h-8 text-xs font-mono"
                      placeholder={param.defaultValue}
                      value={envVars[param.name] || ''}
                      onChange={(e) =>
                        setEnvVars((prev) => ({
                          ...prev,
                          [param.name]: e.target.value,
                        }))
                      }
                      disabled={isRunning}
                    />
                  </div>
                ))}
                <p className="text-[10px] text-dark-400">
                  {t(
                    'fleet.scripts.parametersHint',
                    'Leave empty to use defaults shown as placeholders',
                  )}
                </p>
              </div>
            </div>
          )}

          {/* Script preview */}
          {scriptDetail?.script_content && (
            <div>
              <label className="text-xs text-dark-200 mb-1.5 block">
                {t('fleet.scripts.scriptContent')}
              </label>
              <pre className="bg-[var(--glass-bg)] border border-[var(--glass-border)] rounded-md p-3 text-xs font-mono text-dark-100 max-h-[150px] overflow-auto whitespace-pre-wrap">
                {scriptDetail.script_content}
              </pre>
            </div>
          )}

          {/* Execute button */}
          {!execResults && (
            <Button
              onClick={() => execMutation.mutate()}
              disabled={selectedNodes.length === 0 || execMutation.isPending}
              className="w-full"
            >
              {execMutation.isPending ? (
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Play className="w-4 h-4 mr-2" />
              )}
              {selectedNodes.length > 1
                ? t('fleet.scripts.runOnCount', { count: selectedNodes.length })
                : t('fleet.scripts.run')}
            </Button>
          )}

          {/* Execution output — one panel per node */}
          {execResults && (
            <>
              <Separator />
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-dark-200">{t('fleet.scripts.output')}</span>
                  <button
                    type="button"
                    onClick={() => setExecResults(null)}
                    className="text-[11px] text-primary-400 hover:text-primary-300"
                  >
                    {t('fleet.scripts.runAgain', 'Run again')}
                  </button>
                </div>
                {execResults.map((r) => (
                  <ExecResult
                    key={r.node_uuid}
                    execId={r.exec_id}
                    nodeName={r.node_name}
                    error={r.error}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
