// The memo, the client request and Claude's reports, read on the paper: their Markdown drawn as the panel's own text, in
// paper colours (the host's Markdown takes no colour, and would turn light in a dark theme).
//
// The dialect is the one the deliverables are written in (scripts/packet/render_document.py): `#` to `###` headings,
// paragraphs, `-` bullets with one level of sub-bullets, `1.` numbered lists, `- [ ]` and `- [x]` checklist items,
// `| a | b |` tables, `>` notes, `---` rules, `**bold**`, `*italic*`, `` `code` ``, `<u>underlined</u>` and links,
// which are drawn as their words with the address after them, as the Copy button gives them.
import type { Els } from './kit'
import { ACCENT, ACCENT_TEXT, HOVER, INK, LINE, MUTED, NAVY } from './theme'

type Run = { text: string; bold?: boolean; italic?: boolean; code?: boolean; underline?: boolean }
type Block =
  | { kind: 'h1' | 'h2' | 'h3' | 'para' | 'quote'; runs: Run[] }
  | { kind: 'bullet' | 'number' | 'check'; runs: Run[]; marker: string; level: number }
  | { kind: 'rule' }
  | { kind: 'code'; text: string }
  | { kind: 'table'; rows: Run[][][]; header: boolean }

// The inline marks of a line, as runs: bold, italic, code, underline, and links as their words and address.
export function inline(source: string, base: Omit<Run, 'text'> = {}): Run[] {
  const runs: Run[] = []
  const text = source.replace(/\\([*_`|\\[\]])/g, (_m, c: string) => `\u0000${c.charCodeAt(0)}\u0000`)
  const restore = (s: string) => s.replace(/\u0000(\d+)\u0000/g, (_m, c: string) => String.fromCharCode(Number(c)))
  const push = (t: string, marks: Omit<Run, 'text'>) => {
    if (!t) return
    const last = runs[runs.length - 1]
    const same = last && Boolean(last.bold) === Boolean(marks.bold) && Boolean(last.italic) === Boolean(marks.italic) && Boolean(last.code) === Boolean(marks.code) && Boolean(last.underline) === Boolean(marks.underline)
    if (same) last.text += restore(t)
    else runs.push({ text: restore(t), ...marks })
  }
  const pattern = /(\*\*([^*]+?)\*\*|__([^_]+?)__|\*([^*\s][^*]*?)\*|(?<![A-Za-z0-9])_([^_\s][^_]*?)_(?![A-Za-z0-9])|`([^`]+)`|<u>(.+?)<\/u>|\[([^\]]+)\]\(([^)\s]+)\))/
  let rest = text
  while (rest) {
    const m = pattern.exec(rest)
    if (!m) { push(rest, base); break }
    push(rest.slice(0, m.index), base)
    if (m[2] !== undefined || m[3] !== undefined) runs.push(...inline(restore(m[2] ?? m[3] ?? ''), { ...base, bold: true }))
    else if (m[4] !== undefined || m[5] !== undefined) runs.push(...inline(restore(m[4] ?? m[5] ?? ''), { ...base, italic: true }))
    else if (m[6] !== undefined) push(m[6], { ...base, code: true })
    else if (m[7] !== undefined) runs.push(...inline(restore(m[7]), { ...base, underline: true }))
    else if (m[8] !== undefined) {
      const words = restore(m[8])
      const url = restore(m[9] ?? '')
      runs.push(...inline(words, base))
      if (url && url !== words && !url.startsWith('#')) push(` (${url})`, base)
    }
    rest = rest.slice(m.index + m[0].length)
  }
  return runs
}

const TABLE_RULE = /^:?-{3,}:?$/
function cells(line: string): string[] {
  let s = line.trim().slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1)
  return s.split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, '|'))
}

// The blocks of a document, in order.
export function parse(source: string): Block[] {
  const blocks: Block[] = []
  const para: string[] = []
  const quote: string[] = []
  let listOpen = false
  let tableOpen = false
  let fence: string[] | null = null
  const flush = () => {
    if (para.length) blocks.push({ kind: 'para', runs: inline(para.join(' ')) })
    para.length = 0
    if (quote.length) blocks.push({ kind: 'quote', runs: inline(quote.join(' ')) })
    quote.length = 0
  }
  const lines = source.replace(/\r\n/g, '\n').replace(/<!--[\s\S]*?-->/g, '').split('\n')
  for (const raw of lines) {
    const s = raw.trim()
    if (fence) {
      if (s.startsWith('```')) { blocks.push({ kind: 'code', text: fence.join('\n') }); fence = null } else fence.push(raw)
      continue
    }
    if (s.startsWith('```')) { flush(); fence = []; continue }
    const indent = raw.length - raw.trimStart().length
    if (!s) { flush(); listOpen = false; tableOpen = false; continue }
    if (s.startsWith('|')) {
      flush()
      const row = cells(s)
      const last = blocks[blocks.length - 1]
      if (!tableOpen || !last || last.kind !== 'table') { blocks.push({ kind: 'table', rows: [], header: false }); tableOpen = true }
      const table = blocks[blocks.length - 1] as Extract<Block, { kind: 'table' }>
      if (table.rows.length === 1 && !table.header && row.every(c => TABLE_RULE.test(c))) table.header = true
      else table.rows.push(row.map(c => inline(c)))
      continue
    }
    tableOpen = false
    if (s.startsWith('>')) { if (para.length) flush(); quote.push(s.replace(/^>\s?/, '')); continue }
    const h = /^(#{1,6})\s+(.*)$/.exec(s)
    const check = /^[-*+]\s+\[([ xX])\]\s+(.*)$/.exec(s)
    const bullet = /^[-*+]\s+(.*)$/.exec(s)
    const number = /^(\d{1,3})[.)]\s+(.*)$/.exec(s)
    const level = Math.min(Math.floor(indent / 2), 1)
    if (h) {
      flush()
      const n = h[1]!.length
      blocks.push({ kind: n === 1 ? 'h1' : n === 2 ? 'h2' : 'h3', runs: inline(h[2]!) })
      listOpen = false
    } else if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(s) && !/^_{3,}$/.test(s)) {
      flush()
      blocks.push({ kind: 'rule' })
    } else if (check) {
      flush()
      blocks.push({ kind: 'check', runs: inline(check[2]!), marker: check[1] === ' ' ? '☐' : '☑', level })
      listOpen = true
    } else if (bullet) {
      flush()
      blocks.push({ kind: 'bullet', runs: inline(bullet[1]!), marker: '•', level })
      listOpen = true
    } else if (number && (!para.length || number[1] === '1')) {
      flush()
      blocks.push({ kind: 'number', runs: inline(number[2]!), marker: `${number[1]}.`, level })
      listOpen = true
    } else if (listOpen && indent >= 2 && !para.length) {
      const last = blocks[blocks.length - 1]
      if (last && 'runs' in last) last.runs.push(...inline(` ${s}`))
    } else {
      if (quote.length) flush()
      listOpen = false
      para.push(s)
    }
  }
  if (fence) blocks.push({ kind: 'code', text: fence.join('\n') })
  flush()
  return blocks
}

