/**
 * RunScriptDialog — Select a target node, preview script, execute, view live output.
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Play, RefreshCw, CheckCircle, XCircle, Clock, Server } from 'lucide-react'
import client from '@/api/client'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { getFleetAgents } from '@/api/fleet'
import type { Script } from './ScriptCatalog'

interface RunScriptDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  script: Script | null
}

export default function RunScriptDialog({ open, onOpenChange, script }: RunScriptDialogProps) {
  const { t } = useTranslation()
  const [selectedNode, setSelectedNode] = useState<string>('')
  const [execId, setExecId] = useState<number | null>(null)

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

  // Poll execution status
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

  // Execute script
  const execMutation = useMutation({
    mutationFn: async () => {
      if (!script || !selectedNode) return
      const { data } = await client.post('/fleet/exec-script', {
        script_id: script.id,
        node_uuid: selectedNode,
      })
      return data
    },
    onSuccess: (data) => {
      if (data?.exec_id) {
        setExecId(data.exec_id)
        toast.success(t('fleet.scripts.executing'))
      }
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      toast.error(err.response?.data?.detail || err.message)
    },
  })

  const connectedNodes = agents?.nodes?.filter((n) => n.agent_v2_connected) || []

  const handleClose = () => {
    setSelectedNode('')
    setExecId(null)
    onOpenChange(false)
  }

  const isRunning = execStatus?.status === 'running' || execMutation.isPending

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-base">
            {t('fleet.scripts.run')}: {script?.display_name}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Node selection */}
          <div>
            <label className="text-xs text-dark-200 mb-1.5 block">{t('fleet.scripts.selectNode')}</label>
            <Select value={selectedNode} onValueChange={setSelectedNode} disabled={isRunning}>
              <SelectTrigger>
                <SelectValue placeholder={t('fleet.scripts.selectNode')} />
              </SelectTrigger>
              <SelectContent>
                {connectedNodes.length === 0 ? (
                  <SelectItem value="_none" disabled>
                    {t('fleet.terminal.agentNotConnected')}
                  </SelectItem>
                ) : (
                  connectedNodes.map((node) => (
                    <SelectItem key={node.uuid} value={node.uuid}>
                      <div className="flex items-center gap-2">
                        <Server className="w-3 h-3 text-green-400" />
                        {node.name} ({node.address})
                      </div>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          {/* Script preview */}
          {scriptDetail?.script_content && (
            <div>
              <label className="text-xs text-dark-200 mb-1.5 block">{t('fleet.scripts.scriptContent')}</label>
              <pre className="bg-dark-900 border border-dark-700 rounded-md p-3 text-xs font-mono text-dark-100 max-h-[150px] overflow-auto whitespace-pre-wrap">
                {scriptDetail.script_content}
              </pre>
            </div>
          )}

          {/* Execute button */}
          {!execId && (
            <Button
              onClick={() => execMutation.mutate()}
              disabled={!selectedNode || execMutation.isPending}
              className="w-full"
            >
              {execMutation.isPending ? (
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Play className="w-4 h-4 mr-2" />
              )}
              {t('fleet.scripts.run')}
            </Button>
          )}

          {/* Execution output */}
          {execId && (
            <>
              <Separator />
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs text-dark-200">{t('fleet.scripts.output')}</span>
                  {isRunning && (
                    <Badge variant="secondary" className="text-[10px] gap-1">
                      <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                      {t('fleet.scripts.running')}
                    </Badge>
                  )}
                  {execStatus?.status === 'completed' && (
                    <Badge variant="success" className="text-[10px] gap-1">
                      <CheckCircle className="w-2.5 h-2.5" />
                      {t('fleet.scripts.exitCode')}: {execStatus.exit_code}
                    </Badge>
                  )}
                  {(execStatus?.status === 'error' || execStatus?.status === 'blocked') && (
                    <Badge variant="destructive" className="text-[10px] gap-1">
                      <XCircle className="w-2.5 h-2.5" />
                      {execStatus.status}
                    </Badge>
                  )}
                  {execStatus?.duration_ms != null && (
                    <span className="text-[10px] text-dark-400 ml-auto flex items-center gap-1">
                      <Clock className="w-2.5 h-2.5" />
                      {(execStatus.duration_ms / 1000).toFixed(1)}s
                    </span>
                  )}
                </div>
                <pre className="bg-dark-900 border border-dark-700 rounded-md p-3 text-xs font-mono text-dark-100 max-h-[300px] overflow-auto whitespace-pre-wrap">
                  {execStatus?.output || (isRunning ? t('fleet.scripts.waitingOutput') : '')}
                </pre>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
