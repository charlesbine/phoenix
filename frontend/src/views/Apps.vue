<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { api } from '@/api/client'
import type { AppItem, Playlist, SchemaField } from '@/api/types'
import MatrixPreview from '@/components/MatrixPreview.vue'
import AppSettingsFields from '@/components/AppSettingsFields.vue'
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
const view = ref<'rotation' | 'library'>('rotation')
const addOpen = ref(false)
const addQuery = ref('')
const addBusy = ref<string | null>(null)
const addNote = ref<string | null>(null)
const addPreviewApp = ref<string | null>(null)
const addPreviewLive = ref(false)
const addPreviewTick = ref(0)
const addBatchBusy = ref(false)
const addBatchDone = ref(0)
const addBatchTotal = ref(0)
const addBatchErrors = ref(0)
const addPlaylistIds = ref<string[]>([])
const libraryQuery = ref('')
const libraryFilter = ref<'all' | 'shown' | 'hidden'>('all')
const customKey = ref('')
const customValue = ref('')
const refreshSeconds = ref('')
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
  live_matrix: 'matrix',
  unknown: 'app',
}

const inRotation = computed(() => new Set(apps.value.map((a) => a.name)))
const addCandidates = computed<AddCandidate[]>(() => {
  const rows: AddCandidate[] = []
  for (const app of globalApps.value) {
    if (!app.active) continue
    if (!inRotation.value.has(app.name)) rows.push({ name: app.name, installed: true, app })
  }
  const seen = new Set(rows.map((r) => r.name))
  const registered = globalNames.value
  for (const name of fileNames.value) {
    if (!inRotation.value.has(name) && !seen.has(name) && !registered.has(name)) {
      rows.push({ name, installed: false, app: null })
    }
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
const addSelectedCandidate = computed(() =>
  addPreviewApp.value ? candidateByName(addPreviewApp.value) : null,
)
const addSelectedMeta = computed(() => {
  const candidate = addSelectedCandidate.value
  if (!candidate) return []
  const source = candidate.app?.source || (candidate.installed ? 'local' : 'file')
  return [
    ['Kind', candidateKind(candidate)],
    ['State', candidate.installed ? 'registered' : 'file'],
    ['Source', source],
    ['Runtime', candidate.app?.is_live ? 'live' : 'rendered'],
  ]
})
const schemaIds = computed(() => new Set(schema.value.map((field) => field.id)))
const customConfigKeys = computed(() =>
  Object.keys(values)
    .filter((key) => !schemaIds.value.has(key))
    .sort((a, b) => a.localeCompare(b)),
)
const libraryApps = computed(() => {
  const q = libraryQuery.value.trim().toLowerCase()
  return globalApps.value
    .filter((app) => {
      if (libraryFilter.value === 'shown' && !app.active) return false
      if (libraryFilter.value === 'hidden' && app.active) return false
      if (!q) return true
      const haystack = [app.name, app.app_type, app.source, app.active ? 'shown' : 'hidden']
        .join(' ')
        .toLowerCase()
      return haystack.includes(q)
    })
    .sort((a, b) => a.name.localeCompare(b.name))
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

function replaceGlobal(u: AppItem): void {
  const i = globalApps.value.findIndex((x) => x.name === u.name)
  if (i >= 0) globalApps.value[i] = u
  else globalApps.value.push(u)
  globalNames.value = new Set(globalApps.value.map((a) => a.name))
}

async function selectApp(name: string): Promise<void> {
  selected.value = name
  note.value = null
  schema.value = []
  customKey.value = ''
  customValue.value = ''
  refreshSeconds.value = String(apps.value.find((a) => a.name === name)?.refresh_interval ?? '')
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
  const updated = a.active ? await api.deactivate(a.name) : await api.activate(a.name)
  replace(updated)
  replaceGlobal(updated)
}
async function toggleSkipWhenUnhealthy(a: AppItem): Promise<void> {
  const updated = await api.setSkipWhenUnhealthy(a.name, !a.skip_when_unhealthy, device.value)
  replace(updated)
  replaceGlobal({ ...updated, enabled: globalApps.value.find((g) => g.name === a.name)?.enabled ?? updated.enabled })
}
function healthTooltip(a: AppItem): string {
  const parts: string[] = [a.health_reason || 'Data ingress down']
  if (a.skipped_unhealthy) parts.push('Skipped in rotation')
  parts.push(`Last healthy: ${a.last_healthy_human || 'never'}`)
  return parts.join(' · ')
}

async function deleteGlobalApp(a: AppItem): Promise<void> {
  if (a.is_live || a.source === 'builtin') return
  if (!confirm(`Delete "${a.name}" from My Apps? This also removes it from rotations and playlists.`)) return
  try {
    await api.deleteApp(a.name)
    globalApps.value = globalApps.value.filter((app) => app.name !== a.name)
    globalNames.value = new Set(globalApps.value.map((app) => app.name))
    apps.value = apps.value.filter((app) => app.name !== a.name)
    if (selected.value === a.name) selected.value = null
    if (addPreviewApp.value === a.name) addPreviewApp.value = null
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}
async function setPreset(name: string, preset: string): Promise<void> {
  replace(await api.setPreset(name, preset)) // refresh cadence is global
}
async function saveRefreshInterval(name: string): Promise<void> {
  const seconds = Number(refreshSeconds.value)
  if (!Number.isFinite(seconds) || seconds <= 0) return
  replace(await api.setRefreshInterval(name, seconds))
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
    addBatchBusy.value = false
    addBatchDone.value = 0
    addBatchTotal.value = 0
    addBatchErrors.value = 0
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

function focusCandidate(name: string): void {
  const candidate = candidateByName(name)
  addPreviewApp.value = name
  addPreviewLive.value = Boolean(candidate?.app?.is_live)
  addNote.value = null
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

async function previewVisibleCandidates(): Promise<void> {
  if (addBatchBusy.value || !filteredCandidates.value.length) return
  const targets = [...filteredCandidates.value]
  addBatchBusy.value = true
  addBatchDone.value = 0
  addBatchTotal.value = targets.length
  addBatchErrors.value = 0
  try {
    for (const candidate of targets) {
      addPreviewApp.value = candidate.name
      addPreviewLive.value = Boolean(candidate.app?.is_live)
      addNote.value = `previewing ${addBatchDone.value + 1}/${addBatchTotal.value} · ${candidate.name}`
      try {
        const r = await api.preview(candidate.name)
        if (r?.error) addBatchErrors.value++
      } catch {
        addBatchErrors.value++
      } finally {
        addBatchDone.value++
        addPreviewTick.value++
      }
    }
    addNote.value = addBatchErrors.value
      ? `previewed ${addBatchDone.value}/${addBatchTotal.value} · ${addBatchErrors.value} failed`
      : `previewed ${addBatchDone.value}/${addBatchTotal.value}`
  } finally {
    addBatchBusy.value = false
  }
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

function addCustomConfig(): void {
  const key = customKey.value.trim()
  if (!key) return
  values[key] = customValue.value
  customKey.value = ''
  customValue.value = ''
}

function removeConfigValue(key: string): void {
  delete values[key]
}
</script>

<template>
  <div>
    <p class="mb-1 text-[11px] uppercase tracking-[0.22em] text-ember">Apps</p>
    <h2 class="mb-5 text-xl font-bold text-core">Rotation &amp; configuration</h2>
    <p v-if="error" class="mb-3 text-[11px] text-[#ff6a4a]">{{ error }}</p>

    <div class="mb-4 flex gap-1 border-b border-[#24121c] font-mono text-[11px] uppercase tracking-[0.16em]">
      <button
        class="border-b-2 px-3 py-2"
        :class="view === 'rotation' ? 'border-flame text-gold' : 'border-transparent text-dim hover:text-gold'"
        @click="view = 'rotation'"
      >
        Rotation
      </button>
      <button
        class="border-b-2 px-3 py-2"
        :class="view === 'library' ? 'border-flame text-gold' : 'border-transparent text-dim hover:text-gold'"
        @click="view = 'library'"
      >
        My apps
      </button>
    </div>

    <div v-if="view === 'rotation'" class="grid gap-5 md:grid-cols-2">
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
            :class="[
              a.name === selected ? 'bg-[#1e0f18]' : 'hover:bg-[#160b12]',
              a.health_status === 'unhealthy' ? 'border-l-2 border-l-[#ff5a2a]' : '',
            ]"
            @dragstart="dragName = a.name"
            @dragover.prevent
            @drop="onDrop(a.name)"
          >
            <span class="shrink-0 text-dim">⠿</span>
            <button
              class="flex-1 truncate text-left"
              :class="a.name === selected ? 'text-core' : a.health_status === 'unhealthy' ? 'text-[#ff8a6a]' : 'text-gold'"
              @click="selectApp(a.name)"
            >
              {{ a.name }}
            </button>
            <span
              v-if="a.health_status === 'unhealthy'"
              class="shrink-0 rounded border border-[#b3241a] bg-[#2a0a0e] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-[#ff6a4a]"
              :title="healthTooltip(a)"
            >
              {{ a.skipped_unhealthy ? 'down · skip' : 'data down' }}
            </span>
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
              <div class="mt-2 flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-dim">
                <span>{{ filteredCandidates.length }} shown</span>
                <button
                  class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009] disabled:cursor-not-allowed disabled:opacity-40"
                  :disabled="addBatchBusy || !filteredCandidates.length"
                  @click="previewVisibleCandidates"
                >
                  {{ addBatchBusy ? `Previewing ${addBatchDone}/${addBatchTotal}` : 'Preview visible' }}
                </button>
              </div>

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

            <div class="max-h-80 overflow-y-auto">
              <div
                v-for="c in filteredCandidates"
                :key="c.name"
                class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-[#1c0e14] px-3 py-2.5 last:border-b-0 hover:bg-[#160b12]"
                :class="addPreviewApp === c.name ? 'bg-[#1e0f18]' : ''"
                @click="focusCandidate(c.name)"
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
                    @click.stop="previewCandidate(c.name)"
                  >
                    Preview
                  </button>
                  <button
                    class="rounded bg-flame px-2.5 py-1 text-[10px] uppercase tracking-wider text-[#160a0a] disabled:opacity-40"
                    :disabled="addBusy !== null"
                    @click.stop="addApp(c.name)"
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
      <section v-if="addOpen" class="flex flex-col gap-4">
        <template v-if="addPreviewApp && addSelectedCandidate">
          <MatrixPreview
            :app="addPreviewApp"
            :tick="addPreviewTick"
            :device="device"
            :live="addPreviewLive"
            @render="renderAddPreview"
          />

          <div class="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-wider">
            <button class="rounded border border-[#3a2016] px-2.5 py-1 text-gold hover:bg-[#251009]" @click="renderAddPreview">
              Preview
            </button>
            <button
              class="rounded bg-flame px-2.5 py-1 text-[#160a0a] disabled:opacity-40"
              :disabled="addBusy !== null"
              @click="addPreviewApp && addApp(addPreviewApp)"
            >
              {{ addBusy === addPreviewApp ? 'Adding...' : 'Add to rotation' }}
            </button>
          </div>

          <p v-if="addNote" class="font-mono text-[10px] text-[#c78a5a]">{{ addNote }}</p>

          <div class="rounded border border-[#3a2016] bg-panel p-3">
            <div class="mb-3 flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-sm uppercase tracking-wide text-core">{{ addPreviewApp }}</div>
                <div class="mt-1 text-[10px] uppercase tracking-[0.18em] text-dim">
                  {{ candidateMeta(addSelectedCandidate) }}
                </div>
              </div>
              <span class="shrink-0 rounded border border-[#3a2016] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-flame">
                {{ candidateKind(addSelectedCandidate) }}
              </span>
            </div>

            <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-[11px]">
              <template v-for="row in addSelectedMeta" :key="row[0]">
                <dt class="uppercase tracking-[0.16em] text-dim">{{ row[0] }}</dt>
                <dd class="truncate text-right uppercase tracking-wide text-gold">{{ row[1] }}</dd>
              </template>
            </dl>

            <div v-if="playlists.length" class="mt-4 border-t border-[#1c0e14] pt-3">
              <div class="mb-2 text-[10px] uppercase tracking-[0.18em] text-dim">Playlist targets</div>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="pl in playlists.filter((p) => addPlaylistIds.includes(p.id))"
                  :key="pl.id"
                  class="rounded border border-flame bg-flame px-2 py-1 text-[10px] uppercase tracking-wider text-[#160a0a]"
                >
                  {{ pl.name }}
                </span>
                <span v-if="!addPlaylistIds.length" class="text-[10px] uppercase tracking-[0.16em] text-dim">Rotation only</span>
              </div>
            </div>
          </div>
        </template>

        <section v-else class="grid min-h-64 place-items-center rounded border border-dashed border-[#3a2016] p-10 text-[11px] uppercase tracking-widest text-dim">
          Select an app to preview
        </section>
      </section>

      <section v-else-if="selectedApp" class="flex flex-col gap-4">
        <MatrixPreview :app="selected" :tick="tick" :device="device" :live="selectedApp.is_live" @render="renderPreview" />
        <p v-if="note" class="font-mono text-[10px] text-[#c78a5a]">{{ note }}</p>

        <!-- data-ingress health & skip-when-unhealthy -->
        <div
          class="rounded border p-3 font-mono text-xs"
          :class="selectedApp.health_status === 'unhealthy'
            ? 'border-[#b3241a] bg-[#1e0a0e]'
            : 'border-[#3a2016] bg-panel'"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em]">
              <span
                class="h-2 w-2 rounded-full"
                :class="selectedApp.health_status === 'unhealthy'
                  ? 'bg-[#ff5a2a]'
                  : selectedApp.health_status === 'healthy'
                    ? 'bg-flame'
                    : 'bg-[#7a4a34]'"
              ></span>
              <span :class="selectedApp.health_status === 'unhealthy' ? 'text-[#ff6a4a]' : 'text-dim'">
                Ingress · {{ selectedApp.health_status === 'unhealthy' ? 'data down' : selectedApp.health_status }}
              </span>
              <span
                v-if="selectedApp.skipped_unhealthy"
                class="rounded border border-[#b3241a] bg-[#2a0a0e] px-1.5 py-0.5 text-[9px] text-[#ff6a4a]"
              >
                skipped in cycle
              </span>
            </div>
            <label class="flex cursor-pointer items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-gold">
              <input
                type="checkbox"
                :checked="selectedApp.skip_when_unhealthy"
                class="accent-flame"
                @change="toggleSkipWhenUnhealthy(selectedApp)"
              />
              Skip when data down
            </label>
          </div>
          <p v-if="selectedApp.health_status === 'unhealthy'" class="mt-2 text-[11px] text-core">
            {{ selectedApp.health_reason || 'Data source unavailable or empty.' }}
          </p>
          <p
            class="mt-1 text-[10px] uppercase tracking-[0.14em] text-muted"
            :title="selectedApp.last_healthy ?? undefined"
          >
            Last healthy: {{ selectedApp.last_healthy_human || 'never' }}
          </p>
        </div>

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
            <input
              v-model="refreshSeconds"
              type="number"
              min="1"
              step="1"
              class="w-20 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1 text-xs text-gold focus:border-flame focus:outline-none"
              @keyup.enter="saveRefreshInterval(selectedApp.name)"
            />
            <span>sec</span>
            <button class="rounded border border-[#3a2016] px-2 py-1 text-gold hover:bg-[#251009]" @click="saveRefreshInterval(selectedApp.name)">
              Set
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
          <AppSettingsFields :schema="schema" :values="values" @change="(id, value) => values[id] = value" />
        </div>
        <p v-else class="text-[11px] text-dim">This app has no configurable settings.</p>

        <div class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-3 text-[10px] uppercase tracking-[0.18em] text-dim">Custom settings</div>

          <div v-if="customConfigKeys.length" class="mb-3 flex flex-col gap-2">
            <div v-for="key in customConfigKeys" :key="key" class="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
              <input
                :value="key"
                readonly
                class="rounded border border-[#24121c] bg-[#0e0710] px-2 py-1.5 text-xs text-dim"
              />
              <input
                :value="values[key]"
                type="text"
                class="rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none"
                @input="onValue(key, $event)"
              />
              <button class="rounded border border-[#3a2016] px-2.5 py-1 text-[10px] uppercase tracking-wider text-[#ff6a4a] hover:bg-[#251009]" @click="removeConfigValue(key)">
                Remove
              </button>
            </div>
          </div>

          <div class="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
            <input
              v-model="customKey"
              type="text"
              placeholder="key"
              class="rounded border border-[#3a2016] bg-[#0e0710] px-2 py-1.5 text-xs text-core placeholder:text-[#7a4a34] focus:border-flame focus:outline-none"
            />
            <input
              v-model="customValue"
              type="text"
              placeholder="value"
              class="rounded border border-[#3a2016] bg-[#0e0710] px-2 py-1.5 text-xs text-core placeholder:text-[#7a4a34] focus:border-flame focus:outline-none"
              @keyup.enter="addCustomConfig"
            />
            <button class="rounded border border-[#3a2016] px-2.5 py-1 text-[10px] uppercase tracking-wider text-gold hover:bg-[#251009]" @click="addCustomConfig">
              Add
            </button>
          </div>
        </div>

        <button
          v-if="schema.length || customConfigKeys.length"
          class="self-start rounded bg-flame px-3 py-1.5 text-[11px] uppercase tracking-wider text-[#160a0a]"
          @click="saveConfig"
        >
          Save settings
        </button>
      </section>

      <section v-else class="grid place-items-center rounded border border-dashed border-[#3a2016] p-10 text-[11px] uppercase tracking-widest text-dim">
        Select an app to configure
      </section>
    </div>

    <div v-else class="grid gap-5 md:grid-cols-[18rem_1fr]">
      <section class="space-y-3">
        <input
          v-model="libraryQuery"
          type="search"
          autocomplete="off"
          placeholder="search my apps..."
          class="w-full rounded border border-[#3a2016] bg-[#0e0710] px-2.5 py-2 text-xs text-core placeholder:text-[#7a4a34] focus:border-flame focus:outline-none"
        />
        <div class="flex flex-wrap gap-1.5 font-mono text-[10px] uppercase tracking-wider">
          <button
            class="rounded border border-[#3a2016] px-2 py-1"
            :class="libraryFilter === 'all' ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
            @click="libraryFilter = 'all'"
          >
            All
          </button>
          <button
            class="rounded border border-[#3a2016] px-2 py-1"
            :class="libraryFilter === 'shown' ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
            @click="libraryFilter = 'shown'"
          >
            Shown
          </button>
          <button
            class="rounded border border-[#3a2016] px-2 py-1"
            :class="libraryFilter === 'hidden' ? 'bg-flame text-[#160a0a]' : 'text-dim hover:text-gold'"
            @click="libraryFilter = 'hidden'"
          >
            Hidden
          </button>
        </div>
      </section>

      <section class="rounded border border-[#3a2016]">
        <div
          v-for="app in libraryApps"
          :key="app.name"
          class="grid gap-3 border-b border-[#1c0e14] px-3 py-2.5 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
        >
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <span class="shrink-0 rounded border border-[#3a2016] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-flame">
                {{ TYPE_MARK[app.app_type] ?? app.app_type }}
              </span>
              <span class="truncate text-xs uppercase tracking-wide text-gold">{{ app.name }}</span>
              <span
                v-if="app.health_status === 'unhealthy'"
                class="shrink-0 rounded border border-[#b3241a] bg-[#2a0a0e] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-[#ff6a4a]"
                :title="healthTooltip(app)"
              >
                {{ app.skipped_unhealthy ? 'down · skip' : 'data down' }}
              </span>
              <span v-if="inRotation.has(app.name)" class="shrink-0 text-[10px] uppercase tracking-[0.14em] text-[#c78a5a]">
                in rotation
              </span>
            </div>
            <div class="mt-1 truncate text-[10px] uppercase tracking-[0.16em] text-dim">
              {{ app.source || 'local' }} · {{ app.is_live ? 'live' : 'rendered' }} · {{ app.active ? 'shown in add' : 'hidden from add' }}
            </div>
          </div>

          <div class="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider">
            <button
              class="rounded border border-[#3a2016] px-2.5 py-1"
              :class="app.active ? 'text-[#ff6a4a] hover:bg-[#251009]' : 'bg-flame text-[#160a0a]'"
              @click="toggleActive(app)"
            >
              {{ app.active ? 'Hide' : 'Show' }}
            </button>
            <button
              v-if="!app.is_live && app.source !== 'builtin'"
              class="rounded border border-[#3a2016] px-2.5 py-1 text-[#ff6a4a] hover:bg-[#251009]"
              @click="deleteGlobalApp(app)"
            >
              Delete
            </button>
          </div>
        </div>

        <div v-if="!libraryApps.length" class="px-3 py-8 text-center text-[11px] uppercase tracking-widest text-dim">
          No matches
        </div>
      </section>
    </div>
  </div>
</template>
