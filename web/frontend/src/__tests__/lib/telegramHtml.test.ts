import { describe, expect, it } from 'vitest'
import {
  EMAIL_STYLE,
  escapeRawCharacters,
  telegramMarkupIssues,
  telegramPreviewTree,
  telegramToEmailHtml,
} from '@/lib/telegramHtml'

// Те же случаи, что в web/backend/tests/test_notice_markup.py: редактор обязан
// ругаться ровно на то, на что ругается бэкенд при сохранении.
const codes = (text: string) => telegramMarkupIssues(text).map((issue) => issue.code)
const letter = (inner: string) => `<div style="${EMAIL_STYLE}">${inner}</div>`

describe('telegramMarkupIssues', () => {
  it('passes everything Telegram supports', () => {
    const text = [
      '<b>жирный</b> <strong>жирный</strong> <i>курсив</i> <em>курсив</em>',
      '<u>подчёркнутый</u> <ins>x</ins> <s>зачёркнутый</s> <strike>x</strike> <del>x</del>',
      '<tg-spoiler>спойлер</tg-spoiler> <span class="tg-spoiler">спойлер</span>',
      '<a href="https://stijoin.com/rules">правила</a> <code>код</code>',
      '<pre><code class="language-python">print(1)</code></pre>',
      '<blockquote expandable>цитата</blockquote>',
      '<tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>',
      '&lt; &gt; &amp; &quot; &#169; &#x1F600;',
    ].join('\n')
    expect(codes(text)).toEqual([])
    expect(codes('<b>жирный <i>и курсив <u>и подчёркнутый</u></i></b>')).toEqual([])
  })

  it('requires special characters to be escaped', () => {
    expect(codes('Скидка 50% & бонус')).toEqual(['raw_amp'])
    expect(codes('если a < b')).toEqual(['raw_lt'])
    expect(codes('стрелка ->')).toEqual(['raw_gt'])
    expect(telegramMarkupIssues('пробел&nbsp;тут')[0]).toMatchObject({ code: 'unknown_entity', params: { entity: '&nbsp;' } })
  })

  it('explains that line breaks are newlines', () => {
    expect(codes('строка<br>строка')).toEqual(['line_break'])
    expect(codes('<p>абзац</p>')).toEqual(['line_break', 'line_break'])
    expect(codes('<h1>заголовок</h1>')).toEqual(['unknown_tag', 'unknown_tag'])
  })

  it('catches unclosed and crossed tags', () => {
    expect(codes('<b>жирный без конца')).toEqual(['unclosed'])
    expect(codes('лишний </b>')).toEqual(['unexpected_close'])
    expect(codes('<b><i>крест</b></i>')).toEqual(['mismatched', 'unexpected_close'])
    expect(codes('<b/>')).toEqual(['self_closing'])
  })

  it('checks attributes and nesting', () => {
    expect(codes('<a>без адреса</a>')).toEqual(['missing_attr'])
    expect(codes('<b class="x">жирный</b>')).toEqual(['bad_attr'])
    expect(codes('<span>просто span</span>')).toEqual(['missing_attr'])
    expect(codes('<code class="language-python">вне pre</code>')).toEqual(['bad_attr'])
    expect(codes('<a href="https://a.io"><a href="https://b.io">x</a></a>')).toEqual(['nested_link'])
    expect(codes('<blockquote><blockquote>x</blockquote></blockquote>')).toEqual(['nested_quote'])
    expect(codes('<code><b>x</b></code>')).toEqual(['inside_code'])
  })

  it('points at the exact place', () => {
    const text = 'первая строка\nвторая & третья'
    const issue = telegramMarkupIssues(text)[0]
    expect(text.slice(issue.from, issue.to)).toBe('&')
  })
})

describe('escapeRawCharacters', () => {
  it('escapes only stray characters and keeps markup', () => {
    expect(escapeRawCharacters('<b>50% & бонус</b> -> a < b &amp;')).toBe('<b>50% &amp; бонус</b> -&gt; a &lt; b &amp;')
  })
})

describe('telegramToEmailHtml', () => {
  it('matches the letter the backend sends', () => {
    expect(telegramToEmailHtml('Здравствуйте!\n<b>Важно</b>: <tg-spoiler>тайна</tg-spoiler>')).toBe(
      letter('Здравствуйте!<br>\n<b>Важно</b>: <span>тайна</span>'),
    )
    expect(telegramToEmailHtml('<pre>a\nb</pre>')).toBe(letter('<pre>a\nb</pre>'))
    expect(telegramToEmailHtml('A & B < C')).toBe(letter('A &amp; B &lt; C'))
  })

  it('translates Telegram-only tags', () => {
    const html = telegramToEmailHtml('<blockquote expandable>цитата</blockquote><tg-emoji emoji-id="1">👍</tg-emoji>')
    expect(html).toContain('<blockquote style=')
    expect(html).not.toContain('expandable')
    expect(html).not.toContain('tg-emoji')
    expect(html).toContain('👍')
  })
})

describe('telegramPreviewTree', () => {
  it('builds nested elements and decodes entities', () => {
    expect(telegramPreviewTree('<b>A &amp; <i>B</i></b>')).toEqual([
      {
        type: 'element', tag: 'b', attrs: {}, children: [
          { type: 'text', text: 'A ' },
          { type: 'text', text: '&' },
          { type: 'text', text: ' ' },
          { type: 'element', tag: 'i', attrs: {}, children: [{ type: 'text', text: 'B' }] },
        ],
      },
    ])
  })

  it('shows unsupported tags as typed', () => {
    expect(telegramPreviewTree('a<br>b')).toEqual([
      { type: 'text', text: 'a' },
      { type: 'text', text: '<br>' },
      { type: 'text', text: 'b' },
    ])
  })
})
