// Timeline: what happened on the matter, newest first, grouped by day, in plain words (CONTRACTS §7).
import type { EngineInterface } from 'claude-code'
import type { Card, TimelineEvent } from '../../types'
import type { Ctx } from '../kit'
import { clock, dateOnly, nowMs } from '../words'
import { ACCENT_TEXT } from '../theme'

const WHO: Record<string, string> = { attorney: 'You', claude: 'Claude', app: '' }

// The day a line belongs to, as a heading: "Today", "Yesterday", "October 27, 2026".
function dayOf(iso: string, now: number): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return 'Earlier'
  const today = new Date(now)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === new Date(now - 86400000).toDateString()) return 'Yesterday'
  return dateOnly(iso)
}

export function timelineDays(events: TimelineEvent[], now: number): { day: string; events: TimelineEvent[] }[] {
  const sorted = [...events].filter(e => e && typeof e.text === 'string' && e.text.trim()).sort((a, b) => (b.at ?? '').localeCompare(a.at ?? ''))
  const days: { day: string; events: TimelineEvent[] }[] = []
  for (const e of sorted) {
    const day = dayOf(e.at, now)
    const last = days[days.length - 1]
    if (last && last.day === day) last.events.push(e)
    else days.push({ day, events: [e] })
  }
  return days
}

export async function timelineScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, card, section, rule, matterPage } = x
  const days = timelineDays(c.timeline, nowMs())
  return matterPage(c, 'timeline',
    days.length === 0
      ? card(null, [<Text key="none" dimColor>Nothing is recorded yet. From now on, what you and Claude do on this matter is listed here: documents added or taken out, runs started and finished, answers, and settings.</Text>])
      : null,
    ...days.map(d => section(d.day, [
      rule(`day-rule-${d.day}`),
      ...d.events.map((e, i) => (
        <Box key={`ev-${d.day}-${i}`} flexDirection="row" gap="md" alignItems="flex-start">
          <Text color={ACCENT_TEXT} weight="bold">•</Text>
          <Box flexDirection="column" flexShrink={1} minWidth={0} gap="xs">
            <Text>{WHO[e.actor] ? `${WHO[e.actor]}: ${e.text}` : e.text}</Text>
            <Text dimColor size="caption" tabular>{clock(e.at)}</Text>
          </Box>
        </Box>
      )),
    ], `card-day-${d.day}`)),
  )
}
