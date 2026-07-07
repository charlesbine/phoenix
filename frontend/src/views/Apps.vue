<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { api } from '@/api/client'
import type { AppItem, Playlist, SchemaField } from '@/api/types'
import MatrixPreview from '@/components/MatrixPreview.vue'
import { useMatrixStore } from '@/stores/matrix'

const store = useMatrixStore()
const device = computed(() => store.activeDevice)

const apps = ref<AppItem[]>([]) // this device's rotation
const globalApps = ref<AppItem[]>([]) // every registered app
const globalNames = ref<Set<string>>(new Set()) // every installed app (for the add picker)
const fileNames = ref<string[]>([]) // app files that may not be registered yet
const playlists = ref<Playlist[]>([])
const selected = ref<string | null>(null)
const schema = ref<SchemaField[]>([])
const values = reactive<Record<string, string>>({})
const tick = ref(0)
const error = ref<string | null>(null)
const note = ref<string | null>(null)
const addOpen = ref(false)
const addQuery = ref('')
const addBusy = ref<string | null>(null)
const addNote = ref<string | null>(null)
const addPreviewApp = ref<string | null>(null)
const addPreviewLive = ref(false)
const addPreviewTick = ref(0)
const addPlaylistIds = ref<string[]>([])
const showDisabled = ref(false)
const visibleApps = computed(() =>
  showDisabled.value ? apps.value : apps.value.filter((a) => a.enabled),
)

const PRESETS = ['realtime', 'frequent', 'ambient']
const selectedApp = computed(() => apps.value.find((a) => a.name === selected.value) ?? null)

interface AddCandidate {
  name: string
  installed: boolean
  app: AppItem | null
}

const TYPE_MARK: Record<string, string> = {
  star: 'star',
  python: 'py',
  static: 'static',
  panel: 'panel',
  live_audio: 'audio',
  live_nowplaying: 'playing',
  unknown: 'app',
}

const inRotation = computed(() => new Set(apps.value.map((a) => a.name)))
const addCandidates = computed<AddCandidate[]>(() => {
  const rows: AddCandidate[] = []
  for (const app of globalApps.value) {
    if (!inRotation.value.has(app.name)) rows.push({ name: app.name, installed: true, app })
  }
  const seen = new Set(rows.map((r) => r.name))
  for (const name of fileNames.value) {
    if (!inRotation.value.has(name) && !seen.has(name)) rows.push({ name, installed: false, app: null })
  }
  return rows.sort((a, b) => a.name.localeCompare(b.name))
})
const filteredCandidates = computed(() => {
  const q = addQuery.value.trim().toLowerCase()
  if (!q) return addCandidates.value
  return addCandidates.value.filter((c) => {
    const haystack = [
      c.name,
      c.app?.app_type ?? '',
      c.app?.source ?? '',
      c.installed ? 'registered' : 'file',
    ].join(' ').toLowerCase()
    return haystack.includes(q)
  })
})

