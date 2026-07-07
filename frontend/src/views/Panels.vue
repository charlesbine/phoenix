<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { Panel, PanelLayout, DataSource } from '@/api/types'

type SourceType = NonNullable<DataSource['type']>
type AuthType = 'none' | 'bearer' | 'api_key' | 'basic'
type DraftRow = Record<string, string>

const LAYOUTS: { value: PanelLayout; label: string }[] = [
  { value: 'big_number', label: 'Big Number' },
  { value: 'key_value', label: 'Key/Value' },
  { value: 'marquee', label: 'Marquee' },
  { value: 'multi_stat', label: 'Multi Stat' },
  { value: 'sparkline', label: 'Sparkline' },
]

const SOURCES: { value: SourceType; label: string }[] = [
  { value: 'static', label: 'Static values' },
  { value: 'http', label: 'HTTP JSON' },
  { value: 'mqtt', label: 'MQTT topic' },
  { value: 'ha', label: 'Home Assistant' },
]

const AUTH_TYPES: { value: AuthType; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'bearer', label: 'Bearer token' },
  { value: 'api_key', label: 'API key header' },
  { value: 'basic', label: 'Basic auth' },
]

const COLOR_FIELDS = [
  { key: 'color', label: 'Primary' },
  { key: 'title_color', label: 'Title' },
  { key: 'label_color', label: 'Label' },
  { key: 'key_color', label: 'Key' },
  { key: 'value_color', label: 'Value' },
]

const inputClass =
  'w-full rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none disabled:text-[#7a4a34]'
const miniInputClass =
  'min-w-0 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-gold focus:border-flame focus:outline-none'
const ghostButtonClass =
  'rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-gold hover:bg-[#251009] disabled:text-[#7a4a34]'

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
  data_source: { type: 'static' },
})

const isEditing = computed(() => editingId.value !== null)
const sourceType = computed<SourceType>(() => draft.data_source.type ?? 'static')
const isStaticSource = computed(() => sourceType.value === 'static')
const isMappedSource = computed(() => !isStaticSource.value)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value ?? {})) as T
}

function inputValue(event: Event): string {
  return (event.target as HTMLInputElement | HTMLSelectElement).value
}

function layoutLabel(value: PanelLayout): string {
  return LAYOUTS.find((l) => l.value === value)?.label ?? value
}

function sourceLabel(value: SourceType): string {
  return SOURCES.find((s) => s.value === value)?.label ?? value
}

function normalizeDataSource(source: DataSource | undefined): DataSource {
  const next = deepClone(source ?? {}) as DataSource
  next.type = next.type ?? 'static'
  if (!next.entity_id && typeof next.entity === 'string') {
    next.entity_id = next.entity
  }
  delete next.entity
  if (!isRecord(next.mappings)) {
    next.mappings = {}
  }
  return next
}

function mappings(): Record<string, unknown> {
  if (!isRecord(draft.data_source.mappings)) {
    draft.data_source.mappings = {}
  }
  return draft.data_source.mappings
}

function authRecord(): Record<string, unknown> {
  return isRecord(draft.data_source.auth) ? draft.data_source.auth : {}
}

function authType(): AuthType {
  const value = authRecord().type
  return value === 'bearer' || value === 'api_key' || value === 'basic' ? value : 'none'
}

function recordString(record: Record<string, unknown>, key: string, fallback = ''): string {
  const value = record[key]
  return value === undefined || value === null ? fallback : String(value)
}

function sourceString(key: string, fallback = ''): string {
  return recordString(draft.data_source, key, fallback)
}

