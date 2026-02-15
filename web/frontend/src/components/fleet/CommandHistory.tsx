/**
 * CommandHistory — Table of past script/terminal executions.
 * Supports filtering by node, command type, and pagination.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Clock, CheckCircle, XCircle, RefreshCw, Terminal, FileCode } from 'lucide-react'
import { getCommandLog, type CommandLogEntry } from '@/api/fleet'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return (
        <Badge variant="success" className="text-[10px] gap-1 px-1.5 py-0">
          <CheckCircle className="w-2.5 h-2.5" />
          OK
        </Badge>
      )
    case 'running':
      return (
        <Badge variant="secondary" className="text-[10px] gap-1 px-1.5 py-0">
          <RefreshCw className="w-2.5 h-2.5 animate-spin" />
          Running
        </Badge>
      )
    case 'error':
      return (
        <Badge variant="destructive" className="text-[10px] gap-1 px-1.5 py-0">
          <XCircle className="w-2.5 h-2.5" />
          Error
        </Badge>
      )
    case 'blocked':
      return (
        <Badge variant="destructive" className="text-[10px] gap-1 px-1.5 py-0">
          Blocked
        </Badge>
      )
    default:
      return (
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
          {status}
        </Badge>
      )
  }
}

function TypeIcon({ type }: { type: string }) {
  if (type === 'terminal') return <Terminal className="w-3 h-3 text-green-400" />
  return <FileCode className="w-3 h-3 text-blue-400" />
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return iso
  }
}

export default function CommandHistory() {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const perPage = 25

  const { data, isLoading } = useQuery({
    queryKey: ['fleet-command-log', page, perPage],
    queryFn: () => getCommandLog({ page, per_page: perPage }),
    refetchInterval: 10000,
  })

  const entries = data?.entries || []
  const total = data?.total || 0
  const totalPages = Math.ceil(total / perPage)

  return (
    <div className="space-y-4">
      {isLoading ? (
        <Card>
          <CardContent className="p-4">
            <div className="h-[200px] bg-dark-700/30 rounded animate-pulse" />
          </CardContent>
        </Card>
      ) : entries.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center">
            <Clock className="w-8 h-8 text-dark-300 mx-auto mb-2 opacity-40" />
            <p className="text-dark-300 text-sm">{t('fleet.scripts.noHistory')}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[50px]">#</TableHead>
                    <TableHead>{t('fleet.scripts.historyType')}</TableHead>
                    <TableHead>{t('fleet.scripts.historyAdmin')}</TableHead>
                    <TableHead>{t('fleet.scripts.historyStatus')}</TableHead>
                    <TableHead>{t('fleet.scripts.historyDuration')}</TableHead>
                    <TableHead>{t('fleet.scripts.historyDate')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map((entry: CommandLogEntry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="text-xs font-mono text-dark-400">{entry.id}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <TypeIcon type={entry.command_type} />
                          <span className="text-xs">{entry.command_type}</span>
                          {entry.command_data && (
                            <span className="text-[10px] text-dark-400 truncate max-w-[120px]">
                              {entry.command_data}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-dark-200">
                        {entry.admin_username || '-'}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={entry.status} />
                        {entry.exit_code != null && entry.exit_code !== 0 && (
                          <span className="text-[10px] text-dark-400 ml-1">
                            exit {entry.exit_code}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-dark-300 font-mono">
                        {formatDuration(entry.duration_ms)}
                      </TableCell>
                      <TableCell className="text-xs text-dark-300">
                        {formatTimestamp(entry.started_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                {t('common.previous', { defaultValue: 'Previous' })}
              </Button>
              <span className="text-xs text-dark-300">
                {page} / {totalPages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                {t('common.next', { defaultValue: 'Next' })}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
