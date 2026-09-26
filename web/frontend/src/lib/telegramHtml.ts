/**
 * Разметка Telegram (parse_mode=HTML): проверка, предпросмотр и письмо.
 *
 * Зеркало web/backend/core/notice_markup.py. Telegram отвергает сообщение
 * целиком из-за одной мелочи — незнакомого тега, незакрытого, голого «<» или
 * «&», — поэтому редактор подсвечивает ровно то, на чём он споткнётся (бэкенд
 * проверяет то же при сохранении). Письмо из текста Telegram собирается так же,
 * как на бэкенде: предпросмотр совпадает с тем, что уйдёт клиенту.
 */

export type MarkupIssueCode =
  | 'raw_lt' | 'raw_gt' | 'raw_amp' | 'unknown_entity'
  | 'unknown_tag' | 'line_break' | 'self_closing'
  | 'bad_attr' | 'missing_attr'
  | 'mismatched' | 'unexpected_close' | 'unclosed'
  | 'inside_code' | 'nested_link' | 'nested_quote'

export interface MarkupIssue {
  code: MarkupIssueCode
  from: number
  to: number
  params: Record<string, string>
}

export type PreviewNode =
  | { type: 'text'; text: string }
  | { type: 'element'; tag: string; attrs: Record<string, string | null>; children: PreviewNode[] }

type RawCode = 'raw_lt' | 'raw_gt' | 'raw_amp' | 'unknown_entity'

interface Token {
  kind: 'text' | 'entity' | 'raw' | 'tag'
  start: number
  end: number
  code?: RawCode
  name?: string
  closing?: boolean
  selfClosing?: boolean
  attrs?: string
}

const TELEGRAM_TAGS = new Set([
  'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
  'a', 'code', 'pre', 'blockquote', 'tg-spoiler', 'span', 'tg-emoji',
])
const NAMED_ENTITIES: Record<string, string> = { lt: '<', gt: '>', amp: '&', quot: '"' }
// Переносы в Telegram — обычные переводы строк; эти теги путают чаще прочих
const LINE_BREAK_TAGS = new Set(['br', 'p', 'div'])

const TAG_RE = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[a-zA-Z][a-zA-Z0-9-]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*)\s*(\/?)>/y
const ATTR_RE = /([a-zA-Z][a-zA-Z0-9-]*)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?/g
const ENTITY_RE = /&(#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);/y

const RAW_ESCAPES: Record<string, string> = { raw_lt: '&lt;', raw_gt: '&gt;', raw_amp: '&amp;' }

export const EMAIL_STYLE = "font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;font-size:15px;line-height:1.55;color:#1f2328"
const EMAIL_QUOTE_STYLE = 'margin:0;padding-left:12px;border-left:3px solid #d0d7de;color:#57606a'

/** Разбор на куски текста, сущности, теги и одиночные спецсимволы. */
function scan(text: string): Token[] {
  const tokens: Token[] = []
  let i = 0
  let textStart = 0
  while (i < text.length) {
    const ch = text[i]
    if (ch !== '<' && ch !== '&' && ch !== '>') {
      i++
      continue
    }
    if (i > textStart) tokens.push({ kind: 'text', start: textStart, end: i })
    if (ch === '<') {
      TAG_RE.lastIndex = i
      const m = TAG_RE.exec(text)
      if (m) {
        tokens.push({
          kind: 'tag', start: i, end: i + m[0].length, name: m[2].toLowerCase(),
          closing: m[1] === '/', selfClosing: m[4] === '/', attrs: m[3],
        })
        i += m[0].length
      } else {
        tokens.push({ kind: 'raw', start: i, end: i + 1, code: 'raw_lt' })
        i++
      }
    } else if (ch === '&') {
      ENTITY_RE.lastIndex = i
      const m = ENTITY_RE.exec(text)
      if (m && (m[1].startsWith('#') || m[1] in NAMED_ENTITIES)) {
        tokens.push({ kind: 'entity', start: i, end: i + m[0].length })
        i += m[0].length
      } else if (m) {
        tokens.push({ kind: 'raw', start: i, end: i + m[0].length, code: 'unknown_entity' })
        i += m[0].length
      } else {
        tokens.push({ kind: 'raw', start: i, end: i + 1, code: 'raw_amp' })
        i++
      }
    } else {
      tokens.push({ kind: 'raw', start: i, end: i + 1, code: 'raw_gt' })
      i++
    }
    textStart = i
  }
  if (textStart < text.length) tokens.push({ kind: 'text', start: textStart, end: text.length })
  return tokens
}

function parseAttrs(raw = ''): Record<string, string | null> {
  const attrs: Record<string, string | null> = {}
  for (const m of raw.matchAll(ATTR_RE)) {
    let value: string | null = m[2] ?? null
    if (value && (value[0] === '"' || value[0] === "'")) value = value.slice(1, -1)
    attrs[m[1].toLowerCase()] = value
  }
  return attrs
}

function decodeEntity(raw: string): string {
  const body = raw.slice(1, -1)
  if (body[0] !== '#') return NAMED_ENTITIES[body] ?? raw
  const code = body[1] === 'x' || body[1] === 'X' ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10)
  try {
    return String.fromCodePoint(code)
  } catch {
    return raw
  }
}

