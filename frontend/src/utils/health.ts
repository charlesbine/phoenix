import type { UnhealthyAppSummary } from '@/api/types'

export interface UnhealthyAppEntry {
  app: UnhealthyAppSummary
  detail: string
}

export interface UnhealthyGroup {
  key: string
  title: string
  apps: UnhealthyAppEntry[]
  skippedCount: number
  activeCount: number
  countLabel: string
  inlineNames: string
  statusKind: 'skipped' | 'active' | 'mixed'
}

const HTTP_FROM_RE = /^(HTTP\s+\d{3})\s+from\s+([^/\s:]+(?::\d+)?)(\/[^\s]*)?(?:\s+(.*))?$/i
const HOST_ERR_RE =
  /^(Fetch failed|Timeout|Timed out|Connection error|Invalid JSON|Empty response)\s+(?:for|from)\s+([^/\s:]+(?::\d+)?)(\/[^\s:]*)?(?::\s*(.*))?$/i

export function parseUnhealthyReason(raw: string): { key: string; title: string; detail: string } {
  const reason = (raw || '').trim()
  if (!reason) {
    return {
      key: 'reason:unavailable',
      title: 'Data source unavailable',
      detail: '',
    }
  }

  const httpMatch = reason.match(HTTP_FROM_RE)
  if (httpMatch) {
    const status = httpMatch[1].replace(/\s+/g, ' ').toUpperCase()
    const host = httpMatch[2]
    const path = httpMatch[3] ?? ''
    const extra = (httpMatch[4] ?? '').trim()
    const detail = [path, extra].filter(Boolean).join(' · ')
    return {
      key: `http:${host.toLowerCase()}:${status}`,
      title: `${host} · ${status}`,
      detail,
    }
  }

  const hostMatch = reason.match(HOST_ERR_RE)
  if (hostMatch) {
    const kind = hostMatch[1].trim()
    const host = hostMatch[2]
    const path = hostMatch[3] ?? ''
    const extra = (hostMatch[4] ?? '').trim()
    const detail = [path, extra].filter(Boolean).join(' · ')
    return {
      key: `host:${host.toLowerCase()}:${kind.toLowerCase()}`,
      title: `${host} · ${kind}`,
      detail,
    }
  }

  return {
    key: `reason:${reason.toLowerCase()}`,
    title: reason,
    detail: '',
  }
}

export function groupUnhealthyApps(apps: UnhealthyAppSummary[]): UnhealthyGroup[] {
  const byKey = new Map<string, { title: string; entries: UnhealthyAppEntry[] }>()

  for (const app of apps) {
    const parsed = parseUnhealthyReason(app.reason)
    const existing = byKey.get(parsed.key)
    if (existing) {
      existing.entries.push({ app, detail: parsed.detail })
    } else {
      byKey.set(parsed.key, {
        title: parsed.title,
        entries: [{ app, detail: parsed.detail }],
      })
    }
  }

  const groups: UnhealthyGroup[] = []
  for (const [key, value] of byKey.entries()) {
    const sorted = [...value.entries].sort((a, b) => a.app.name.localeCompare(b.app.name))
    const skippedCount = sorted.filter((e) => e.app.skipped_unhealthy).length
    const activeCount = sorted.length - skippedCount
    const allPanels = sorted.every((e) => e.app.name.startsWith('panel_'))
    const noun = allPanels
      ? sorted.length === 1
        ? 'panel'
        : 'panels'
      : sorted.length === 1
        ? 'app'
        : 'apps'
    const statusKind =
      skippedCount === sorted.length ? 'skipped' : activeCount === sorted.length ? 'active' : 'mixed'

    groups.push({
      key,
      title: value.title,
      apps: sorted,
      skippedCount,
      activeCount,
      countLabel: `${sorted.length} ${noun}`,
      inlineNames: sorted.map((e) => e.app.name).join(', '),
      statusKind,
    })
  }

  groups.sort((a, b) => b.apps.length - a.apps.length || a.title.localeCompare(b.title))
  return groups
}

export function formatUnhealthySummary(apps: UnhealthyAppSummary[]): string {
  const total = apps.length
  if (total === 0) return ''
  const skipped = apps.filter((a) => a.skipped_unhealthy).length
  if (skipped > 0) return `${total} down · ${skipped} skipped`
  return `${total} down · in cycle`
}
