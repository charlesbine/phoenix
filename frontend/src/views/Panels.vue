<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { Panel, PanelLayout, DataSource } from '@/api/types'

type SourceType = NonNullable<DataSource['type']>

const LAYOUTS: { value: PanelLayout; label: string }[] = [
  { value: 'big_number', label: 'Big Number' },
  { value: 'key_value', label: 'Key/Value' },
  { value: 'marquee', label: 'Marquee' },
  { value: 'multi_stat', label: 'Multi Stat' },
  { value: 'sparkline', label: 'Sparkline' },
]

const SOURCES: { value: SourceType; label: string }[] = [
  { value: 'http', label: 'HTTP JSON' },
  { value: 'mqtt', label: 'MQTT topic' },
  { value: 'ha', label: 'Home Assistant' },
]

const panels = ref<Panel[]>([])
const loading = ref(false)
const saving = ref(false)
const previewing = ref(false)
const error = ref('')
const previewUrl = ref('')

/** null = creating a new panel; otherwise the id being edited. */
const editingId = ref<string | null>(null)

const draft = reactive<{
  id: string
  title: string
  layout: PanelLayout
  config: Record<string, unknown>
  data_source: DataSource
}>({
  id: '',
  title: '',
  layout: 'big_number',
  config: {},
  data_source: { type: 'http' },
})

const isEditing = computed(() => editingId.value !== null)
const sourceType = computed<SourceType>(() => draft.data_source.type ?? 'http')

function layoutLabel(value: PanelLayout): string {
  return LAYOUTS.find((l) => l.value === value)?.label ?? value
}

/** Assemble a clean payload from the draft for create/update/preview. */
function payload(): Partial<Panel> {
  return {
    id: draft.id.trim(),
    title: draft.title.trim(),
    layout: draft.layout,
    config: draft.config,
    data_source: { ...draft.data_source },
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    panels.value = await api.listPanels()
  } catch {
    error.value = 'Failed to load panels.'
  } finally {
    loading.value = false
  }
}

function resetForm() {
  editingId.value = null
  previewUrl.value = ''
  error.value = ''
  draft.id = ''
  draft.title = ''
  draft.layout = 'big_number'
  draft.config = {}
  draft.data_source = { type: 'http' }
}

function editPanel(p: Panel) {
  editingId.value = p.id
  previewUrl.value = ''
  error.value = ''
  draft.id = p.id
  draft.title = p.title
  draft.layout = p.layout
  draft.config = { ...p.config }
  draft.data_source = { type: 'http', ...p.data_source }
}

async function del(id: string) {
  if (!window.confirm(`Delete panel "${id}"? This cannot be undone.`)) return
  error.value = ''
  try {
    await api.deletePanel(id)
    if (editingId.value === id) resetForm()
    await load()
  } catch {
    error.value = `Failed to delete panel "${id}".`
  }
}

async function doPreview() {
  previewing.value = true
  error.value = ''
  previewUrl.value = ''
  try {
    const res = await api.previewPanel(payload())
    if (res.error) {
      error.value = res.error
    } else if (res.preview_url) {
      previewUrl.value = res.preview_url
    } else {
      error.value = 'Preview returned no image.'
    }
  } catch {
    error.value = 'Preview request failed.'
  } finally {
    previewing.value = false
  }
}

