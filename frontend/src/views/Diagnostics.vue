<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/api/client'
import type { CacheEntry, Health, LogLines, NotificationItem, Stats } from '@/api/types'
import { formatUnhealthySummary, groupUnhealthyApps, type UnhealthyGroup } from '@/utils/health'

const health = ref<Health | null>(null)
const stats = ref<Stats | null>(null)
const logs = ref<LogLines>({ lines: [] })
const notifications = ref<NotificationItem[]>([])
const cacheEntries = ref<CacheEntry[]>([])
const lines = ref(150)
const notifyText = ref('')
const notifyColor = ref('#ffffff')
const notifyDuration = ref(10)
const error = ref<string | null>(null)
const loading = ref(false)
const notifying = ref(false)
let timer: number | null = null

const renderTimes = computed(() =>
  Object.entries(stats.value?.render_times ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12),
)
const issues = computed(() => health.value?.issues ?? [])
const unhealthyApps = computed(() => health.value?.unhealthy_apps ?? [])
const unhealthyGroups = computed(() => groupUnhealthyApps(unhealthyApps.value))
const unhealthySummary = computed(() => formatUnhealthySummary(unhealthyApps.value))
const hasActiveUnhealthy = computed(() => unhealthyApps.value.some((a) => !a.skipped_unhealthy))
const expandedGroups = ref<Record<string, boolean>>({})
const defaultExpandGroups = computed(() => unhealthyApps.value.length <= 3)
const hasExpandableGroups = computed(() => unhealthyGroups.value.some((g) => g.apps.length > 1))
const allGroupsExpanded = computed(() =>
  unhealthyGroups.value
    .filter((g) => g.apps.length > 1)
    .every((g) => isGroupExpanded(g)),
)

function isGroupExpanded(group: UnhealthyGroup): boolean {
  if (group.apps.length <= 1) return false
  return expandedGroups.value[group.key] ?? defaultExpandGroups.value
}

function toggleGroup(key: string): void {
  const current = expandedGroups.value[key] ?? defaultExpandGroups.value
  expandedGroups.value = { ...expandedGroups.value, [key]: !current }
}

function toggleAllGroups(): void {
  const nextState = !allGroupsExpanded.value
  const updated: Record<string, boolean> = {}
  for (const g of unhealthyGroups.value) {
    if (g.apps.length > 1) updated[g.key] = nextState
  }
  expandedGroups.value = updated
}
const cacheSummary = computed(() => {
  const entries = cacheEntries.value
  const fresh = entries.filter((entry) => entry.fresh).length
  const bytes = entries.reduce((sum, entry) => sum + entry.size_bytes, 0)
  return { fresh, total: entries.length, bytes }
})

function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatNotificationTime(seconds: number): string {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function displayCacheUrl(raw: string): string {
  try {
    const url = new URL(raw)
    for (const key of [...url.searchParams.keys()]) {
      if (/(api[_-]?key|token|auth|signature|secret|password|cache)/i.test(key)) {
        url.searchParams.set(key, 'redacted')
      }
    }
    return url.toString()
  } catch {
    return raw.replace(/([?&][^=]*(?:token|key|auth|signature|secret|password|cache)[^=]*=)[^&]+/gi, '$1redacted')
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [h, s, l, n, c] = await Promise.all([
      api.health(),
      api.stats(),
      api.logs(lines.value),
      api.notifications(),
      api.cacheStats(),
    ])
    health.value = h
    stats.value = s
    logs.value = l
    notifications.value = n
    cacheEntries.value = c
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function sendNotification(): Promise<void> {
  const text = notifyText.value.trim()
  if (!text) return
  notifying.value = true
  error.value = null
  try {
    const result = await api.notify({
      text,
      color: notifyColor.value,
      duration: notifyDuration.value,
      layout: 'marquee',
    })
    if (result.error) {
      error.value = result.error
      return
    }
    notifyText.value = ''
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    notifying.value = false
  }
}

onMounted(() => {
  void load()
  timer = window.setInterval(() => void load(), 30_000)
})
onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer)
})
</script>