/** Что не так с открывающим тегом: атрибуты и вложенность. */
function openTagIssues(tok: Token, stack: Token[]): MarkupIssue[] {
  const issues: MarkupIssue[] = []
  const issue = (code: MarkupIssueCode, params: Record<string, string> = {}) =>
    issues.push({ code, from: tok.start, to: tok.end, params })

  const name = tok.name!
  const parent = stack.length ? stack[stack.length - 1].name : undefined
  if (parent === 'code' || (parent === 'pre' && name !== 'code')) issue('inside_code', { tag: name, parent: parent! })
  if (name === 'a' && stack.some((t) => t.name === 'a')) issue('nested_link')
  if (name === 'blockquote' && stack.some((t) => t.name === 'blockquote')) issue('nested_quote')

  const attrs = parseAttrs(tok.attrs)
  const allowed: Record<string, string[]> = {
    a: ['href'], span: ['class'], 'tg-emoji': ['emoji-id'],
    code: parent === 'pre' ? ['class'] : [], blockquote: ['expandable'],
  }
  for (const attr of Object.keys(attrs)) {
    if (!(allowed[name] ?? []).includes(attr)) issue('bad_attr', { tag: name, attr })
  }

  if (name === 'a' && !(attrs.href ?? '').trim()) issue('missing_attr', { tag: 'a', attr: 'href' })
  else if (name === 'span' && attrs.class !== 'tg-spoiler') issue('missing_attr', { tag: 'span', attr: 'class="tg-spoiler"' })
  else if (name === 'tg-emoji' && !/^\d+$/.test(attrs['emoji-id'] ?? '')) issue('missing_attr', { tag: 'tg-emoji', attr: 'emoji-id' })
  else if (name === 'code' && 'class' in attrs && !(attrs.class ?? '').startsWith('language-')) issue('bad_attr', { tag: 'code', attr: 'class' })
  return issues
}