async function save() {
  if (!draft.id.trim()) {
    error.value = 'Panel id is required.'
    return
  }
  saving.value = true
  error.value = ''
  try {
    const body = payload()
    const result = isEditing.value
      ? await api.updatePanel(editingId.value as string, body)
      : await api.createPanel(body)
    if ('error' in result) {
      error.value = result.error
      return
    }
    resetForm()
    await load()
  } catch {
    error.value = 'Failed to save panel.'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <p class="text-[11px] uppercase tracking-[0.22em] text-ember mb-1">Panels</p>
    <h2 class="text-xl font-bold text-core mb-5">Panel Builder</h2>

    <p v-if="error" class="mb-4 text-[11px] text-[#ff6a4a]">{{ error }}</p>

    <div class="grid gap-5 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <!-- editor -->
      <section class="border border-[#3a2016] rounded bg-panel p-3">
        <div class="mb-3 flex items-center justify-between">
          <p class="text-[10px] uppercase tracking-[0.18em] text-dim">
            {{ isEditing ? 'Edit Panel' : 'New Panel' }}
          </p>
          <button
            class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009]"
            @click="resetForm"
          >
            {{ isEditing ? 'Cancel' : 'New' }}
          </button>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Id</label>
            <input
              v-model="draft.id"
              type="text"
              placeholder="weather"
              :disabled="isEditing"
              class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame disabled:text-[#7a4a34]"
            />
          </div>
          <div>
            <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Title</label>
            <input
              v-model="draft.title"
              type="text"
              placeholder="Weather"
              class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
            />
          </div>
        </div>

        <div class="mt-3">
          <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Layout</label>
          <select
            v-model="draft.layout"
            class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
          >
            <option v-for="l in LAYOUTS" :key="l.value" :value="l.value">{{ l.label }}</option>
          </select>
        </div>

        <div class="mt-4 border-t border-[#1c0e14] pt-3">
          <p class="text-[10px] uppercase tracking-[0.18em] text-dim mb-2">Data Source</p>
          <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Type</label>
          <select
            v-model="draft.data_source.type"
            class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
          >
            <option v-for="s in SOURCES" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>

          <!-- http -->
          <template v-if="sourceType === 'http'">
            <div class="mt-3">
              <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Url</label>
              <input
                v-model="draft.data_source.url"
                type="text"
                placeholder="https://api.example.com/data.json"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
              />
            </div>
            <div class="mt-3">
              <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Json Path</label>
              <input
                v-model="draft.data_source.json_path"
                type="text"
                placeholder="current.temp_c"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
              />
            </div>
          </template>

          <!-- mqtt -->
          <template v-else-if="sourceType === 'mqtt'">
            <div class="mt-3">
              <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Topic</label>
              <input
                v-model="draft.data_source.topic"
                type="text"
                placeholder="sensors/livingroom/temp"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
              />
            </div>
            <div class="mt-3">
              <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Json Path</label>
              <input
                v-model="draft.data_source.json_path"
                type="text"
                placeholder="value"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
              />
            </div>
          </template>

          <!-- ha -->
          <template v-else>
            <div class="mt-3">
              <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Entity</label>
              <input
                v-model="draft.data_source.entity"
                type="text"
                placeholder="sensor.living_room_temperature"
                class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
              />
            </div>
          </template>

          <div class="mt-3">
            <label class="block text-[10px] uppercase tracking-[0.18em] text-dim mb-1">Label</label>
            <input
              v-model="draft.data_source.label"
              type="text"
              placeholder="Temp"
              class="bg-[#120a10] border border-[#3a2016] text-gold px-2 py-1.5 text-xs rounded w-full focus:outline-none focus:border-flame"
            />
          </div>
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-2">
          <button
            class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009] disabled:text-[#7a4a34]"
            :disabled="previewing"
            @click="doPreview"
          >
            {{ previewing ? 'Rendering…' : 'Preview' }}
          </button>
          <button
            class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider bg-flame text-[#160a0a] disabled:opacity-60"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? 'Saving…' : isEditing ? 'Save' : 'Create' }}
          </button>
        </div>

        <!-- CRT preview bezel -->
        <div v-if="previewUrl" class="mt-4 flex flex-col items-center gap-2">
          <p class="text-[10px] uppercase tracking-[0.18em] text-dim">Preview</p>
          <div class="rounded-lg border-2 border-[#24121c] bg-black p-1.5" style="box-shadow: inset 0 0 20px #3a0f06">
            <img class="px w-40 h-40 object-contain" :src="previewUrl" alt="panel preview" />
          </div>
        </div>
      </section>

      <!-- list -->
      <section>
        <div class="mb-2 flex items-center justify-between">
          <p class="text-[10px] uppercase tracking-[0.18em] text-dim">
            Panels · {{ panels.length }}
          </p>
          <button
            class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009]"
            @click="load"
          >
            Refresh
          </button>
        </div>

        <p v-if="loading" class="text-[11px] uppercase tracking-wider text-dim">Loading panels…</p>
        <p v-else-if="!panels.length" class="text-[11px] uppercase tracking-wider text-dim">
          No panels yet. Create one on the left.
        </p>

        <div v-else class="grid gap-3 sm:grid-cols-2">
          <div
            v-for="p in panels"
            :key="p.id"
            class="border border-[#3a2016] rounded bg-panel p-3"
            :class="{ 'border-flame': editingId === p.id }"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="text-sm text-gold break-all">{{ p.id }}</span>
              <span class="shrink-0 rounded border border-[#3a2016] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-dim">
                {{ layoutLabel(p.layout) }}
              </span>
            </div>
            <p class="mt-1 text-xs text-core truncate">{{ p.title || '—' }}</p>
            <p class="mt-0.5 text-[10px] uppercase tracking-wider text-muted">
              {{ p.data_source.type ?? 'http' }}
            </p>
            <div class="mt-3 flex items-center gap-2">
              <button
                class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009]"
                @click="editPanel(p)"
              >
                Edit
              </button>
              <button
                class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-[#ff6a4a] hover:bg-[#251009]"
                @click="del(p.id)"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
