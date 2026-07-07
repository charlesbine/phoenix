<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMatrixStore } from '@/stores/matrix'
import { api } from '@/api/client'
import type { Health } from '@/api/types'
import MatrixPreview from '@/components/MatrixPreview.vue'
import BrightnessSlider from '@/components/BrightnessSlider.vue'
import AppRow from '@/components/AppRow.vue'

const store = useMatrixStore()
const { rotation, config, nowPlaying, nowPlayingLive, online, tick, note, previewApp, selectedApp, following } =
  storeToRefs(store)

const showDisabled = ref(false)
const health = ref<Health | null>(null)
const healthError = ref<string | null>(null)
let healthTimer: number | null = null
const visibleRotation = computed(() =>
  showDisabled.value ? rotation.value : rotation.value.filter((a) => a.enabled),
)
const previewLive = computed(() => selectedApp.value?.is_live ?? (following.value && nowPlayingLive.value))
const healthStatus = computed(() => health.value?.status ?? (healthError.value ? 'offline' : 'checking'))
const healthIssues = computed(() => health.value?.issues ?? (healthError.value ? [healthError.value] : []))
const m4Connected = computed(() => Boolean(health.value?.m4?.connected))
const mqttConnected = computed(() => Boolean(health.value?.mqtt?.connected))
const load1m = computed(() => health.value?.load?.['1m'])
const memoryUsed = computed(() => health.value?.memory?.used_pct)

async function refreshHealth(): Promise<void> {
  try {
    health.value = await api.health()
    healthError.value = null
  } catch (e) {
    healthError.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(() => {
  void store.refresh()
  store.connect()
  void refreshHealth()
  healthTimer = window.setInterval(() => void refreshHealth(), 60_000)
})
onUnmounted(() => {
  store.disconnect()
  if (healthTimer !== null) window.clearInterval(healthTimer)
})

</script>

<template>
  <div>
    <div class="grid gap-5 md:grid-cols-2">
      <!-- stage -->
      <section>
        <MatrixPreview
          :app="previewApp"
          :tick="tick"
          :device="store.activeDevice"
          :live="previewLive"
          @render="previewApp && store.render(previewApp)"
        />

        <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] uppercase tracking-wider">
          <span class="text-dim">Preview <b class="text-gold">{{ previewApp ?? '—' }}</b></span>
          <span class="flex items-center gap-1.5 text-dim">
            <span class="h-2 w-2 rounded-full" :class="online ? 'bg-flame blink' : 'bg-[#7a4a34]'" style="box-shadow: 0 0 9px #ff6a2a"></span>
            live <b class="text-gold">{{ nowPlaying ?? '—' }}</b>
          </span>
          <button v-if="!following" class="text-flame hover:text-gold" @click="store.followLive()">◉ follow live</button>
        </div>

        <p v-if="note" class="mt-1 font-mono text-[10px] text-[#c78a5a]">{{ note }}</p>

        <div v-if="selectedApp" class="mt-3 flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-wider">
          <button class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009]" @click="store.showNow(selectedApp.name)">▷ show on display</button>
          <button class="rounded border border-[#3a2016] px-2.5 py-1 text-dim hover:bg-[#251009] hover:text-gold" @click="store.render(selectedApp.name)">⟳ render</button>
          <div class="flex items-center gap-1.5 text-dim">
            <span>weight</span>
            <button class="px-1 text-gold hover:text-core" @click="store.setPriority(selectedApp.name, selectedApp.priority - 1)">−</button>
            <span class="text-gold">×{{ selectedApp.priority + 1 }}</span>
            <button class="px-1 text-gold hover:text-core" @click="store.setPriority(selectedApp.name, selectedApp.priority + 1)">+</button>
          </div>
          <button class="ml-auto rounded px-2.5 py-1" :class="selectedApp.enabled ? 'text-flame' : 'text-[#7a4a34]'" @click="store.toggle(selectedApp)">
            {{ selectedApp.enabled ? 'enabled' : 'disabled' }}
          </button>
        </div>
      </section>

      <!-- rotation -->
      <section class="flex flex-col gap-4">
        <div class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 flex items-center justify-between gap-3 font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>System · {{ healthStatus }}</span>
            <button class="text-gold hover:text-core" @click="refreshHealth">Refresh</button>
          </div>

          <div class="grid grid-cols-3 gap-2 font-mono text-[10px] uppercase tracking-[0.16em]">
            <div class="rounded border border-[#24121c] px-2 py-1.5">
              <div class="flex items-center gap-1.5 text-dim">
                <span class="h-2 w-2 rounded-full" :class="m4Connected ? 'bg-flame' : 'bg-[#7a4a34]'"></span>
                M4
              </div>
              <div class="mt-1 truncate text-gold">{{ health?.m4?.port ?? '—' }}</div>
            </div>
            <div class="rounded border border-[#24121c] px-2 py-1.5">
              <div class="flex items-center gap-1.5 text-dim">
                <span class="h-2 w-2 rounded-full" :class="mqttConnected ? 'bg-flame' : 'bg-[#7a4a34]'"></span>
                MQTT
              </div>
              <div class="mt-1 truncate text-gold">{{ health?.mqtt?.broker ?? '—' }}</div>
            </div>
            <div class="rounded border border-[#24121c] px-2 py-1.5">
              <div class="text-dim">Load</div>
              <div class="mt-1 truncate text-gold">
                {{ load1m ?? '—' }}<span v-if="memoryUsed !== undefined" class="text-dim"> · {{ memoryUsed }}%</span>
              </div>
            </div>
          </div>

          <div v-if="healthIssues.length" class="mt-3 space-y-1 border-t border-[#1c0e14] pt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-[#c78a5a]">
            <div v-for="issue in healthIssues" :key="issue">{{ issue }}</div>
          </div>
        </div>

        <BrightnessSlider v-if="config" :value="config.brightness" @commit="store.setBrightness" />
        <div>
          <div class="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>Rotation · {{ rotation.length }}</span>
            <div class="flex items-center gap-3">
              <button class="hover:text-gold" :class="showDisabled ? 'text-gold' : ''" @click="showDisabled = !showDisabled">
                {{ showDisabled ? '− hide disabled' : '+ show disabled' }}
              </button>
              <span>on {{ rotation.filter((a) => a.enabled).length }}</span>
            </div>
          </div>
          <ul class="rounded border border-[#3a2016]">
            <AppRow
              v-for="a in visibleRotation"
              :key="a.name"
              :app="a"
              :selected="a.name === previewApp"
              :playing="a.name === nowPlaying"
              @select="store.select(a.name)"
              @show="store.showNow(a.name)"
              @toggle="store.toggle(a)"
            />
          </ul>
          <p v-if="!rotation.length && online" class="mt-2 px-1 font-mono text-[11px] text-dim">No apps registered yet.</p>
        </div>
      </section>
    </div>
  </div>
</template>