function sourceNumber(key: string, fallback: number): number {
  const value = draft.data_source[key]
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function configString(key: string, fallback = ''): string {
  return recordString(draft.config, key, fallback)
}

function mappingString(key: string, fallback = ''): string {
  return recordString(mappings(), key, fallback)
}

function configColor(key: string): string {
  const value = configString(key)
  return /^#[0-9a-f]{6}$/i.test(value) ? value : '#ffffff'
}

function setRecordValue(record: Record<string, unknown>, key: string, value: string): void {
  if (value.trim() === '') {
    delete record[key]
    return
  }
  record[key] = value
}

function setSourceValue(key: string, event: Event): void {
  setRecordValue(draft.data_source, key, inputValue(event))
}

function setSourceNumber(key: string, event: Event, fallback: number): void {
  const parsed = Number(inputValue(event))
  draft.data_source[key] = Number.isFinite(parsed) ? parsed : fallback
}

function setConfigValue(key: string, event: Event): void {
  setRecordValue(draft.config, key, inputValue(event))
}

function setMappingValue(key: string, event: Event): void {
  setRecordValue(mappings(), key, inputValue(event))
}

function setAuthType(event: Event): void {
  const value = inputValue(event) as AuthType
  if (value === 'none') {
    delete draft.data_source.auth
    return
  }

  const current = authRecord()
  const next: Record<string, unknown> = { type: value }
  if (value === 'api_key') {
    next.header = recordString(current, 'header', 'X-API-Key')
    next.token = recordString(current, 'token')
  } else if (value === 'basic') {
    next.username = recordString(current, 'username')
    next.password = recordString(current, 'password')
  } else {
    next.token = recordString(current, 'token')
  }
  draft.data_source.auth = next
}

function setAuthValue(key: string, event: Event): void {
  if (!isRecord(draft.data_source.auth)) {
    draft.data_source.auth = { type: 'bearer' }
  }
  setRecordValue(draft.data_source.auth, key, inputValue(event))
}

function ensureRows(target: Record<string, unknown>, key: string, fallback: DraftRow): DraftRow[] {
  if (!Array.isArray(target[key]) || !(target[key] as unknown[]).length) {
    target[key] = [{ ...fallback }]
  }
  return target[key] as DraftRow[]
}

function staticItems(): DraftRow[] {
  return ensureRows(draft.config, 'items', { key: '', value: '' })
}

function mappedItems(): DraftRow[] {
  return ensureRows(mappings(), 'items', { key: '', value_path: '', transform: '', unit: '' })
}

function staticStats(): DraftRow[] {
  return ensureRows(draft.config, 'stats', { label: '', value: '', color: '#ffffff' })
}

function mappedStats(): DraftRow[] {
  return ensureRows(mappings(), 'stats', {
    label: '',
    value_path: '',
    transform: '',
    unit: '',
    color: '#ffffff',
  })
}

function addItemRow(): void {
  const rows = isStaticSource.value ? staticItems() : mappedItems()
  rows.push(isStaticSource.value ? { key: '', value: '' } : { key: '', value_path: '', transform: '', unit: '' })
}

function removeItemRow(index: number): void {
  const rows = isStaticSource.value ? staticItems() : mappedItems()
  rows.splice(index, 1)
  if (!rows.length) addItemRow()
}

function addStatRow(): void {
  const rows = isStaticSource.value ? staticStats() : mappedStats()
  rows.push(
    isStaticSource.value
      ? { label: '', value: '', color: '#ffffff' }
      : { label: '', value_path: '', transform: '', unit: '', color: '#ffffff' },
  )
}

function removeStatRow(index: number): void {
  const rows = isStaticSource.value ? staticStats() : mappedStats()
  rows.splice(index, 1)
  if (!rows.length) addStatRow()
}

function setLayout(event: Event): void {
  draft.layout = inputValue(event) as PanelLayout
  previewUrl.value = ''
  ensureLayoutDefaults()
}

function setSourceType(event: Event): void {
  const value = inputValue(event) as SourceType
  const previous = normalizeDataSource(draft.data_source)
  const next: DataSource = {
    type: value,
    label: previous.label,
    mappings: isRecord(previous.mappings) ? deepClone(previous.mappings) : {},
  }

  if (value === 'http') {
    next.url = typeof previous.url === 'string' ? previous.url : ''
    next.ttl = sourceNumber('ttl', 300)
    if (isRecord(previous.auth)) next.auth = deepClone(previous.auth)
    if (isRecord(previous.headers)) next.headers = deepClone(previous.headers) as Record<string, string>
  } else if (value === 'mqtt') {
    next.topic = typeof previous.topic === 'string' ? previous.topic : ''
  } else if (value === 'ha') {
    next.entity_id = typeof previous.entity_id === 'string' ? previous.entity_id : ''
    next.ttl = sourceNumber('ttl', 60)
  }

  draft.data_source = next
  previewUrl.value = ''
  ensureLayoutDefaults()
}

function ensureLayoutDefaults(): void {
  if (draft.layout === 'key_value') {
    isStaticSource.value ? staticItems() : mappedItems()
  } else if (draft.layout === 'multi_stat') {
    isStaticSource.value ? staticStats() : mappedStats()
  } else if (draft.layout === 'big_number' && sourceType.value === 'ha' && !mappingString('value')) {
    mappings().value = 'state'
  } else if (draft.layout === 'sparkline' && isStaticSource.value && !Array.isArray(draft.config.points)) {
    draft.config.points = [2, 4, 3, 7, 6, 9, 8]
  }
}

function cleanStringRecord(row: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(row)) {
    if (value === undefined || value === null) continue
    const text = String(value).trim()
    if (text) out[key] = text
  }
  return out
}

