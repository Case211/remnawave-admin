/**
 * Редакторы шаблона предупреждения: текст для Telegram и письмо.
 *
 * У Telegram своя урезанная разметка и живые переносы строк, письму нужна
 * обычная вёрстка — поэтому редакторы раздельные, каждый со своим
 * предпросмотром. Ошибки разметки Telegram подсвечиваются на лету: Telegram
 * отвергает сообщение целиком, и узнать об этом надо до сохранения.
 */
import { Fragment, useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { EditorView } from '@codemirror/view'
import type { Diagnostic } from '@codemirror/lint'
import { CodeEditor } from '@/components/code/CodeEditor'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AlertTriangle, Code, EyeOff, Link, Quote } from '@/components/brand/icons'
import {
  escapeRawCharacters,
  telegramMarkupIssues,
  telegramPreviewTree,
  telegramToEmailHtml,
  type MarkupIssue,
  type PreviewNode,
} from '@/lib/telegramHtml'
import { cn } from '@/lib/utils'

// Тема письма, если своей нет, — та же, что подставляет бэкенд
const DEFAULT_SUBJECT = 'Использование подписки'
const ISSUES_SHOWN = 6
const SAFE_LINK = /^(https?:|tg:|mailto:)/i
const FIXABLE = new Set(['raw_lt', 'raw_gt', 'raw_amp'])

// ── Telegram ──

interface TelegramNoticeEditorProps {
  value: string
  onChange: (value: string) => void
  issues: MarkupIssue[]
  readOnly: boolean
}