/** Всё, из-за чего Telegram не примет текст с parse_mode=HTML. */
export function telegramMarkupIssues(text: string): MarkupIssue[] {
  const issues: MarkupIssue[] = []
  const stack: Token[] = []
  for (const tok of scan(text)) {
    if (tok.kind === 'raw') {
      const params: Record<string, string> = tok.code === 'unknown_entity' ? { entity: text.slice(tok.start, tok.end) } : {}
      issues.push({ code: tok.code!, from: tok.start, to: tok.end, params })
      continue
    }
    if (tok.kind !== 'tag') continue
    const name = tok.name!
    if (!TELEGRAM_TAGS.has(name)) {
      issues.push({ code: LINE_BREAK_TAGS.has(name) ? 'line_break' : 'unknown_tag', from: tok.start, to: tok.end, params: { tag: name } })
      continue
    }
    if (tok.closing) {
      if (stack.length && stack[stack.length - 1].name === name) {
        stack.pop()
      } else if (stack.some((t) => t.name === name)) {
        // Закрыли внешний тег раньше внутреннего — снимаем незакрытые
        issues.push({ code: 'mismatched', from: tok.start, to: tok.end, params: { tag: name, expected: stack[stack.length - 1].name! } })
        while (stack[stack.length - 1].name !== name) stack.pop()
        stack.pop()
      } else {
        issues.push({ code: 'unexpected_close', from: tok.start, to: tok.end, params: { tag: name } })
      }
      continue
    }
    if (tok.selfClosing) {
      issues.push({ code: 'self_closing', from: tok.start, to: tok.end, params: { tag: name } })
      continue
    }
    issues.push(...openTagIssues(tok, stack))
    stack.push(tok)
  }
  for (const t of stack) issues.push({ code: 'unclosed', from: t.start, to: t.end, params: { tag: t.name! } })
  return issues.sort((a, b) => a.from - b.from)
}

/** Правка «заменить спецсимволы»: голые <, > и & → сущности. */
export function escapeRawCharacters(text: string): string {
  return scan(text)
    .map((tok) => {
      const raw = text.slice(tok.start, tok.end)
      return tok.kind === 'raw' ? RAW_ESCAPES[tok.code!] ?? raw : raw
    })
    .join('')
}

/**
 * Дерево для предпросмотра в «пузыре» Telegram. Строится и из текста с
 * ошибками: незнакомые теги и лишние символы показываются как есть.
 */
export function telegramPreviewTree(text: string): PreviewNode[] {
  const root: PreviewNode[] = []
  const stack: { tag: string; children: PreviewNode[] }[] = []
  const children = () => (stack.length ? stack[stack.length - 1].children : root)

  for (const tok of scan(text)) {
    const raw = text.slice(tok.start, tok.end)
    if (tok.kind === 'text' || tok.kind === 'raw') {
      children().push({ type: 'text', text: raw })
    } else if (tok.kind === 'entity') {
      children().push({ type: 'text', text: decodeEntity(raw) })
    } else if (!TELEGRAM_TAGS.has(tok.name!) || tok.selfClosing) {
      children().push({ type: 'text', text: raw })
    } else if (tok.closing) {
      const at = stack.map((s) => s.tag).lastIndexOf(tok.name!)
      if (at >= 0) stack.length = at
      else children().push({ type: 'text', text: raw })
    } else {
      const node: PreviewNode = { type: 'element', tag: tok.name!, attrs: parseAttrs(tok.attrs), children: [] }
      children().push(node)
      stack.push({ tag: tok.name!, children: node.children })
    }
  }
  return root
}

function emailTag(tok: Token, raw: string): string {
  if (tok.name === 'tg-emoji') return '' // вместо кастомного эмодзи — запасной, он внутри тега
  if (tok.name === 'tg-spoiler' || tok.name === 'span') return tok.closing ? '</span>' : '<span>'
  if (tok.name === 'blockquote') return tok.closing ? '</blockquote>' : `<blockquote style="${EMAIL_QUOTE_STYLE}">`
  return raw
}

/** Письмо из текста Telegram: переводы строк → <br>, свои теги Telegram → HTML. */
export function telegramToEmailHtml(text: string): string {
  const parts: string[] = []
  let inPre = 0
  for (const tok of scan(text)) {
    const raw = text.slice(tok.start, tok.end)
    if (tok.kind === 'text') {
      parts.push(inPre ? raw : raw.split('\n').join('<br>\n'))
    } else if (tok.kind === 'raw') {
      parts.push(RAW_ESCAPES[tok.code!] ?? raw)
    } else if (tok.kind === 'tag') {
      if (tok.name === 'pre') inPre = Math.max(inPre + (tok.closing ? -1 : 1), 0)
      parts.push(emailTag(tok, raw))
    } else {
      parts.push(raw)
    }
  }
  return `<div style="${EMAIL_STYLE}">${parts.join('')}</div>`
}