async function load(): Promise<void> {
  try {
    const [rotation, allApps, files, allPlaylists] = await Promise.all([
      api.listApps(device.value),
      api.listApps(),
      api.availableApps(),
      api.listPlaylists(),
    ])
    apps.value = rotation.sort((a, b) => a.sort_order - b.sort_order)
    globalApps.value = allApps
    globalNames.value = new Set(allApps.map((a) => a.name))
    fileNames.value = files
    playlists.value = allPlaylists
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
onMounted(load)
watch(device, () => {
  selected.value = null
  void load()
})

function replace(u: AppItem): void {
  const i = apps.value.findIndex((x) => x.name === u.name)
  if (i >= 0) apps.value[i] = u
}

async function selectApp(name: string): Promise<void> {
  selected.value = name
  note.value = null
  schema.value = []
  for (const k of Object.keys(values)) delete values[k]
  try {
    schema.value = await api.getSchema(name)
  } catch {
    schema.value = []
  }
  for (const f of schema.value) values[f.id] = f.default ?? ''
  const cfg = apps.value.find((a) => a.name === name)?.pixlet_config ?? {}
  for (const [k, v] of Object.entries(cfg)) values[k] = String(v)
  tick.value++
}

async function saveConfig(): Promise<void> {
  if (!selected.value) return
  try {
    replace(await api.setAppConfig(selected.value, { ...values }))
    note.value = 'saved · rendering…'
    const r = await api.preview(selected.value)
    note.value = r?.error ?? r?.info ?? 'saved'
    tick.value++
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function renderPreview(): Promise<void> {
  if (!selected.value) return
  note.value = 'rendering…'
  const r = await api.preview(selected.value)
  note.value = r?.error ?? r?.info ?? null
  tick.value++
}

async function toggleEnabled(a: AppItem): Promise<void> {
  replace(a.enabled ? await api.disable(a.name, device.value) : await api.enable(a.name, device.value))
}
async function toggleActive(a: AppItem): Promise<void> {
  // active/inactive is a global app property (preprocessor gate), not per-device.
  replace(a.active ? await api.deactivate(a.name) : await api.activate(a.name))
}
async function setPreset(name: string, preset: string): Promise<void> {
  replace(await api.setPreset(name, preset)) // refresh cadence is global
}
async function setPriority(name: string, priority: number): Promise<void> {
  replace(await api.setPriority(name, Math.max(0, priority), device.value))
}
async function removeApp(name: string): Promise<void> {
  if (!confirm(`Remove "${name}" from this panel's rotation? (The app itself is kept.)`)) return
  await api.removeFromDevice(name, device.value)
  if (selected.value === name) selected.value = null
  await load()
}

function toggleAddPanel(): void {
  addOpen.value = !addOpen.value
  addNote.value = null
  if (!addOpen.value) {
    addQuery.value = ''
    addPreviewApp.value = null
    addPreviewLive.value = false
  }
}

function togglePlaylist(id: string): void {
  addPlaylistIds.value = addPlaylistIds.value.includes(id)
    ? addPlaylistIds.value.filter((x) => x !== id)
    : [...addPlaylistIds.value, id]
}

function candidateKind(c: AddCandidate): string {
  if (!c.app) return 'file'
  return TYPE_MARK[c.app.app_type] ?? c.app.app_type
}

function candidateMeta(c: AddCandidate): string {
  const parts = [c.installed ? 'registered' : 'file']
  if (c.app?.source) parts.push(c.app.source)
  if (c.app?.is_live) parts.push('live')
  return parts.join(' · ')
}

function candidateByName(name: string): AddCandidate | null {
  return addCandidates.value.find((c) => c.name === name) ?? null
}

async function previewCandidate(name: string): Promise<void> {
  const candidate = candidateByName(name)
  addPreviewApp.value = name
  addPreviewLive.value = Boolean(candidate?.app?.is_live)
  addNote.value = 'previewing...'
  try {
    const r = await api.preview(name)
    addNote.value = r?.error ?? r?.info ?? 'preview ready'
  } catch (e) {
    addNote.value = e instanceof Error ? e.message : String(e)
  } finally {
    addPreviewTick.value++
  }
}

async function renderAddPreview(): Promise<void> {
  if (addPreviewApp.value) await previewCandidate(addPreviewApp.value)
}

async function addApp(name: string): Promise<void> {
  if (!name || addBusy.value) return
  addBusy.value = name
  addNote.value = null
  try {
    // Install globally first if it's an app file that isn't registered yet…
    if (!globalNames.value.has(name)) await api.addApp(name)
    // …then add it to this panel's rotation.
    await api.addApp(name, device.value)
    for (const id of addPlaylistIds.value) {
      const playlist = playlists.value.find((p) => p.id === id)
      if (!playlist || playlist.app_names.includes(name)) continue
      const updated = await api.updatePlaylist(id, { app_names: [...playlist.app_names, name] })
      const idx = playlists.value.findIndex((p) => p.id === id)
      if (idx >= 0) playlists.value[idx] = updated
    }
    addOpen.value = false
    addQuery.value = ''
    addPreviewApp.value = null
    addPreviewLive.value = false
    addPlaylistIds.value = []
    await load()
    await selectApp(name)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    addBusy.value = null
  }
}

// --- drag reorder ---
const dragName = ref<string | null>(null)
function onDrop(target: string): void {
  const from = dragName.value
  dragName.value = null
  if (!from || from === target) return
  const order = apps.value.map((a) => a.name)
  const fi = order.indexOf(from)
  const ti = order.indexOf(target)
  order.splice(ti, 0, order.splice(fi, 1)[0])
  apps.value = order.map((n) => apps.value.find((a) => a.name === n)!)
  api.reorder(order, device.value).catch((e: unknown) => {
    error.value = e instanceof Error ? e.message : String(e)
  })
}

function onValue(id: string, e: Event): void {
  const t = e.target as HTMLInputElement
  values[id] = t.type === 'checkbox' ? (t.checked ? 'true' : 'false') : t.value
}
</script>

<template>
  <div>
    <p class="mb-1 text-[11px] uppercase tracking-[0.22em] text-ember">Apps</p>
    <h2 class="mb-5 text-xl font-bold text-core">Rotation &amp; configuration</h2>
    <p v-if="error" class="mb-3 text-[11px] text-[#ff6a4a]">{{ error }}</p>

    <div class="grid gap-5 md:grid-cols-2">
      <!-- rotation list (drag to reorder) -->
      <section>
        <div class="mb-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
          <span>Rotation · {{ apps.length }} · drag to reorder</span>
          <button class="hover:text-gold" :class="showDisabled ? 'text-gold' : ''" @click="showDisabled = !showDisabled">
            {{ showDisabled ? '− hide disabled' : '+ show disabled' }}
          </button>
        </div>
        <ul class="rounded border border-[#3a2016]">
          <li
            v-for="a in visibleApps"
            :key="a.name"
            draggable="true"
            class="flex cursor-grab items-center gap-2.5 border-b border-[#1c0e14] px-3 py-2 text-xs uppercase tracking-wide last:border-b-0"
            :class="a.name === selected ? 'bg-[#1e0f18]' : 'hover:bg-[#160b12]'"
            @dragstart="dragName = a.name"
            @dragover.prevent
            @drop="onDrop(a.name)"
          >
            <span class="shrink-0 text-dim">⠿</span>
            <button class="flex-1 truncate text-left" :class="a.name === selected ? 'text-core' : 'text-gold'" @click="selectApp(a.name)">
              {{ a.name }}
            </button>
            <span v-if="a.priority > 0" class="shrink-0 text-[10px] text-[#ff6a4a]">×{{ a.priority + 1 }}</span>
            <button class="w-8 shrink-0 text-right text-[10px]" :class="a.enabled ? 'text-flame' : 'text-[#7a4a34]'" @click="toggleEnabled(a)">
              {{ a.enabled ? 'ON' : 'OFF' }}
            </button>
          </li>
        </ul>

        <!-- add app -->
        <div class="mt-3">
          <button
            class="flex w-full items-center justify-between rounded border border-[#3a2016] bg-[#120a10] px-3 py-2 text-left font-mono text-[11px] uppercase tracking-[0.16em] text-gold hover:bg-[#1a0c11]"
            @click="toggleAddPanel"
          >
            <span>{{ addOpen ? 'Close add flow' : 'Add app to rotation' }}</span>
            <span class="text-dim">{{ addCandidates.length }} available</span>
          </button>

          <div v-if="addOpen" class="mt-2 rounded border border-[#3a2016] bg-[#120a10]">
            <div class="border-b border-[#1c0e14] p-3">
              <input
                v-model="addQuery"
                type="search"
                autocomplete="off"
                placeholder="search apps, types, sources..."
                class="w-full rounded border border-[#3a2016] bg-[#0e0710] px-2.5 py-2 text-xs text-core placeholder:text-[#7a4a34] focus:border-flame focus:outline-none"
              />

              <div v-if="playlists.length" class="mt-3">
                <div class="mb-1.5 text-[10px] uppercase tracking-[0.18em] text-dim">Also add to playlist</div>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    v-for="pl in playlists"
                    :key="pl.id"
                    type="button"
                    class="rounded border px-2 py-1 text-[10px] uppercase tracking-wider"
                    :class="
                      addPlaylistIds.includes(pl.id)
                        ? 'border-flame bg-flame text-[#160a0a]'
                        : 'border-[#3a2016] text-dim hover:bg-[#251009] hover:text-gold'
                    "
                    @click="togglePlaylist(pl.id)"
                  >
                    {{ pl.name }}
                  </button>
                </div>
              </div>
            </div>

            <div v-if="addPreviewApp" class="grid gap-3 border-b border-[#1c0e14] p-3 sm:grid-cols-[7rem_1fr]">
              <MatrixPreview
                :app="addPreviewApp"
                :tick="addPreviewTick"
                :device="device"
                :live="addPreviewLive"
                @render="renderAddPreview"
              />
              <div class="min-w-0 self-center">
                <div class="truncate text-sm uppercase tracking-wide text-core">{{ addPreviewApp }}</div>
                <p v-if="addNote" class="mt-1 text-[11px] text-[#c78a5a]">{{ addNote }}</p>
              </div>
            </div>

            <div class="max-h-80 overflow-y-auto">
              <div
                v-for="c in filteredCandidates"
                :key="c.name"
                class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-[#1c0e14] px-3 py-2.5 last:border-b-0 hover:bg-[#160b12]"
              >
                <div class="min-w-0">
                  <div class="flex min-w-0 items-center gap-2">
                    <span class="shrink-0 rounded border border-[#3a2016] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-flame">
                      {{ candidateKind(c) }}
                    </span>
                    <span class="truncate text-xs uppercase tracking-wide text-gold">{{ c.name }}</span>
                  </div>
                  <div class="mt-1 truncate text-[10px] uppercase tracking-[0.16em] text-dim">
                    {{ candidateMeta(c) }}
                  </div>
                </div>
                <div class="flex items-center gap-1.5">
                  <button
                    class="rounded border border-[#3a2016] px-2 py-1 text-[10px] uppercase tracking-wider text-dim hover:bg-[#251009] hover:text-gold"
                    @click="previewCandidate(c.name)"
                  >
                    Preview
                  </button>
                  <button
                    class="rounded bg-flame px-2.5 py-1 text-[10px] uppercase tracking-wider text-[#160a0a] disabled:opacity-40"
                    :disabled="addBusy !== null"
                    @click="addApp(c.name)"
                  >
                    {{ addBusy === c.name ? 'Adding...' : 'Add' }}
                  </button>
                </div>
              </div>

              <div v-if="!filteredCandidates.length" class="px-3 py-8 text-center text-[11px] uppercase tracking-widest text-dim">
                {{ addCandidates.length ? 'No matches' : 'No apps available' }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- detail / config editor -->
      <section v-if="selectedApp" class="flex flex-col gap-4">
        <MatrixPreview :app="selected" :tick="tick" :device="device" :live="selectedApp.is_live" @render="renderPreview" />
        <p v-if="note" class="font-mono text-[10px] text-[#c78a5a]">{{ note }}</p>

        <!-- settings -->
        <div class="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-wider">
          <button class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009]" @click="api.showNow(selectedApp.name, device)">▷ show</button>
          <button class="rounded px-2.5 py-1" :class="selectedApp.enabled ? 'text-flame' : 'text-[#7a4a34]'" @click="toggleEnabled(selectedApp)">{{ selectedApp.enabled ? 'enabled' : 'disabled' }}</button>
          <button class="rounded px-2.5 py-1" :class="selectedApp.active ? 'text-flame' : 'text-[#7a4a34]'" @click="toggleActive(selectedApp)">{{ selectedApp.active ? 'active' : 'inactive' }}</button>
          <button class="ml-auto rounded border border-[#3a2016] px-2.5 py-1 text-[#ff6a4a] hover:bg-[#251009]" @click="removeApp(selectedApp.name)">remove</button>
        </div>

        <!-- refresh preset + priority -->
        <div class="flex flex-wrap items-center gap-3 font-mono text-[11px] uppercase tracking-wider">
          <div class="flex items-center gap-1">
            <span class="text-dim">refresh</span>
            <button
              v-for="p in PRESETS"
              :key="p"
              class="rounded border border-[#3a2016] px-2 py-1"
              :class="selectedApp.refresh_preset === p ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
              @click="setPreset(selectedApp.name, p)"
            >
              {{ p }}
            </button>
          </div>
          <div class="flex items-center gap-1.5 text-dim">
            <span>weight</span>
            <button class="px-1 text-gold hover:text-core" @click="setPriority(selectedApp.name, selectedApp.priority - 1)">−</button>
            <span class="text-gold">×{{ selectedApp.priority + 1 }}</span>
            <button class="px-1 text-gold hover:text-core" @click="setPriority(selectedApp.name, selectedApp.priority + 1)">+</button>
          </div>
        </div>

        <!-- schema-driven config -->
        <div v-if="schema.length" class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 text-[10px] uppercase tracking-[0.18em] text-dim">Settings</div>
          <div class="flex flex-col gap-3">
            <div v-for="f in schema" :key="f.id">
              <label class="mb-1 block text-[10px] uppercase tracking-[0.14em] text-dim">{{ f.name ?? f.id }}</label>
              <p v-if="f.desc" class="mb-1 text-[10px] normal-case text-muted">{{ f.desc }}</p>

              <select v-if="f.type === 'dropdown'" :value="values[f.id]" class="w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none" @change="onValue(f.id, $event)">
                <option v-for="o in f.options ?? []" :key="o.value" :value="o.value">{{ o.display }}</option>
              </select>

              <label v-else-if="f.type === 'toggle'" class="flex items-center gap-2 text-xs text-gold">
                <input type="checkbox" :checked="values[f.id] === 'true'" @change="onValue(f.id, $event)" />
                {{ values[f.id] === 'true' ? 'on' : 'off' }}
              </label>

              <input v-else-if="f.type === 'color'" type="color" :value="values[f.id] || '#000000'" class="h-8 w-16 rounded border border-[#3a2016] bg-[#120a10]" @input="onValue(f.id, $event)" />

              <input v-else :value="values[f.id]" type="text" class="w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none" @input="onValue(f.id, $event)" />
            </div>
          </div>
          <button class="mt-4 rounded bg-flame px-3 py-1.5 text-[11px] uppercase tracking-wider text-[#160a0a]" @click="saveConfig">Save settings</button>
        </div>
        <p v-else class="text-[11px] text-dim">This app has no configurable settings.</p>
      </section>

      <section v-else class="grid place-items-center rounded border border-dashed border-[#3a2016] p-10 text-[11px] uppercase tracking-widest text-dim">
        Select an app to configure
      </section>
    </div>
  </div>
</template>
