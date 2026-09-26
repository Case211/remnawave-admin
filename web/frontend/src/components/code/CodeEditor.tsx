/**
 * CodeEditor — редактор кода в стиле панели (CodeMirror 6): JSON, YAML, HTML.
 *
 * Валидация JSON: синтаксис + JSON-схема xray (ajv), автокомплит ключей по схеме
 * и официальных протоколов Xray (xtls.github.io/en/config/). HTML — подсветка
 * и перенос длинных строк; проверку под свою задачу даёт вызывающий (`lint`).
 */
import { useEffect, useMemo, useRef } from 'react'
import { EditorState, Extension } from '@codemirror/state'
import {
  EditorView, keymap, drawSelection, highlightActiveLine, dropCursor,
  highlightSpecialChars, lineNumbers, highlightActiveLineGutter, placeholder as placeholderText,
} from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import {
  indentOnInput, bracketMatching, foldGutter, foldKeymap,
  syntaxHighlighting, defaultHighlightStyle, syntaxTree,
} from '@codemirror/language'
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search'
import {
  autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap,
  CompletionContext, CompletionResult,
} from '@codemirror/autocomplete'
import { lintKeymap, linter, lintGutter, forEachDiagnostic, Diagnostic } from '@codemirror/lint'
import { json, jsonLanguage, jsonParseLinter } from '@codemirror/lang-json'
import { yaml } from '@codemirror/lang-yaml'
import { html } from '@codemirror/lang-html'
import { oneDark } from '@codemirror/theme-one-dark'
import Ajv, { ValidateFunction } from 'ajv'
import i18n from '@/i18n'
import xraySchema from './xray.schema.json'
import { lintXray } from './xray.semantics'

const ajv = new Ajv({ allErrors: true, strict: false })

// Официальные протоколы Xray (xtls.github.io/en/config/, включая 25.x: hysteria/tun)
const INBOUND_PROTOCOLS = ['dokodemo-door', 'http', 'shadowsocks', 'socks', 'trojan', 'vless', 'vmess', 'wireguard', 'hysteria', 'tun']
const OUTBOUND_PROTOCOLS = ['blackhole', 'dns', 'freedom', 'http', 'loopback', 'shadowsocks', 'socks', 'trojan', 'vless', 'vmess', 'wireguard', 'hysteria']

export type CodeEditorSchema = 'xray' | 'json' | 'yaml' | 'html' | 'none'

interface CodeEditorProps {
  value: string
  onChange: (value: string) => void
  readOnly?: boolean
  schema?: CodeEditorSchema
  className?: string
  /** ошибки (блокируют сохранение) и подсказки-advisory (не блокируют) */
  onDiagnostics?: (errors: number, hints: number) => void
  /** доступ к EditorView (навигация по секциям и т.п.) */
  viewRef?: React.MutableRefObject<EditorView | null>
  /** своя проверка текста (сейчас — для schema="html"); severity error блокирует сохранение */
  lint?: (doc: string) => Diagnostic[]
  /** подсказка в пустом редакторе */
  placeholder?: string
}

/** Тема под Glassmorphism панели: прозрачный фон, наши переменные. */
const panelTheme = EditorView.theme({
  '&': { height: '100%', backgroundColor: 'transparent', fontSize: '13px' },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': {
    fontFamily: "'JetBrains Mono', monospace",
    overflow: 'auto',
    scrollbarWidth: 'thin',
  },
  '.cm-content': { caretColor: 'var(--primary-400, #4FE0C6)' },
  '.cm-gutters': {
    backgroundColor: 'transparent',
    color: 'rgba(148, 163, 184, 0.5)',
    border: 'none',
  },
  '.cm-activeLineGutter': { backgroundColor: 'rgba(255,255,255,0.04)' },
  '.cm-activeLine': { backgroundColor: 'rgba(255,255,255,0.03)' },
  '.cm-tooltip': {
    backgroundColor: 'var(--glass-bg, #0f172a)',
    border: '1px solid var(--glass-border, #334155)',
    borderRadius: '8px',
  },
  '.cm-tooltip-autocomplete > ul > li[aria-selected]': {
    backgroundColor: 'rgba(79, 224, 198, 0.15)',
    color: 'white',
  },
})

function schemaFor(schema: CodeEditorSchema): object | null {
  if (schema === 'xray') return xraySchema as object
  return null
}

/** Позиция подсветки по подстроке-якорю (пропуская `skip` первых вхождений). */
function locate(doc: string, anchor?: string, skip = 0): { from: number; to: number } {
  if (!anchor) return { from: 0, to: 0 }
  let idx = -1
  for (let n = 0; n <= skip; n++) {
    idx = doc.indexOf(anchor, idx + 1)
    if (idx < 0) break
  }
  if (idx < 0) return { from: 0, to: 0 }
  return { from: idx, to: idx + anchor.length }
}

/**
 * Линтер: синтаксис (jsonParseLinter, точная позиция) → схема (ajv, warning)
 * → семантика xray (severity info — advisory, НЕ блокирует сохранение).
 */