function cleanRows(value: unknown, requiredKey: string): Record<string, string>[] {
  if (!Array.isArray(value)) return []
  return value.map((row) => cleanStringRecord(isRecord(row) ? row : {})).filter((row) => row[requiredKey])
}

function pruneEmpty(value: unknown): unknown {
  if (Array.isArray(value)) {
    const rows = value.map(pruneEmpty).filter((item) => {
      if (Array.isArray(item)) return item.length > 0
      if (isRecord(item)) return Object.keys(item).length > 0
      return item !== '' && item !== undefined && item !== null
    })
    return rows
  }
  if (isRecord(value)) {
    const out: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value)) {
      const cleaned = pruneEmpty(item)
      if (cleaned === '' || cleaned === undefined || cleaned === null) continue
      if (Array.isArray(cleaned) && !cleaned.length) continue
      if (isRecord(cleaned) && !Object.keys(cleaned).length) continue
      out[key] = cleaned
    }
    return out
  }
  return value
}

function cleanConfig(): Record<string, unknown> {
  const config = deepClone(draft.config)
  config.items = cleanRows(config.items, 'key')
  config.stats = cleanRows(config.stats, 'label')
  return pruneEmpty(config) as Record<string, unknown>
}

function cleanSource(): DataSource {
  const source = deepClone(draft.data_source) as DataSource
  source.type = sourceType.value
  if (!source.entity_id && typeof source.entity === 'string') source.entity_id = source.entity
  delete source.entity

  if (source.type === 'static') {
    return { type: 'static' }
  }

  const sourceMappings = isRecord(source.mappings) ? source.mappings : {}
  sourceMappings.items = cleanRows(sourceMappings.items, 'key')
  sourceMappings.stats = cleanRows(sourceMappings.stats, 'label')
  source.mappings = pruneEmpty(sourceMappings) as Record<string, unknown>

  if (isRecord(source.auth) && source.auth.type === 'none') {
    delete source.auth
  }
  return pruneEmpty(source) as DataSource
}

/** Assemble a clean payload from the draft for create/update. */
function payload(): Partial<Panel> {
  return {
    id: draft.id.trim(),
    title: draft.title.trim(),
    layout: draft.layout,
    config: cleanConfig(),
    data_source: cleanSource(),
  }
}

function previewPayload(): Partial<Panel> {
  const body = payload()
  const config = { ...(body.config ?? {}) }
  if (body.data_source?.type === 'static') {
    if (draft.layout === 'big_number' && !config.value) {
      config.value = '42'
    } else if (draft.layout === 'key_value' && !Array.isArray(config.items)) {
      config.items = [{ key: 'Label', value: 'Value' }]
    } else if (draft.layout === 'marquee' && !config.text) {
      config.text = 'Preview text'
    } else if (draft.layout === 'multi_stat' && !Array.isArray(config.stats)) {
      config.stats = [{ label: 'Stat', value: '0', color: '#ffffff' }]
    } else if (draft.layout === 'sparkline' && !Array.isArray(config.points)) {
      config.points = [2, 4, 3, 7, 6, 9, 8]
    }
  }
  body.config = config
  return body
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
  draft.data_source = { type: 'static' }
}