// The document drawn: headings in navy, the text in ink, list markers and notes in muted and the accent, tables as
// aligned rows. `key` keeps two documents on one screen apart; `compact` draws a report a step smaller.
export function markdown(els: Pick<Els, 'Box' | 'Text'>, key: string, source: string, compact = false): JSX.Element {
  const { Box, Text } = els
  const size = compact ? 'footnote' as const : 'body' as const
  const runsOf = (runs: Run[], color: string, k: string) => runs.map((r, i) => (
    <Text key={`${k}-${i}`} color={color} weight={r.bold ? 'semibold' : undefined} italic={r.italic || undefined} underline={r.underline || undefined} mono={r.code || undefined} backgroundColor={r.code ? HOVER : undefined}>{r.text}</Text>
  ))
  const blocks = parse(source)
  return (
    <Box key={key} flexDirection="column" gap="sm">
      {blocks.map((bl, i) => {
        const k = `${key}-${i}`
        switch (bl.kind) {
          case 'h1':
            return <Box key={k} flexDirection="column" paddingBottom="xs"><Text size={compact ? 'heading' : 'title'} weight="semibold" color={NAVY}>{runsOf(bl.runs, NAVY, k)}</Text></Box>
          case 'h2':
            return <Box key={k} flexDirection="column" paddingTop={i ? 'md' : undefined}><Text size={compact ? 'body' : 'heading'} weight="semibold" color={NAVY}>{runsOf(bl.runs, NAVY, k)}</Text></Box>
          case 'h3':
            return <Box key={k} flexDirection="column" paddingTop={i ? 'sm' : undefined}><Text size={size} weight="semibold" color={NAVY}>{runsOf(bl.runs, NAVY, k)}</Text></Box>
          case 'para':
            return <Text key={k} size={size} color={INK}>{runsOf(bl.runs, INK, k)}</Text>
          case 'quote':
            return (
              <Box key={k} flexDirection="row" gap="md">
                <Box backgroundColor={ACCENT} paddingLeft="xs" />
                <Box flexDirection="column" flexShrink={1} paddingY="xs"><Text size={size} color={MUTED}>{runsOf(bl.runs, MUTED, k)}</Text></Box>
              </Box>
            )
          case 'bullet':
          case 'number':
          case 'check':
            return (
              <Box key={k} flexDirection="row" gap="sm" alignItems="flex-start" paddingLeft={bl.level ? 'xl' : 'sm'}>
                <Box flexDirection="row" flexShrink={0}><Text size={size} color={bl.kind === 'number' ? ACCENT_TEXT : MUTED} weight={bl.kind === 'number' ? 'semibold' : undefined} tabular>{bl.marker}</Text></Box>
                <Box flexDirection="column" flexShrink={1} flexGrow={1}><Text size={size} color={INK}>{runsOf(bl.runs, INK, k)}</Text></Box>
              </Box>
            )
          case 'rule':
            return <Box key={k} height={0} borderStyle="single" borderColor={LINE} />
          case 'code':
            return <Box key={k} flexDirection="column" backgroundColor={HOVER} paddingX="md" paddingY="sm"><Text size="footnote" mono color={INK}>{bl.text}</Text></Box>
          case 'table': {
            const width = `${Math.floor(100 / Math.max(1, ...bl.rows.map(r => r.length)))}%`
            return (
              <Box key={k} flexDirection="column">
                {bl.rows.map((row, r) => (
                  <Box key={`${k}-r${r}`} flexDirection="column">
                    <Box flexDirection="row" columnGap="md" paddingY="xs">
                      {row.map((cell, c) => (
                        <Box key={`${k}-r${r}c${c}`} flexDirection="column" width={width} flexShrink={1}>
                          <Text size={compact || bl.header && r === 0 ? 'footnote' : size} weight={bl.header && r === 0 ? 'semibold' : undefined} color={bl.header && r === 0 ? NAVY : INK}>{runsOf(cell, bl.header && r === 0 ? NAVY : INK, `${k}-r${r}c${c}`)}</Text>
                        </Box>
                      ))}
                    </Box>
                    <Box height={0} borderStyle="single" borderColor={LINE} />
                  </Box>
                ))}
              </Box>
            )
          }
        }
        return null
      })}
    </Box>
  )
}