function makeLinter(validate: ValidateFunction | null, isXray: boolean) {
  const syntax = jsonParseLinter()
  return linter((view) => {
    const doc = view.state.doc.toString()
    if (!doc.trim()) return []
    const syntaxErrors = syntax(view)
    if (syntaxErrors.length) return syntaxErrors
    let parsed: unknown
    try {
      parsed = JSON.parse(doc)
    } catch {
      return [] // синтаксис уже отловлен выше
    }
    const diagnostics: Diagnostic[] = []
    if (validate && !validate(parsed) && validate.errors) {
      for (const err of validate.errors.slice(0, 20)) {
        // позиционируем ошибку на ключе из instancePath, если найдём
        const seg = err.instancePath.split('/').filter(Boolean).pop()
        let from = 0
        let to = 0
        if (seg && !/^\d+$/.test(seg)) {
          const idx = doc.indexOf(`"${seg}"`)
          if (idx >= 0) { from = idx; to = idx + seg.length + 2 }
        }
        diagnostics.push({
          from, to, severity: 'warning',
          message: `${err.instancePath || '/'} ${err.message || ''}`.trim(),
        })
      }
    }
    if (isXray) {
      for (const issue of lintXray(parsed).slice(0, 30)) {
        const { from, to } = locate(doc, issue.anchor, issue.anchorSkip)
        diagnostics.push({
          from, to, severity: 'info', source: 'xray',
          message: String(i18n.t(`resources.editor.lint.${issue.code}`, issue.params ?? {})),
        })
      }
    }
    return diagnostics
  })
}

/**
 * Контекстный автокомплит по JSON-схеме xray.
 *
 * Путь курсора определяется по синтаксическому дереву (Property/Array вверх),
 * затем резолвится в узел схемы: в позиции ключа — свойства ЭТОЙ секции
 * (с описаниями, без уже существующих соседей), в позиции значения —
 * enum-варианты / true/false / официальные протоколы.
 */