export function TelegramNoticeEditor({ value, onChange, issues, readOnly }: TelegramNoticeEditorProps) {
  const { t } = useTranslation()
  const viewRef = useRef<EditorView | null>(null)

  const lint = useCallback(
    (doc: string): Diagnostic[] =>
      telegramMarkupIssues(doc).map((issue) => ({
        from: issue.from,
        to: issue.to,
        severity: 'error',
        message: t(`violations.notices.markup.${issue.code}`, issue.params),
      })),
    [t],
  )

  /** Обернуть выделение тегами; без выделения — поставить курсор между ними. */
  const wrap = (open: string, close: string, select?: [number, number]) => {
    const view = viewRef.current
    if (!view) return
    const { from, to } = view.state.selection.main
    const selected = view.state.sliceDoc(from, to)
    const anchor = select ? from + select[0] : from + open.length
    const head = select ? from + select[1] : anchor + selected.length
    view.dispatch({ changes: { from, to, insert: open + selected + close }, selection: { anchor, head } })
    view.focus()
  }

  const tools: { key: string; label: ReactNode; apply: () => void }[] = [
    { key: 'bold', label: <span className="font-bold">B</span>, apply: () => wrap('<b>', '</b>') },
    { key: 'italic', label: <span className="font-serif italic">I</span>, apply: () => wrap('<i>', '</i>') },
    { key: 'underline', label: <span className="underline underline-offset-2">U</span>, apply: () => wrap('<u>', '</u>') },
    { key: 'strike', label: <span className="line-through">S</span>, apply: () => wrap('<s>', '</s>') },
    { key: 'spoiler', label: <EyeOff className="h-4 w-4" aria-hidden="true" />, apply: () => wrap('<tg-spoiler>', '</tg-spoiler>') },
    { key: 'code', label: <Code className="h-4 w-4" aria-hidden="true" />, apply: () => wrap('<code>', '</code>') },
    // Ссылка: сразу выделяем адрес — его остаётся только вписать
    { key: 'link', label: <Link className="h-4 w-4" aria-hidden="true" />, apply: () => wrap('<a href="https://">', '</a>', [9, 17]) },
    { key: 'quote', label: <Quote className="h-4 w-4" aria-hidden="true" />, apply: () => wrap('<blockquote>', '</blockquote>') },
  ]

  return (
    <div className="space-y-2">
      {!readOnly && (
        <div role="toolbar" aria-label={t('violations.notices.format.toolbar')} className="flex flex-wrap gap-1">
          {tools.map((tool) => (
            <Button
              key={tool.key}
              type="button"
              variant="ghost"
              size="sm"
              title={t(`violations.notices.format.${tool.key}`)}
              aria-label={t(`violations.notices.format.${tool.key}`)}
              // Не забираем фокус у редактора — иначе пропадёт выделение
              onMouseDown={(e) => e.preventDefault()}
              onClick={tool.apply}
              className="h-9 min-w-9 px-2 text-sm text-dark-100"
            >
              {tool.label}
            </Button>
          ))}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="h-64">
          <CodeEditor
            schema="html"
            value={value}
            onChange={onChange}
            readOnly={readOnly}
            viewRef={viewRef}
            lint={lint}
            placeholder={t('violations.notices.bodyPlaceholder')}
          />
        </div>
        <TelegramBubble text={value} />
      </div>

      {issues.length > 0 && (
        <MarkupIssues
          text={value}
          issues={issues}
          onFix={readOnly ? undefined : () => onChange(escapeRawCharacters(value))}
        />
      )}
      <p className="text-xs leading-relaxed text-dark-300">{t('violations.notices.telegramHint')}</p>
    </div>
  )
}

function MarkupIssues({ text, issues, onFix }: { text: string; issues: MarkupIssue[]; onFix?: () => void }) {
  const { t } = useTranslation()
  const lineOf = (pos: number) => text.slice(0, pos).split('\n').length
  const fixable = issues.some((issue) => FIXABLE.has(issue.code))

  return (
    <div role="alert" className="space-y-1.5 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
      <div className="flex flex-wrap items-center gap-2">
        <AlertTriangle className="h-4 w-4 flex-shrink-0 text-red-300" aria-hidden="true" />
        <span className="font-medium">{t('violations.notices.issuesTitle')}</span>
        <span className="flex-1" />
        {fixable && onFix && (
          <Button type="button" variant="secondary" size="sm" onClick={onFix}>
            {t('violations.notices.fixSpecialChars')}
          </Button>
        )}
      </div>
      <ul className="space-y-0.5 pl-6">
        {issues.slice(0, ISSUES_SHOWN).map((issue) => (
          <li key={`${issue.from}-${issue.code}`}>
            <span className="text-red-300/70">{t('violations.notices.markup.line', { line: lineOf(issue.from) })}</span>{' '}
            {t(`violations.notices.markup.${issue.code}`, issue.params)}
          </li>
        ))}
        {issues.length > ISSUES_SHOWN && (
          <li className="text-red-300/70">{t('violations.notices.markup.more', { count: issues.length - ISSUES_SHOWN })}</li>
        )}
      </ul>
    </div>
  )
}

/** Пузырь сообщения в тёмной теме Telegram — цвета взяты у него, а не из темы панели. */
function TelegramBubble({ text }: { text: string }) {
  const { t } = useTranslation()
  const nodes = useMemo(() => telegramPreviewTree(text), [text])

  return (
    <div className="flex min-h-64 flex-col rounded-lg border border-[var(--glass-border)] bg-[#0e1621] p-3">
      <span className="mb-2 text-[11px] font-medium uppercase tracking-wide text-dark-300">
        {t('violations.notices.previewTelegram')}
      </span>
      <div className="max-w-[92%] self-start whitespace-pre-wrap break-words rounded-2xl rounded-bl-md bg-[#182533] px-3.5 py-2 text-sm leading-relaxed text-[#f5f5f5] shadow-md">
        {text.trim() ? renderNodes(nodes) : <span className="text-dark-300">{t('violations.notices.previewEmpty')}</span>}
      </div>
    </div>
  )
}

function renderNodes(nodes: PreviewNode[]): ReactNode[] {
  return nodes.map((node, i) => {
    if (node.type === 'text') return <Fragment key={i}>{node.text}</Fragment>
    const children = renderNodes(node.children)
    switch (node.tag) {
      case 'b':
      case 'strong':
        return <strong key={i}>{children}</strong>
      case 'i':
      case 'em':
        return <em key={i}>{children}</em>
      case 'u':
      case 'ins':
        return <u key={i}>{children}</u>
      case 's':
      case 'strike':
      case 'del':
        return <s key={i}>{children}</s>
      case 'code':
        return <code key={i} className="rounded bg-black/30 px-1 font-mono text-[0.85em] text-[#7fd1ff]">{children}</code>
      case 'pre':
        return <pre key={i} className="my-1 overflow-x-auto rounded-md bg-black/30 p-2 font-mono text-[0.85em]">{children}</pre>
      case 'blockquote':
        return <blockquote key={i} className="my-1 rounded-r-md border-l-[3px] border-[#6ab2f2] bg-[#6ab2f2]/10 py-1 pl-2">{children}</blockquote>
      case 'a': {
        const href = node.attrs.href ?? ''
        return SAFE_LINK.test(href)
          ? <a key={i} href={href} target="_blank" rel="noopener noreferrer" className="text-[#6ab2f2] hover:underline">{children}</a>
          : <span key={i} className="text-[#6ab2f2]">{children}</span>
      }
      case 'tg-spoiler':
      case 'span':
        return <Spoiler key={i}>{children}</Spoiler>
      default:
        return <Fragment key={i}>{children}</Fragment>
    }
  })
}

function Spoiler({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const [shown, setShown] = useState(false)
  return (
    <span
      role="button"
      tabIndex={0}
      aria-pressed={shown}
      aria-label={shown ? undefined : t('violations.notices.format.spoiler')}
      onClick={() => setShown((v) => !v)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          setShown((v) => !v)
        }
      }}
      className={cn('rounded-sm transition', !shown && 'cursor-pointer select-none bg-white/10 blur-[3px]')}
    >
      {children}
    </span>
  )
}

// ── Письмо ──

interface EmailNoticeEditorProps {
  subject: string
  html: string
  telegramText: string
  readOnly: boolean
  onSubject: (value: string) => void
  onHtml: (value: string) => void
}

export function EmailNoticeEditor({ subject, html, telegramText, readOnly, onSubject, onHtml }: EmailNoticeEditorProps) {
  const { t } = useTranslation()
  const own = html.trim().length > 0
  const letter = own ? html : telegramToEmailHtml(telegramText)

  return (
    <div className="space-y-2">
      <label className="block space-y-1">
        <span className="text-xs text-dark-300">{t('violations.notices.subject')}</span>
        <Input
          value={subject}
          disabled={readOnly}
          placeholder={t('violations.notices.subjectPlaceholder', { subject: DEFAULT_SUBJECT })}
          onChange={(e) => onSubject(e.target.value)}
          className="h-9"
        />
      </label>

      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          {own ? (
            <Button type="button" variant="ghost" size="sm" onClick={() => onHtml('')}>
              {t('violations.notices.useTelegramText')}
            </Button>
          ) : (
            <Button type="button" variant="secondary" size="sm" onClick={() => onHtml(telegramToEmailHtml(telegramText))}>
              {t('violations.notices.fillFromTelegram')}
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="h-72">
          <CodeEditor
            schema="html"
            value={html}
            onChange={onHtml}
            readOnly={readOnly}
            placeholder={t('violations.notices.emailPlaceholder')}
          />
        </div>
        <EmailPreview subject={subject.trim() || DEFAULT_SUBJECT} html={letter} />
      </div>
      <p className="text-xs leading-relaxed text-dark-300">
        {t(own ? 'violations.notices.emailOwnHint' : 'violations.notices.emailAutoHint')}
      </p>
    </div>
  )
}

/** Письмо в песочнице: без скриптов, форм и переходов — вёрстка оператора панель не трогает. */
function EmailPreview({ subject, html }: { subject: string; html: string }) {
  const { t } = useTranslation()
  const doc = /<html[\s>]/i.test(html) ? html : `<!doctype html><html><body style="margin:16px">${html}</body></html>`

  return (
    <div className="flex min-h-72 flex-col overflow-hidden rounded-lg border border-[var(--glass-border)]">
      <div className="border-b border-[var(--glass-border)] bg-[var(--glass-bg)] px-3 py-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-dark-300">
          {t('violations.notices.previewEmail')}
        </span>
        <div className="truncate text-sm text-dark-100">{subject}</div>
      </div>
      <iframe title={t('violations.notices.previewEmail')} sandbox="" srcDoc={doc} className="w-full flex-1 bg-white" />
    </div>
  )
}