function editPanel(p: Panel) {
  editingId.value = p.id
  previewUrl.value = ''
  error.value = ''
  draft.id = p.id
  draft.title = p.title
  draft.layout = p.layout
  draft.config = deepClone(p.config ?? {})
  draft.data_source = normalizeDataSource(p.data_source)
  ensureLayoutDefaults()
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
    const res = await api.previewPanel(previewPayload())
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
    <p class="mb-1 text-[11px] uppercase tracking-[0.22em] text-ember">Panels</p>
    <h2 class="mb-5 text-xl font-bold text-core">Panel Builder</h2>

    <p v-if="error" class="mb-4 text-[11px] text-[#ff6a4a]">{{ error }}</p>

    <div class="grid gap-5 lg:grid-cols-[32rem_minmax(0,1fr)]">
      <!-- editor -->
      <section class="rounded border border-[#3a2016] bg-panel p-3">
        <div class="mb-3 flex items-center justify-between">
          <p class="text-[10px] uppercase tracking-[0.18em] text-dim">
            {{ isEditing ? 'Edit Panel' : 'New Panel' }}
          </p>
          <button :class="ghostButtonClass" @click="resetForm">
            {{ isEditing ? 'Cancel' : 'New' }}
          </button>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Id</label>
            <input
              v-model="draft.id"
              type="text"
              placeholder="weather"
              :disabled="isEditing"
              :class="inputClass"
            />
          </div>
          <div>
            <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Title</label>
            <input v-model="draft.title" type="text" placeholder="Weather" :class="inputClass" />
          </div>
        </div>

        <div class="mt-3 grid grid-cols-[1fr_1fr_auto] gap-3">
          <div>
            <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Layout</label>
            <select :value="draft.layout" :class="inputClass" @change="setLayout">
              <option v-for="layout in LAYOUTS" :key="layout.value" :value="layout.value">
                {{ layout.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Data Source</label>
            <select :value="sourceType" :class="inputClass" @change="setSourceType">
              <option v-for="source in SOURCES" :key="source.value" :value="source.value">
                {{ source.label }}
              </option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Color</label>
            <input
              type="color"
              :value="configColor('color')"
              class="h-8 w-12 rounded border border-[#3a2016] bg-[#120a10] p-0.5"
              @input="setConfigValue('color', $event)"
            />
          </div>
        </div>

        <div class="mt-4 border-t border-[#1c0e14] pt-3">
          <p class="mb-2 text-[10px] uppercase tracking-[0.18em] text-dim">Source</p>

          <template v-if="sourceType === 'http'">
            <div class="grid gap-3">
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Url</label>
                <input
                  :value="sourceString('url')"
                  type="text"
                  placeholder="https://api.example.com/data.json"
                  :class="inputClass"
                  @input="setSourceValue('url', $event)"
                />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">TTL</label>
                  <input
                    :value="sourceNumber('ttl', 300)"
                    type="number"
                    min="10"
                    :class="inputClass"
                    @input="setSourceNumber('ttl', $event, 300)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Auth</label>
                  <select :value="authType()" :class="inputClass" @change="setAuthType">
                    <option v-for="auth in AUTH_TYPES" :key="auth.value" :value="auth.value">
                      {{ auth.label }}
                    </option>
                  </select>
                </div>
              </div>
              <div v-if="authType() === 'bearer'">
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Token</label>
                <input
                  :value="recordString(authRecord(), 'token')"
                  type="text"
                  autocomplete="off"
                  data-1p-ignore
                  :class="inputClass"
                  @input="setAuthValue('token', $event)"
                />
              </div>
              <div v-else-if="authType() === 'api_key'" class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Header</label>
                  <input
                    :value="recordString(authRecord(), 'header', 'X-API-Key')"
                    type="text"
                    :class="inputClass"
                    @input="setAuthValue('header', $event)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Key</label>
                  <input
                    :value="recordString(authRecord(), 'token')"
                    type="text"
                    autocomplete="off"
                    data-1p-ignore
                    :class="inputClass"
                    @input="setAuthValue('token', $event)"
                  />
                </div>
              </div>
              <div v-else-if="authType() === 'basic'" class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Username</label>
                  <input
                    :value="recordString(authRecord(), 'username')"
                    type="text"
                    autocomplete="off"
                    data-1p-ignore
                    :class="inputClass"
                    @input="setAuthValue('username', $event)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Password</label>
                  <input
                    :value="recordString(authRecord(), 'password')"
                    type="password"
                    autocomplete="off"
                    data-1p-ignore
                    :class="inputClass"
                    @input="setAuthValue('password', $event)"
                  />
                </div>
              </div>
            </div>
          </template>

          <template v-else-if="sourceType === 'mqtt'">
            <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Topic</label>
            <input
              :value="sourceString('topic')"
              type="text"
              placeholder="sensors/livingroom/temp"
              :class="inputClass"
              @input="setSourceValue('topic', $event)"
            />
          </template>

          <template v-else-if="sourceType === 'ha'">
            <div class="grid grid-cols-[1fr_7rem] gap-3">
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Entity ID</label>
                <input
                  :value="sourceString('entity_id')"
                  type="text"
                  placeholder="sensor.living_room_temperature"
                  :class="inputClass"
                  @input="setSourceValue('entity_id', $event)"
                />
              </div>
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">TTL</label>
                <input
                  :value="sourceNumber('ttl', 60)"
                  type="number"
                  min="5"
                  :class="inputClass"
                  @input="setSourceNumber('ttl', $event, 60)"
                />
              </div>
            </div>
          </template>

          <template v-else>
            <p class="text-[11px] uppercase tracking-wider text-muted">
              Values are stored directly in this panel.
            </p>
          </template>
        </div>

        <div class="mt-4 border-t border-[#1c0e14] pt-3">
          <p class="mb-2 text-[10px] uppercase tracking-[0.18em] text-dim">
            {{ layoutLabel(draft.layout) }}
          </p>

          <template v-if="draft.layout === 'big_number'">
            <div class="grid gap-3" :class="isMappedSource ? 'grid-cols-2' : 'grid-cols-[1fr_7rem]'">
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">
                  {{ isStaticSource ? 'Value' : 'Value Path' }}
                </label>
                <input
                  v-if="isStaticSource"
                  :value="configString('value')"
                  type="text"
                  placeholder="72"
                  :class="inputClass"
                  @input="setConfigValue('value', $event)"
                />
                <input
                  v-else
                  :value="mappingString('value')"
                  type="text"
                  :placeholder="sourceType === 'ha' ? 'state' : 'data.temperature'"
                  :class="inputClass"
                  @input="setMappingValue('value', $event)"
                />
              </div>
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Unit</label>
                <input
                  :value="configString('unit')"
                  type="text"
                  placeholder="F"
                  :class="inputClass"
                  @input="setConfigValue('unit', $event)"
                />
              </div>
              <div v-if="isMappedSource" class="col-span-2">
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Transform</label>
                <input
                  :value="mappingString('transform')"
                  type="text"
                  placeholder="/ 100 | round 2 | format $%.2f"
                  :class="inputClass"
                  @input="setMappingValue('transform', $event)"
                />
              </div>
            </div>
          </template>

          <template v-else-if="draft.layout === 'marquee'">
            <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">
              {{ isStaticSource ? 'Text' : 'Text Path' }}
            </label>
            <input
              v-if="isStaticSource"
              :value="configString('text')"
              type="text"
              placeholder="Scrolling message"
              :class="inputClass"
              @input="setConfigValue('text', $event)"
            />
            <div v-else class="grid gap-3">
              <input
                :value="mappingString('text')"
                type="text"
                placeholder="data.headline"
                :class="inputClass"
                @input="setMappingValue('text', $event)"
              />
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Transform</label>
                <input
                  :value="mappingString('transform')"
                  type="text"
                  placeholder="prefix Alert: "
                  :class="inputClass"
                  @input="setMappingValue('transform', $event)"
                />
              </div>
            </div>
          </template>

          <template v-else-if="draft.layout === 'key_value'">
            <div class="space-y-2">
              <div
                v-for="(item, index) in isStaticSource ? staticItems() : mappedItems()"
                :key="index"
                class="grid items-center gap-2"
                :class="isStaticSource ? 'grid-cols-[1fr_1fr_auto]' : 'grid-cols-[1fr_1fr_0.8fr_4rem_auto]'"
              >
                <input v-model="item.key" type="text" placeholder="Label" :class="miniInputClass" />
                <input
                  v-if="isStaticSource"
                  v-model="item.value"
                  type="text"
                  placeholder="Value"
                  :class="miniInputClass"
                />
                <input
                  v-else
                  v-model="item.value_path"
                  type="text"
                  placeholder="json.path"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="item.transform"
                  type="text"
                  placeholder="transform"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="item.unit"
                  type="text"
                  placeholder="unit"
                  :class="miniInputClass"
                />
                <button :class="ghostButtonClass" @click="removeItemRow(index)">Remove</button>
              </div>
            </div>
            <button class="mt-2" :class="ghostButtonClass" @click="addItemRow">Add Row</button>
          </template>

          <template v-else-if="draft.layout === 'multi_stat'">
            <div class="space-y-2">
              <div
                v-for="(stat, index) in isStaticSource ? staticStats() : mappedStats()"
                :key="index"
                class="grid items-center gap-2"
                :class="isStaticSource ? 'grid-cols-[1fr_1fr_3rem_auto]' : 'grid-cols-[1fr_1fr_0.8fr_4rem_3rem_auto]'"
              >
                <input v-model="stat.label" type="text" placeholder="Label" :class="miniInputClass" />
                <input
                  v-if="isStaticSource"
                  v-model="stat.value"
                  type="text"
                  placeholder="Value"
                  :class="miniInputClass"
                />
                <input
                  v-else
                  v-model="stat.value_path"
                  type="text"
                  placeholder="json.path"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="stat.transform"
                  type="text"
                  placeholder="transform"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="stat.unit"
                  type="text"
                  placeholder="unit"
                  :class="miniInputClass"
                />
                <input
                  v-model="stat.color"
                  type="color"
                  class="h-8 w-12 rounded border border-[#3a2016] bg-[#120a10] p-0.5"
                />
                <button :class="ghostButtonClass" @click="removeStatRow(index)">Remove</button>
              </div>
            </div>
            <button class="mt-2" :class="ghostButtonClass" @click="addStatRow">Add Stat</button>
          </template>

          <template v-else-if="draft.layout === 'sparkline'">
            <div v-if="isStaticSource" class="grid gap-3">
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Points</label>
                <input
                  :value="Array.isArray(draft.config.points) ? draft.config.points.join(', ') : configString('points')"
                  type="text"
                  placeholder="2, 4, 3, 7, 6, 9, 8"
                  :class="inputClass"
                  @input="
                    draft.config.points = inputValue($event)
                      .split(',')
                      .map((p) => Number(p.trim()))
                      .filter((p) => Number.isFinite(p))
                  "
                />
              </div>
            </div>
            <div v-else class="grid gap-3">
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Points Path</label>
                <input
                  :value="mappingString('points')"
                  type="text"
                  placeholder="daily_mrr"
                  :class="inputClass"
                  @input="setMappingValue('points', $event)"
                />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Point Value</label>
                  <input
                    :value="mappingString('point_value')"
                    type="text"
                    placeholder="mrr_cents"
                    :class="inputClass"
                    @input="setMappingValue('point_value', $event)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Point Transform</label>
                  <input
                    :value="mappingString('point_transform')"
                    type="text"
                    placeholder="/ 100"
                    :class="inputClass"
                    @input="setMappingValue('point_transform', $event)"
                  />
                </div>
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Current Path</label>
                  <input
                    :value="mappingString('value')"
                    type="text"
                    placeholder="mrr_cents"
                    :class="inputClass"
                    @input="setMappingValue('value', $event)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Current Transform</label>
                  <input
                    :value="mappingString('transform')"
                    type="text"
                    placeholder="/ 100 | round 0 | format $%d"
                    :class="inputClass"
                    @input="setMappingValue('transform', $event)"
                  />
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="mt-4 border-t border-[#1c0e14] pt-3">
          <p class="mb-2 text-[10px] uppercase tracking-[0.18em] text-dim">Colors</p>
          <div class="grid grid-cols-5 gap-2">
            <label v-for="field in COLOR_FIELDS" :key="field.key" class="text-[10px] uppercase tracking-[0.12em] text-muted">
              {{ field.label }}
              <input
                type="color"
                :value="configColor(field.key)"
                class="mt-1 h-8 w-full rounded border border-[#3a2016] bg-[#120a10] p-0.5"
                @input="setConfigValue(field.key, $event)"
              />
            </label>
          </div>
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-2">
          <button :class="ghostButtonClass" :disabled="previewing" @click="doPreview">
            {{ previewing ? 'Rendering...' : 'Preview' }}
          </button>
          <button
            class="rounded border border-[#3a2016] bg-flame px-2.5 py-1 text-[11px] uppercase tracking-wider text-[#160a0a] disabled:opacity-60"
            :disabled="saving"
            @click="save"
          >
            {{ saving ? 'Saving...' : isEditing ? 'Save' : 'Create' }}
          </button>
          <span class="text-[10px] uppercase tracking-wider text-muted">
            {{ sourceLabel(sourceType) }}
          </span>
        </div>

        <!-- CRT preview bezel -->
        <div v-if="previewUrl" class="mt-4 flex flex-col items-center gap-2">
          <p class="text-[10px] uppercase tracking-[0.18em] text-dim">Preview</p>
          <div class="rounded-lg border-2 border-[#24121c] bg-black p-1.5" style="box-shadow: inset 0 0 20px #3a0f06">
            <img class="h-40 w-40 object-contain" :src="previewUrl" alt="panel preview" />
          </div>
        </div>
      </section>

      <!-- list -->
      <section>
        <div class="mb-2 flex items-center justify-between">
          <p class="text-[10px] uppercase tracking-[0.18em] text-dim">Panels · {{ panels.length }}</p>
          <button :class="ghostButtonClass" @click="load">Refresh</button>
        </div>

        <p v-if="loading" class="text-[11px] uppercase tracking-wider text-dim">Loading panels...</p>
        <p v-else-if="!panels.length" class="text-[11px] uppercase tracking-wider text-dim">
          No panels yet. Create one on the left.
        </p>

        <div v-else class="grid gap-3 sm:grid-cols-2">
          <div
            v-for="panel in panels"
            :key="panel.id"
            class="rounded border border-[#3a2016] bg-panel p-3"
            :class="{ 'border-flame': editingId === panel.id }"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="break-all text-sm text-gold">{{ panel.id }}</span>
              <span class="shrink-0 rounded border border-[#3a2016] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-dim">
                {{ layoutLabel(panel.layout) }}
              </span>
            </div>
            <p class="mt-1 truncate text-xs text-core">{{ panel.title || '-' }}</p>
            <p class="mt-0.5 text-[10px] uppercase tracking-wider text-muted">
              {{ panel.data_source.type ?? 'static' }}
            </p>
            <div class="mt-3 flex items-center gap-2">
              <button :class="ghostButtonClass" @click="editPanel(panel)">Edit</button>
              <button
                class="rounded border border-[#3a2016] px-2.5 py-1 text-[11px] uppercase tracking-wider text-[#ff6a4a] hover:bg-[#251009]"
                @click="del(panel.id)"
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