<template>
  <div>
    <div class="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="mb-1 text-[11px] uppercase tracking-[0.22em] text-ember">Diagnostics</p>
        <h2 class="text-xl font-bold text-core">Status &amp; logs</h2>
      </div>
      <div class="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider">
        <input
          v-model.number="lines"
          type="number"
          min="20"
          max="1000"
          step="10"
          class="w-20 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1 text-xs text-gold focus:border-flame focus:outline-none"
          @keyup.enter="load"
        />
        <span class="text-dim">lines</span>
        <button class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009]" @click="load">
          {{ loading ? 'Loading' : 'Refresh' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="mb-3 text-[11px] text-[#ff6a4a]">{{ error }}</p>

    <div class="grid gap-5 lg:grid-cols-[24rem_1fr]">
      <section class="space-y-4">
        <div class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>System</span>
            <span :class="health?.status === 'ok' ? 'text-flame' : 'text-[#c78a5a]'">{{ health?.status ?? 'checking' }}</span>
          </div>

          <div class="grid gap-2 font-mono text-[10px] uppercase tracking-[0.16em]">
            <div v-if="health?.player" class="flex items-center justify-between gap-2 rounded border border-[#24121c] px-2 py-1.5">
              <span class="text-dim">{{ health.player.name }}</span>
              <span class="truncate text-gold">{{ health.player.status }}</span>
            </div>
            <div v-else-if="health?.m4" class="flex items-center justify-between rounded border border-[#24121c] px-2 py-1.5">
              <span class="text-dim">M4</span>
              <span class="truncate text-gold">{{ health?.m4?.connected ? 'connected' : health?.m4?.port ?? 'missing' }}</span>
            </div>
            <div class="flex items-center justify-between rounded border border-[#24121c] px-2 py-1.5">
              <span class="text-dim">MQTT</span>
              <span class="truncate text-gold">{{ health?.mqtt?.broker ? (health.mqtt.connected ? health.mqtt.broker : 'disconnected') : 'not configured' }}</span>
            </div>
            <div class="flex items-center justify-between rounded border border-[#24121c] px-2 py-1.5">
              <span class="text-dim">Load</span>
              <span class="text-gold">{{ stats?.load?.['1m'] ?? health?.load?.['1m'] ?? '-' }}</span>
            </div>
          </div>

          <div
            v-if="issues.length"
            class="mt-3 space-y-1 border-t border-[#24121c] pt-2.5 font-mono text-[11px] text-[#e6a45c]"
          >
            <div v-for="issue in issues" :key="issue" class="flex items-center gap-2">
              <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-[#ff6a4a]"></span>
              <span class="truncate" :title="issue">{{ issue }}</span>
            </div>
          </div>
        </div>

        <div
          class="rounded border p-3"
          :class="unhealthyApps.length ? 'border-[#5c1f1c] bg-[#16090e]' : 'border-[#3a2016] bg-panel'"
        >
          <div class="mb-3 flex items-center justify-between gap-2 font-mono text-[10px]">
            <div class="flex min-w-0 items-center gap-2">
              <span
                class="h-1.5 w-1.5 shrink-0 rounded-full"
                :class="!unhealthyApps.length ? 'bg-flame' : hasActiveUnhealthy ? 'bg-[#ff5a2a]' : 'bg-[#d98a3c]'"
              ></span>
              <span class="uppercase tracking-[0.18em] text-dim">Data ingress</span>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <span :class="!unhealthyApps.length ? 'uppercase tracking-[0.16em] text-flame' : 'text-[#e6a45c]'">
                {{ unhealthyApps.length ? unhealthySummary : 'healthy' }}
              </span>
              <button
                v-if="hasExpandableGroups"
                class="text-dim hover:text-gold"
                @click="toggleAllGroups"
              >
                {{ allGroupsExpanded ? 'Collapse ▾' : 'Expand ▸' }}
              </button>
            </div>
          </div>

          <div
            v-if="unhealthyApps.length"
            class="divide-y divide-[#221118] rounded border border-[#3a1a1c] bg-[#11070c]"
          >
            <div v-for="group in unhealthyGroups" :key="group.key">
              <!-- Single-app group -->
              <div
                v-if="group.apps.length === 1"
                class="px-2.5 py-2 font-mono text-[11px]"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="truncate text-gold">{{ group.apps[0].app.name }}</span>
                  <span
                    class="shrink-0 rounded border px-1.5 py-0.5 text-[9px] tracking-wide"
                    :class="
                      group.apps[0].app.skipped_unhealthy
                        ? 'border-[#6b3c1e] bg-[#21120a] text-[#e6a45c]'
                        : 'border-[#8f241c] bg-[#260b0f] text-[#ff7b5c]'
                    "
                  >
                    {{ group.apps[0].app.skipped_unhealthy ? 'skipped' : 'in cycle' }}
                  </span>
                </div>
                <p class="mt-1 truncate text-[10px] text-core/85" :title="group.apps[0].app.reason || group.title">
                  {{ group.apps[0].app.reason || group.title }}
                </p>
                <p
                  class="mt-0.5 text-[10px] text-muted"
                  :title="group.apps[0].app.last_healthy ?? undefined"
                >
                  Last healthy: {{ group.apps[0].app.last_healthy_human || 'never' }}
                </p>
              </div>

              <!-- Multi-app group -->
              <template v-else>
                <button
                  type="button"
                  class="flex w-full items-center gap-2 px-2.5 py-2 text-left font-mono text-[11px] transition-colors hover:bg-[#1b0b12]"
                  :title="`${group.title} (${group.inlineNames})`"
                  @click="toggleGroup(group.key)"
                >
                  <span class="w-2.5 shrink-0 text-[9px] text-dim">
                    {{ isGroupExpanded(group) ? '▾' : '▸' }}
                  </span>
                  <span class="min-w-0 flex-1 truncate text-core/90">{{ group.title }}</span>
                  <span
                    class="max-w-[8.5rem] shrink-0 truncate text-[10px] text-muted"
                    :title="group.inlineNames"
                  >
                    {{ group.apps.length <= 2 ? group.inlineNames : group.countLabel }}
                  </span>
                  <span
                    class="shrink-0 rounded border px-1.5 py-0.5 text-[9px] tracking-wide"
                    :class="
                      group.statusKind === 'skipped'
                        ? 'border-[#6b3c1e] bg-[#21120a] text-[#e6a45c]'
                        : group.statusKind === 'active'
                          ? 'border-[#8f241c] bg-[#260b0f] text-[#ff7b5c]'
                          : 'border-[#6b3c1e] bg-[#21120a] text-[#ff9e6a]'
                    "
                  >
                    {{
                      group.statusKind === 'skipped'
                        ? 'skipped'
                        : group.statusKind === 'active'
                          ? 'in cycle'
                          : `${group.skippedCount}/${group.apps.length} skip`
                    }}
                  </span>
                </button>

                <div
                  v-if="isGroupExpanded(group)"
                  class="space-y-1 border-t border-[#1e0f15] bg-[#0d060a] py-1.5 pl-6 pr-2.5 font-mono text-[10px]"
                >
                  <div
                    v-for="entry in group.apps"
                    :key="entry.app.name"
                    class="rounded px-1.5 py-1 hover:bg-[#190a11]"
                    :title="`${entry.app.reason || group.title} · Last healthy: ${entry.app.last_healthy_human || 'never'}`"
                  >
                    <div class="flex items-center gap-2">
                      <span class="shrink-0 text-gold">{{ entry.app.name }}</span>
                      <span v-if="entry.detail" class="min-w-0 flex-1 truncate text-muted">
                        {{ entry.detail }}
                      </span>
                      <span v-else class="flex-1"></span>
                      <span
                        class="shrink-0 text-[9px]"
                        :class="entry.app.skipped_unhealthy ? 'text-[#c78a5a]' : 'text-[#ff7b5c]'"
                      >
                        {{ entry.app.skipped_unhealthy ? 'skipped' : 'in cycle' }}
                      </span>
                    </div>
                    <div class="mt-0.5 text-[9px] text-dim">
                      Last healthy: {{ entry.app.last_healthy_human || 'never' }}
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
          <div v-else class="text-[11px] uppercase tracking-widest text-dim">All active data sources healthy</div>
        </div>

        <div class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 text-[10px] uppercase tracking-[0.18em] text-dim">Render timing</div>
          <div v-if="renderTimes.length" class="space-y-1 font-mono text-[10px] uppercase tracking-[0.14em]">
            <div v-for="[name, seconds] in renderTimes" :key="name" class="grid grid-cols-[minmax(0,1fr)_auto] gap-3">
              <span class="truncate text-gold">{{ name }}</span>
              <span class="text-dim">{{ seconds.toFixed(2) }}s</span>
            </div>
          </div>
          <div v-else class="text-[11px] uppercase tracking-widest text-dim">No render timings</div>
        </div>

        <div class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>Notification queue</span>
            <span>{{ notifications.length }}</span>
          </div>

          <form class="grid gap-2" @submit.prevent="sendNotification">
            <input
              v-model="notifyText"
              type="text"
              placeholder="Message"
              class="rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
            />
            <div class="grid grid-cols-[3rem_1fr_auto] gap-2">
              <input
                v-model="notifyColor"
                type="color"
                class="h-8 w-12 rounded border border-[#3a2016] bg-[#120a10] p-0.5"
              />
              <input
                v-model.number="notifyDuration"
                type="number"
                min="1"
                max="120"
                class="rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
              />
              <button
                type="submit"
                :disabled="notifying || !notifyText.trim()"
                class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009] disabled:opacity-40"
              >
                {{ notifying ? 'Sending' : 'Send' }}
              </button>
            </div>
          </form>

          <div v-if="notifications.length" class="mt-3 space-y-1 border-t border-[#1c0e14] pt-2 font-mono text-[10px] uppercase tracking-[0.14em]">
            <div v-for="note in notifications.slice(0, 5)" :key="note.id" class="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-2">
              <span :class="note.displayed ? 'text-dim' : 'text-flame'">{{ note.displayed ? 'done' : 'queued' }}</span>
              <span class="truncate text-gold">{{ note.text }}</span>
              <span class="text-dim">{{ formatNotificationTime(note.created_at) }}</span>
            </div>
          </div>
          <div v-else class="mt-3 text-[11px] uppercase tracking-widest text-dim">No notifications</div>
        </div>

        <div class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>HTTP cache</span>
            <span>{{ cacheSummary.fresh }}/{{ cacheSummary.total }} fresh · {{ formatBytes(cacheSummary.bytes) }}</span>
          </div>

          <div v-if="cacheEntries.length" class="space-y-1 font-mono text-[10px] uppercase tracking-[0.14em]">
            <div v-for="entry in cacheEntries.slice(0, 8)" :key="entry.url" class="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-2">
              <span :class="entry.fresh ? 'text-flame' : 'text-[#c78a5a]'">{{ entry.fresh ? 'fresh' : 'stale' }}</span>
              <span class="truncate text-gold">{{ displayCacheUrl(entry.url) }}</span>
              <span class="text-dim">{{ formatAge(entry.age_seconds) }}</span>
            </div>
          </div>
          <div v-else class="text-[11px] uppercase tracking-widest text-dim">No cached HTTP responses</div>
        </div>
      </section>

      <section class="min-w-0 rounded border border-[#3a2016] bg-[#0b0609]">
        <div class="border-b border-[#1c0e14] px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
          Recent logs
        </div>
        <pre class="max-h-[36rem] overflow-auto whitespace-pre-wrap break-words p-3 font-mono text-[10px] leading-relaxed text-[#c78a5a]">{{ logs.lines.join('\n') || 'No logs' }}</pre>
      </section>
    </div>
  </div>
</template>