function makeCompletion(schema: object | null): Extension | null {
  if (!schema) return null
  const definitions: Record<string, any> = (schema as any).definitions || {}
  const deref = (s: any): any => {
    let node = s
    for (let i = 0; i < 5 && node?.$ref; i++) {
      node = definitions[String(node.$ref).split('/').pop() || '']
    }
    return node
  }

  /** Путь контейнера курсора: имена родительских свойств, массивы — '*'. */
  const pathAt = (context: CompletionContext): string[] => {
    const path: string[] = []
    try {
      let node: any = syntaxTree(context.state).resolveInner(context.pos, -1)
      while (node) {
        if (node.name === 'Property') {
          const nameNode = node.getChild('PropertyName')
          // свойство входит в путь, только если курсор ЗА его именем (в значении)
          if (nameNode && context.pos > nameNode.to) {
            path.unshift(context.state.sliceDoc(nameNode.from + 1, nameNode.to - 1))
          }
        } else if (node.name === 'Array') {
          path.unshift('*')
        }
        node = node.parent
      }
    } catch { /* частично невалидный JSON — вернём что собрали */ }
    return path
  }

  const schemaNodeAt = (path: string[]): any => {
    let node: any = deref(schema)
    for (const seg of path) {
      node = deref(node)
      if (!node) return null
      node = seg === '*' ? deref(node.items) : deref((node.properties || {})[seg])
    }
    return deref(node)
  }

  /** Уже существующие ключи объекта вокруг курсора — их не предлагаем. */
  const siblingKeys = (context: CompletionContext): Set<string> => {
    const keys = new Set<string>()
    try {
      let node: any = syntaxTree(context.state).resolveInner(context.pos, -1)
      while (node && node.name !== 'Object') node = node.parent
      if (node) {
        for (let ch = node.firstChild; ch; ch = ch.nextSibling) {
          if (ch.name === 'Property') {
            const nameNode = ch.getChild('PropertyName')
            if (nameNode) keys.add(context.state.sliceDoc(nameNode.from + 1, nameNode.to - 1))
          }
        }
      }
    } catch { /* ignore */ }
    return keys
  }

  const typeLabel = (s: any): string => {
    if (!s) return ''
    if (s.enum) return s.enum.slice(0, 4).join('|') + (s.enum.length > 4 ? '|…' : '')
    if (s.$ref) return String(s.$ref).split('/').pop() || ''
    if (s.type === 'array') return `${typeLabel(s.items) || 'array'}[]`
    return s.type || ''
  }

  return jsonLanguage.data.of({
    autocomplete: (context: CompletionContext): CompletionResult | null => {
      const word = context.matchBefore(/[\w"./-]*/)
      if (!word || (word.from === word.to && !context.explicit)) return null
      const line = context.state.doc.lineAt(context.pos)
      const beforeCursor = context.state.sliceDoc(line.from, context.pos)
      const inValue = /:\s*"?[\w./-]*$/.test(beforeCursor)
      const path = pathAt(context)

      if (inValue) {
        // значение: имя поля = последний сегмент пути
        const field = path[path.length - 1]
        if (field === 'protocol') {
          const list = path.includes('inbounds') ? INBOUND_PROTOCOLS : OUTBOUND_PROTOCOLS
          return {
            from: word.from,
            options: list.map((p) => ({ label: `"${p}"`, type: 'keyword', detail: 'protocol' })),
          }
        }
        const fieldSchema = schemaNodeAt(path)
        if (fieldSchema?.enum) {
          return {
            from: word.from,
            options: fieldSchema.enum.map((v: unknown) => ({
              label: typeof v === 'string' ? `"${v}"` : String(v), type: 'keyword', detail: 'enum',
            })),
          }
        }
        if (fieldSchema?.type === 'boolean') {
          return {
            from: word.from,
            options: [{ label: 'true', type: 'keyword' }, { label: 'false', type: 'keyword' }],
          }
        }
        return null
      }

      // ключ: свойства секции, в которой стоит курсор
      const container = schemaNodeAt(path)
      const props: Record<string, any> = container?.properties || {}
      const names = Object.keys(props)
      if (!names.length) return null
      const existing = siblingKeys(context)
      return {
        from: word.from,
        options: names
          .filter((k) => !existing.has(k))
          .map((k) => ({
            label: `"${k}"`,
            type: 'property',
            apply: `"${k}": `,
            detail: typeLabel(props[k]),
            info: props[k]?.description,
          })),
      }
    },
  })
}

export function CodeEditor({ value, onChange, readOnly = false, schema = 'json', className, onDiagnostics, viewRef: externalViewRef, lint, placeholder }: CodeEditorProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<EditorView | null>(null)
  const onChangeRef = useRef(onChange)
  const onDiagRef = useRef(onDiagnostics)
  const lintRef = useRef(lint)
  const lastErr = useRef(-1)
  const lastHint = useRef(-1)
  onChangeRef.current = onChange
  onDiagRef.current = onDiagnostics
  lintRef.current = lint

  const jsonSchema = useMemo(() => schemaFor(schema), [schema])
  const validate = useMemo(
    () => (jsonSchema ? ajv.compile(jsonSchema) : null),
    [jsonSchema],
  )

  useEffect(() => {
    if (!parentRef.current) return

    const reportDiagnostics = EditorView.updateListener.of((update) => {
      if (update.docChanged) onChangeRef.current(update.state.doc.toString())
      // счётчики для индикаторов (линтер приходит отдельной транзакцией):
      // ошибки+схема (блокируют сохранение) отдельно от advisory-подсказок
      if (onDiagRef.current) {
        let errors = 0
        let hints = 0
        forEachDiagnostic(update.state, (d) => {
          if (d.severity === 'info' || d.severity === 'hint') hints++
          else errors++
        })
        if (errors !== lastErr.current || hints !== lastHint.current) {
          lastErr.current = errors
          lastHint.current = hints
          onDiagRef.current(errors, hints)
        }
      }
    })

    const extensions: Extension[] = [
      lineNumbers(),
      highlightActiveLineGutter(),
      highlightSpecialChars(),
      history(),
      foldGutter(),
      drawSelection(),
      dropCursor(),
      indentOnInput(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      bracketMatching(),
      closeBrackets(),
      highlightActiveLine(),
      highlightSelectionMatches(),
      keymap.of([
        ...closeBracketsKeymap, ...defaultKeymap, ...searchKeymap,
        ...historyKeymap, ...foldKeymap, ...completionKeymap, ...lintKeymap,
        indentWithTab,
      ]),
      oneDark,
      panelTheme,
      reportDiagnostics,
      EditorView.editable.of(!readOnly),
      EditorState.readOnly.of(readOnly),
    ]
    if (placeholder) extensions.push(placeholderText(placeholder))

    if (schema === 'yaml') {
      extensions.push(yaml())
    } else if (schema === 'html') {
      extensions.push(html(), EditorView.lineWrapping)
      if (lintRef.current) {
        extensions.push(lintGutter(), linter((view) => lintRef.current?.(view.state.doc.toString()) ?? [], { delay: 200 }))
      }
    } else if (schema !== 'none') {
      extensions.push(json(), lintGutter(), makeLinter(validate, schema === 'xray'))
      extensions.push(autocompletion({ activateOnTyping: true, icons: true }))
      const completion = makeCompletion(jsonSchema)
      if (completion) extensions.push(completion)
    }

    const view = new EditorView({
      state: EditorState.create({ doc: value, extensions }),
      parent: parentRef.current,
    })
    viewRef.current = view
    if (externalViewRef) externalViewRef.current = view
    return () => {
      view.destroy()
      if (externalViewRef) externalViewRef.current = null
    }
    // пересоздание только при смене схемы/readOnly — value синхронится ниже
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema, readOnly, validate, jsonSchema, placeholder])

  // внешнее обновление value (история версий, формат)
  useEffect(() => {
    const view = viewRef.current
    if (view && value !== view.state.doc.toString()) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } })
    }
  }, [value])

  return (
    <div
      ref={parentRef}
      className={
        'h-full w-full overflow-hidden rounded-lg border border-[var(--glass-border)] bg-[var(--glass-bg)] ' +
        (className || '')
      }
    />
  )
}
