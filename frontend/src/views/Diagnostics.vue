<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '@/api/client'
import type { Health, LogLines, Stats } from '@/api/types'

const health = ref<Health | null>(null)
const stats = ref<Stats | null>(null)
const logs = ref<LogLines>({ lines: [] })
const lines = ref(150)
const error = ref<string | null>(null)
const loading = ref(false)
let timer: number | null = null

const renderTimes = computed(() =>
  Object.entries(stats.value?.render_times ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12),
)
const issues = computed(() => health.value?.issues ?? [])

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [h, s, l] = await Promise.all([api.health(), api.stats(), api.logs(lines.value)])
    health.value = h
    stats.value = s
    logs.value = l
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
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
            <div class="flex items-center justify-between rounded border border-[#24121c] px-2 py-1.5">
              <span class="text-dim">M4</span>
              <span class="truncate text-gold">{{ health?.m4?.connected ? 'connected' : health?.m4?.port ?? 'missing' }}</span>
            </div>
            <div class="flex items-center justify-between rounded border border-[#24121c] px-2 py-1.5">
              <span class="text-dim">MQTT</span>
              <span class="truncate text-gold">{{ health?.mqtt?.connected ? health?.mqtt?.broker ?? 'connected' : 'disconnected' }}</span>
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
