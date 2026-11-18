<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
import type { Device, DisplaySettings } from '@/api/types'
import DeviceBrightnessSchedule from '@/components/DeviceBrightnessSchedule.vue'
import { useMatrixStore } from '@/stores/matrix'

const store = useMatrixStore()
const devices = ref<Device[]>([])
const error = ref<string | null>(null)
const displaySettings = ref<DisplaySettings | null>(null)
const timezones = ref<string[]>([])
const settingsMessage = ref('')
const savingSettings = ref(false)

const BACKENDS: Device['backend'][] = ['web', 'serial', 'wled', 'matrix']
const LAYOUTS: Device['layout_mode'][] = ['cycle', 'random', 'single']

const draft = ref<{ id: string; name: string; backend: Device['backend'] }>({
  id: '',
  name: '',
  backend: 'wled',
})

async function load(): Promise<void> {
  try {
    const [panels, global] = await Promise.all([api.listDevices(), api.getDisplaySettings()])
    devices.value = panels
    displaySettings.value = global.settings
    timezones.value = global.timezones
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
onMounted(load)

async function saveDisplaySettings(): Promise<void> {
  if (!displaySettings.value) return
  savingSettings.value = true
  settingsMessage.value = ''
  error.value = null
  const { timezone, latitude, longitude } = displaySettings.value
  try {
    displaySettings.value = await api.setDisplaySettings({
      timezone,
      latitude: latitude === null || String(latitude) === '' ? null : latitude,
      longitude: longitude === null || String(longitude) === '' ? null : longitude,
    })
    settingsMessage.value = 'Display settings saved.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    savingSettings.value = false
  }
}

function mirrorOptions(id: string): Device[] {
  // A panel can mirror any *other* non-mirror panel (no chains/cycles).
  return devices.value.filter((d) => d.id !== id && !d.mirror_of)
}

async function patch(d: Device, patchObj: Partial<Device>): Promise<void> {
  error.value = null
  const res = await api.updateDevice(d.id, patchObj)
  if (res && 'error' in res) {
    error.value = res.error
    return
  }
  Object.assign(d, res)
  await store.loadDevices()
}

async function create(): Promise<void> {
  error.value = null
  const id = draft.value.id.trim().toLowerCase().replace(/\s+/g, '-')
  const name = draft.value.name.trim()
  if (!id || !name) {
    error.value = 'id and name are required'
    return
  }
  const res = await api.createDevice({ id, name, backend: draft.value.backend })
  if (res && 'error' in res) {
    error.value = res.error
    return
  }
  draft.value = { id: '', name: '', backend: 'wled' }
  await load()
  await store.loadDevices()
}

async function remove(d: Device): Promise<void> {
  if (!confirm(`Delete panel "${d.name}"? Its rotation membership is removed (apps are kept).`)) return
  await api.deleteDevice(d.id)
  await load()
  await store.loadDevices()
  if (store.activeDevice === d.id && devices.value.length) {
    void store.setActiveDevice(devices.value[0].id)
  }
}
</script>

<template>
  <div>
    <p class="mb-1 text-[11px] uppercase tracking-[0.22em] text-ember">Devices</p>
    <h2 class="mb-5 text-xl font-bold text-core">Panels</h2>
    <p v-if="error" class="mb-3 text-[11px] text-[#ff6a4a]">{{ error }}</p>

    <section v-if="displaySettings" class="mb-4 rounded border border-[#3a2016] bg-panel p-4">
      <h3 class="text-sm font-semibold text-core">Global display settings</h3>
      <form class="mt-3 grid max-w-xl gap-3" @submit.prevent="saveDisplaySettings" @input="settingsMessage = ''">
        <label class="grid gap-1 text-xs text-core">
          Time zone
          <select v-model="displaySettings.timezone"
            class="min-h-9 w-full rounded border border-[#3a2016] bg-[#120a10] px-2 text-gold focus:border-flame">
            <option v-for="zone in timezones" :key="zone" :value="zone">{{ zone.replaceAll('_', ' ') }}</option>
          </select>
        </label>
        <details>
          <summary class="cursor-pointer text-xs text-gold">Sunrise and sunset location</summary>
          <div class="mt-2 grid grid-cols-2 gap-3">
            <label class="grid min-w-0 gap-1 text-xs text-core">
              Latitude
              <input v-model.number="displaySettings.latitude" type="number" min="-90" max="90" step="any"
                class="min-h-9 w-full rounded border border-[#3a2016] bg-[#120a10] px-2 text-gold focus:border-flame" />
            </label>
            <label class="grid min-w-0 gap-1 text-xs text-core">
              Longitude
              <input v-model.number="displaySettings.longitude" type="number" min="-180" max="180" step="any"
                class="min-h-9 w-full rounded border border-[#3a2016] bg-[#120a10] px-2 text-gold focus:border-flame" />
            </label>
          </div>
          <p class="mt-2 text-xs text-muted">City coordinates are enough. With no location set, dimming follows 7 p.m.–7 a.m.</p>
        </details>
        <div class="flex flex-wrap items-center gap-3">
          <button type="submit" :disabled="savingSettings"
            class="min-h-9 rounded border border-[#8f4b29] px-3 text-xs text-gold hover:bg-[#251009] disabled:opacity-50">
            {{ savingSettings ? 'Saving…' : 'Save settings' }}
          </button>
          <p v-if="settingsMessage" role="status" class="text-xs text-gold">{{ settingsMessage }}</p>
        </div>
      </form>
    </section>

    <div class="grid grid-cols-1 gap-4">
      <section
        v-for="d in devices"
        :key="d.id"
        class="rounded border border-[#3a2016] bg-panel p-4"
        :class="d.enabled ? '' : 'opacity-60'"
      >
        <div class="mb-3 flex items-center gap-2">
          <input
            :value="d.name"
            class="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 text-base font-bold text-core hover:border-[#3a2016] focus:border-flame focus:outline-none"
            @change="patch(d, { name: ($event.target as HTMLInputElement).value })"
          />
          <span class="shrink-0 font-mono text-[10px] uppercase tracking-[0.18em] text-dim">{{ d.id }}</span>
          <button
            class="shrink-0 rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider"
            :class="d.enabled ? 'text-flame' : 'text-[#7a4a34]'"
            @click="patch(d, { enabled: !d.enabled })"
          >
            {{ d.enabled ? 'on' : 'off' }}
          </button>
          <button
            class="shrink-0 rounded border border-[#3a2016] px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-[#ff6a4a] hover:bg-[#251009]"
            @click="remove(d)"
          >
            delete
          </button>
        </div>

        <div class="grid gap-3 font-mono text-[11px] uppercase tracking-wider sm:grid-cols-2">
          <label class="flex items-center justify-between gap-2">
            <span class="text-dim">backend</span>
            <select
              :value="d.backend"
              class="rounded border border-[#3a2016] bg-[#120a10] px-2 py-1 text-gold focus:border-flame focus:outline-none"
              @change="patch(d, { backend: ($event.target as HTMLSelectElement).value as Device['backend'] })"
            >
              <option v-for="b in BACKENDS" :key="b" :value="b">{{ b }}</option>
            </select>
          </label>

          <label v-if="d.backend === 'wled' || d.backend === 'serial'" class="flex items-center justify-between gap-2">
            <span class="text-dim">{{ d.backend === 'wled' ? 'IP' : 'port' }}</span>
            <input
              :value="d.address"
              :placeholder="d.backend === 'wled' ? '192.168.1.166' : '/dev/tty…'"
              class="w-40 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1 text-right text-gold focus:border-flame focus:outline-none"
              @change="patch(d, { address: ($event.target as HTMLInputElement).value.trim() })"
            />
          </label>

          <label class="flex items-center justify-between gap-2">
            <span class="text-dim">mirror of</span>
            <select
              :value="d.mirror_of ?? ''"
              class="rounded border border-[#3a2016] bg-[#120a10] px-2 py-1 text-gold focus:border-flame focus:outline-none"
              @change="patch(d, { mirror_of: ($event.target as HTMLSelectElement).value || null })"
            >
              <option value="">— none —</option>
              <option v-for="o in mirrorOptions(d.id)" :key="o.id" :value="o.id">{{ o.name }}</option>
            </select>
          </label>

          <template v-if="!d.mirror_of">
            <label class="flex items-center justify-between gap-2">
              <span class="text-dim">layout</span>
              <select
                :value="d.layout_mode"
                class="rounded border border-[#3a2016] bg-[#120a10] px-2 py-1 text-gold focus:border-flame focus:outline-none"
                @change="patch(d, { layout_mode: ($event.target as HTMLSelectElement).value as Device['layout_mode'] })"
              >
                <option v-for="l in LAYOUTS" :key="l" :value="l">{{ l }}</option>
              </select>
            </label>

            <label class="flex items-center justify-between gap-2">
              <span class="text-dim">interval&nbsp;(s)</span>
              <input
                type="number"
                min="1"
                :value="d.cycle_interval"
                class="w-20 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1 text-gold focus:border-flame focus:outline-none"
                @change="patch(d, { cycle_interval: Number(($event.target as HTMLInputElement).value) })"
              />
            </label>

            <label class="flex items-center justify-between gap-2 sm:col-span-2">
              <span class="text-dim">{{ d.brightness_schedule?.enabled && d.brightness_schedule.mode === 'custom' ? 'manual fallback' : 'brightness' }} · {{ d.brightness }}</span>
              <input
                type="range"
                min="0"
                max="255"
                :value="d.brightness"
                class="w-40 accent-[#ff9e3d]"
                @change="patch(d, { brightness: Number(($event.target as HTMLInputElement).value) })"
              />
            </label>
          </template>
          <p v-else class="text-[10px] normal-case text-muted sm:col-span-2">
            Mirrors <span class="text-gold">{{ devices.find((x) => x.id === d.mirror_of)?.name ?? d.mirror_of }}</span> —
            shows the same content; layout &amp; rotation come from the target.
          </p>
        </div>
        <DeviceBrightnessSchedule
          v-if="d.backend === 'wled' || d.backend === 'serial'"
          :device="d"
          @saved="d.brightness_schedule = $event; store.loadDevices()"
        />
      </section>
    </div>

    <!-- add a panel -->
    <section class="mt-5 rounded border border-dashed border-[#3a2016] p-4">
      <div class="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-dim">Add a panel</div>
      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="draft.id"
          placeholder="id (e.g. apollo)"
          class="w-36 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
        />
        <input
          v-model="draft.name"
          placeholder="Name"
          class="w-40 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
        />
        <select
          v-model="draft.backend"
          class="rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
        >
          <option v-for="b in BACKENDS" :key="b" :value="b">{{ b }}</option>
        </select>
        <button
          class="rounded border border-[#3a2016] px-3 py-1.5 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009] disabled:opacity-40"
          :disabled="!draft.id || !draft.name"
          @click="create"
        >
          Add panel
        </button>
      </div>
    </section>
  </div>
</template>
