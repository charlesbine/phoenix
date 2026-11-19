<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/api/client'
import type { CacheEntry, Health, LogLines, NotificationItem, Stats } from '@/api/types'

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

          <div v-if="issues.length" class="mt-3 space-y-1 border-t border-[#1c0e14] pt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-[#c78a5a]">
            <div v-for="issue in issues" :key="issue">{{ issue }}</div>
          </div>
        </div>

        <div
          class="rounded border p-3"
          :class="unhealthyApps.length ? 'border-[#b3241a] bg-[#1e0a0e]' : 'border-[#3a2016] bg-panel'"
        >
          <div class="mb-3 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>Data ingress</span>
            <span :class="unhealthyApps.length ? 'text-[#ff6a4a]' : 'text-flame'">
              {{ unhealthyApps.length ? `${unhealthyApps.length} down` : 'healthy' }}
            </span>
          </div>

          <div v-if="unhealthyApps.length" class="space-y-2 font-mono text-[10px]">
            <div
              v-for="item in unhealthyApps"
              :key="item.name"
              class="rounded border border-[#b3241a]/60 bg-[#14070b] px-2 py-1.5"
            >
              <div class="flex items-center justify-between gap-2 uppercase tracking-[0.14em]">
                <span class="truncate text-[#ff8a6a]">{{ item.name }}</span>
                <span class="shrink-0 text-[9px] text-[#ff6a4a]">
                  {{ item.skipped_unhealthy ? 'skipped' : 'in cycle' }}
                </span>
              </div>
              <p class="mt-1 text-core">{{ item.reason || 'Data source unavailable or empty.' }}</p>
              <p
                class="mt-0.5 uppercase tracking-[0.12em] text-muted"
                :title="item.last_healthy ?? undefined"
              >
                Last healthy: {{ item.last_healthy_human || 'never' }}
              </p>
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
