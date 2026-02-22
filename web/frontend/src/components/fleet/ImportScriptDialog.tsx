/**
 * ImportScriptDialog — Import scripts from GitHub URL or repository.
 *
 * Two tabs:
 * 1. "URL" — paste a direct URL to a .sh file, preview, configure, import
 * 2. "Repository" — paste a GitHub repo URL, browse .sh files, select, bulk import
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Link,
  FolderGit2,
  Eye,
  Search,
  Loader2,
  AlertTriangle,
  FileCode,
} from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import {
  importScriptFromUrl,
  browseGithubRepo,
  bulkImportScripts,
  type RepoFileItem,
  type ImportUrlRequest,
} from '@/api/fleet'
import client from '@/api/client'

const CATEGORIES = ['security', 'network', 'system', 'monitoring', 'custom'] as const

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/\.sh$/, '')
    .replace(/[^a-z0-9_\s-]/g, '')
    .replace(/[\s-]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

interface ImportScriptDialogProps {
  open: boolean
  onClose: () => void
}

export default function ImportScriptDialog({ open, onClose }: ImportScriptDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  // ── URL tab state ──
  const [fileUrl, setFileUrl] = useState('')
  const [preview, setPreview] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [urlForm, setUrlForm] = useState({
    name: '',
    display_name: '',
    description: '',
    category: 'custom',
    timeout_seconds: '60',
    requires_root: false,
  })

  // ── Repo tab state ──
  const [repoUrl, setRepoUrl] = useState('')
  const [repoFiles, setRepoFiles] = useState<RepoFileItem[]>([])
  const [repoName, setRepoName] = useState('')
  const [repoTruncated, setRepoTruncated] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set())
  const [bulkCategory, setBulkCategory] = useState('custom')
  const [bulkTimeout, setBulkTimeout] = useState('60')
  const [bulkRequiresRoot, setBulkRequiresRoot] = useState(false)

  // ── Preview ──
  const handlePreview = async () => {
    if (!fileUrl.trim()) return
    setPreviewLoading(true)
    setPreview(null)
    try {
      // Normalize github.com URLs to raw
      let url = fileUrl.trim()
      const match = url.match(/https?:\/\/github\.com\/([^/]+)\/([^/]+)\/blob\/(.+)/)
      if (match) {
        url = `https://raw.githubusercontent.com/${match[1]}/${match[2]}/${match[3]}`
      }
      const { data } = await client.get('/fleet/scripts/preview-url', {
        params: { url },
      }).catch(() => {
        // Fallback: fetch via import-url won't work for preview, try raw fetch
        return { data: null }
      })
      if (data) {
        setPreview(data.content)
      } else {
        // Try direct fetch as text
        const resp = await fetch(url)
        if (resp.ok) {
          setPreview(await resp.text())
        } else {
          toast.error(t('fleet.scripts.downloadError'))
        }
      }
      // Auto-fill name from URL
      const filename = url.split('/').pop() || 'script.sh'
      const baseName = filename.replace(/\.sh$/, '')
      if (!urlForm.display_name) {
        setUrlForm((prev) => ({
          ...prev,
          display_name: baseName,
          name: slugify(baseName),
        }))
      }
    } catch {
      toast.error(t('fleet.scripts.downloadError'))
    } finally {
      setPreviewLoading(false)
    }
  }

  // ── Import single URL ──
  const importUrlMutation = useMutation({
    mutationFn: () => {
      const body: ImportUrlRequest = {
        url: fileUrl.trim(),
        name: urlForm.name || slugify(urlForm.display_name),
        display_name: urlForm.display_name,
        description: urlForm.description || undefined,
        category: urlForm.category,
        timeout_seconds: parseInt(urlForm.timeout_seconds) || 60,
        requires_root: urlForm.requires_root,
      }
      return importScriptFromUrl(body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-scripts'] })
      toast.success(t('fleet.scripts.imported'))
      onClose()
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : String(err))
    },
  })

  // ── Browse repo ──
  const browseMutation = useMutation({
    mutationFn: () => browseGithubRepo(repoUrl.trim()),
    onSuccess: (data) => {
      setRepoFiles(data.files)
      setRepoName(data.repo)
      setRepoTruncated(data.truncated)
      setSelectedFiles(new Set())
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : String(err))
    },
  })

  // ── Bulk import ──
  const bulkMutation = useMutation({
    mutationFn: () => {
      const files: ImportUrlRequest[] = repoFiles
        .filter((f) => selectedFiles.has(f.path))
        .map((f) => ({
          url: f.download_url,
          name: slugify(f.name),
          display_name: f.name.replace(/\.sh$/, ''),
          category: bulkCategory,
          timeout_seconds: parseInt(bulkTimeout) || 60,
          requires_root: bulkRequiresRoot,
        }))
      return bulkImportScripts(files)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['fleet-scripts'] })
      if (data.errors.length > 0) {
        toast.warning(`${t('fleet.scripts.bulkImported', { count: data.imported })}. ${data.errors.length} errors.`)
      } else {
        toast.success(t('fleet.scripts.bulkImported', { count: data.imported }))
      }
      onClose()
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : String(err))
    },
  })

  const toggleFile = (path: string) => {
    setSelectedFiles((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedFiles.size === repoFiles.length) {
      setSelectedFiles(new Set())
    } else {
      setSelectedFiles(new Set(repoFiles.map((f) => f.path)))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('fleet.scripts.importFromGithub')}</DialogTitle>
          <DialogDescription>
            {t('fleet.scripts.importDescription')}
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="url" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="url" className="flex-1 gap-1.5 text-xs">
              <Link className="w-3.5 h-3.5" />
              {t('fleet.scripts.importFromUrl')}
            </TabsTrigger>
            <TabsTrigger value="repo" className="flex-1 gap-1.5 text-xs">
              <FolderGit2 className="w-3.5 h-3.5" />
              {t('fleet.scripts.importFromRepo')}
            </TabsTrigger>
          </TabsList>

          {/* ── Tab: Import from URL ── */}
          <TabsContent value="url" className="space-y-4 mt-4">
            <div>
              <Label>{t('fleet.scripts.importUrl')}</Label>
              <div className="flex gap-2 mt-1.5">
                <Input
                  value={fileUrl}
                  onChange={(e) => setFileUrl(e.target.value)}
                  placeholder="https://raw.githubusercontent.com/user/repo/main/script.sh"
                  className="flex-1"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handlePreview}
                  disabled={!fileUrl.trim() || previewLoading}
                  className="gap-1"
                >
                  {previewLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eye className="w-3.5 h-3.5" />}
                  {t('fleet.scripts.preview')}
                </Button>
              </div>
              <p className="text-xs text-dark-300 mt-1">{t('fleet.scripts.importUrlHint')}</p>
            </div>

            {preview && (
              <div>
                <Label>{t('fleet.scripts.preview')}</Label>
                <pre className="mt-1.5 p-3 bg-dark-800 border border-dark-400/20 rounded-md text-xs font-mono text-dark-100 max-h-[200px] overflow-auto whitespace-pre-wrap">
                  {preview.slice(0, 5000)}
                  {preview.length > 5000 && '\n... (truncated)'}
                </pre>
              </div>
            )}

            <div>
              <Label>{t('fleet.scripts.formDisplayName')} *</Label>
              <Input
                value={urlForm.display_name}
                onChange={(e) => {
                  const val = e.target.value
                  setUrlForm((prev) => ({ ...prev, display_name: val, name: slugify(val) }))
                }}
                placeholder="My Script"
                className="mt-1.5"
              />
            </div>

            <div>
              <Label>{t('fleet.scripts.formDescription')}</Label>
              <Input
                value={urlForm.description}
                onChange={(e) => setUrlForm({ ...urlForm, description: e.target.value })}
                className="mt-1.5"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('fleet.scripts.formCategory')}</Label>
                <select
                  value={urlForm.category}
                  onChange={(e) => setUrlForm({ ...urlForm, category: e.target.value })}
                  className="flex h-10 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-2 text-sm text-dark-50 mt-1.5"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>{t('fleet.scripts.formTimeout')}</Label>
                <Input
                  type="number"
                  min="1"
                  max="3600"
                  value={urlForm.timeout_seconds}
                  onChange={(e) => setUrlForm({ ...urlForm, timeout_seconds: e.target.value })}
                  className="mt-1.5"
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Switch
                checked={urlForm.requires_root}
                onCheckedChange={(v) => setUrlForm({ ...urlForm, requires_root: v })}
              />
              <Label>{t('fleet.scripts.formRequiresRoot')}</Label>
            </div>

            <DialogFooter>
              <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
              <Button
                onClick={() => importUrlMutation.mutate()}
                disabled={importUrlMutation.isPending || !urlForm.display_name.trim() || !fileUrl.trim()}
              >
                {importUrlMutation.isPending ? t('fleet.scripts.importing') : t('fleet.scripts.import')}
              </Button>
            </DialogFooter>
          </TabsContent>

          {/* ── Tab: Browse Repository ── */}
          <TabsContent value="repo" className="space-y-4 mt-4">
            <div>
              <Label>{t('fleet.scripts.repoUrl')}</Label>
              <div className="flex gap-2 mt-1.5">
                <Input
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/user/repo"
                  className="flex-1"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => browseMutation.mutate()}
                  disabled={!repoUrl.trim() || browseMutation.isPending}
                  className="gap-1"
                >
                  {browseMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                  {t('fleet.scripts.browseRepo')}
                </Button>
              </div>
              <p className="text-xs text-dark-300 mt-1">{t('fleet.scripts.repoUrlHint')}</p>
            </div>

            {repoTruncated && (
              <div className="flex items-center gap-2 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded-md">
                <AlertTriangle className="w-4 h-4 text-yellow-400 shrink-0" />
                <p className="text-xs text-yellow-300">{t('fleet.scripts.truncatedWarning')}</p>
              </div>
            )}

            {repoFiles.length > 0 && (
              <>
                <div className="flex items-center justify-between">
                  <p className="text-sm text-dark-200">
                    {repoName} — {repoFiles.length} .sh {repoFiles.length === 1 ? 'file' : 'files'}
                  </p>
                  <Button variant="ghost" size="sm" className="text-xs h-7" onClick={toggleAll}>
                    {selectedFiles.size === repoFiles.length ? t('common.deselectAll') : t('common.selectAll')}
                  </Button>
                </div>

                <div className="border border-dark-400/20 rounded-md max-h-[250px] overflow-y-auto divide-y divide-dark-400/10">
                  {repoFiles.map((file) => (
                    <label
                      key={file.path}
                      className="flex items-center gap-3 px-3 py-2 hover:bg-dark-700/30 cursor-pointer"
                    >
                      <Checkbox
                        checked={selectedFiles.has(file.path)}
                        onCheckedChange={() => toggleFile(file.path)}
                      />
                      <FileCode className="w-4 h-4 text-dark-300 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-dark-100 truncate">{file.path}</p>
                      </div>
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 shrink-0">
                        {formatBytes(file.size)}
                      </Badge>
                    </label>
                  ))}
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <Label className="text-xs">{t('fleet.scripts.categoryForAll')}</Label>
                    <select
                      value={bulkCategory}
                      onChange={(e) => setBulkCategory(e.target.value)}
                      className="flex h-9 w-full rounded-md border border-dark-400/20 bg-dark-800 px-3 py-1 text-sm text-dark-50 mt-1"
                    >
                      {CATEGORIES.map((cat) => (
                        <option key={cat} value={cat}>{cat}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">{t('fleet.scripts.timeoutForAll')}</Label>
                    <Input
                      type="number"
                      min="1"
                      max="3600"
                      value={bulkTimeout}
                      onChange={(e) => setBulkTimeout(e.target.value)}
                      className="mt-1 h-9"
                    />
                  </div>
                  <div className="flex items-end pb-1">
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={bulkRequiresRoot}
                        onCheckedChange={setBulkRequiresRoot}
                      />
                      <Label className="text-xs">root</Label>
                    </div>
                  </div>
                </div>
              </>
            )}

            {repoFiles.length === 0 && browseMutation.isSuccess && (
              <div className="p-6 text-center">
                <p className="text-dark-300 text-sm">{t('fleet.scripts.noShFiles')}</p>
              </div>
            )}

            <DialogFooter>
              <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
              <Button
                onClick={() => bulkMutation.mutate()}
                disabled={bulkMutation.isPending || selectedFiles.size === 0}
              >
                {bulkMutation.isPending
                  ? t('fleet.scripts.importing')
                  : `${t('fleet.scripts.importSelected')} (${selectedFiles.size})`}
              </Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
