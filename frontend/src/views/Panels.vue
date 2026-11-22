<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '@/api/client'
import type { Panel, PanelLayout, DataSource } from '@/api/types'

type SourceType = NonNullable<DataSource['type']>
type AuthType = 'none' | 'bearer' | 'api_key' | 'basic'
type DraftRow = Record<string, string>

interface LayoutOption {
  value: PanelLayout
  label: string
  short: string
  hint: string
}

interface LedSwatch {
  name: string
  hex: string
}

interface StarterTemplate {
  key: string
  name: string
  badge: string
  id: string
  title: string
  layout: PanelLayout
  config: Record<string, unknown>
  data_source: DataSource
}

const LAYOUTS: LayoutOption[] = [
  { value: 'big_number', label: 'Big Number', short: 'KPI', hint: 'Hero figure + delta & progress' },
  { value: 'sparkline', label: 'Sparkline', short: 'Trend', hint: 'Shaded curve + live value' },
  { value: 'multi_stat', label: 'Multi Stat', short: '2×2', hint: 'Structured dark metric tiles' },
  { value: 'key_value', label: 'Key / Value', short: 'Table', hint: 'Banded telemetry rows' },
  { value: 'marquee', label: 'Marquee', short: 'Ticker', hint: 'Framed scrolling feed' },
]

const SOURCES: { value: SourceType; label: string; badge: string }[] = [
  { value: 'static', label: 'Static', badge: 'STATIC' },
  { value: 'http', label: 'HTTP JSON', badge: 'HTTP' },
  { value: 'ha', label: 'Home Assistant', badge: 'HA' },
  { value: 'mqtt', label: 'MQTT', badge: 'MQTT' },
]

const AUTH_TYPES: { value: AuthType; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'bearer', label: 'Bearer token' },
  { value: 'api_key', label: 'API key header' },
  { value: 'basic', label: 'Basic auth' },
]

const LED_SWATCHES: LedSwatch[] = [
  { name: 'Ember', hex: '#FF8E3C' },
  { name: 'Cyan', hex: '#5BCEFA' },
  { name: 'Emerald', hex: '#2EE58D' },
  { name: 'Violet', hex: '#BA8AFF' },
  { name: 'Gold', hex: '#FFD98A' },
  { name: 'Coral', hex: '#FF5E57' },
]

const COLOR_FIELDS: { key: string; label: string; fallback: string }[] = [
  { key: 'color', label: 'Primary', fallback: '#5bcefa' },
  { key: 'accent_color', label: 'Accent', fallback: '#ff8e3c' },
  { key: 'title_color', label: 'Title', fallback: '#a8b8d0' },
  { key: 'label_color', label: 'Label', fallback: '#7a8ca8' },
  { key: 'key_color', label: 'Key', fallback: '#7a8ca8' },
  { key: 'value_color', label: 'Value', fallback: '#f4f7fc' },
]

const STARTER_TEMPLATES: StarterTemplate[] = [
  {
    key: 'homelab',
    name: 'Homelab',
    badge: '2×2',
    id: 'homelab_stats',
    title: 'HOMELAB',
    layout: 'multi_stat',
    config: {
      accent_color: '#5BCEFA',
      stats: [
        { label: 'CPU', value: '28%', color: '#5BCEFA' },
        { label: 'RAM', value: '62%', color: '#FF9E3D' },
        { label: 'TEMP', value: '51°', color: '#2EE58D' },
        { label: 'UP', value: '42d', color: '#BA8AFF' },
      ],
    },
    data_source: { type: 'static' },
  },
  {
    key: 'latency',
    name: 'API P95',
    badge: 'Trend',
    id: 'api_latency',
    title: 'API P95',
    layout: 'sparkline',
    config: {
      color: '#5BCEFA',
      value: '42ms',
      delta: '-14%',
      delta_color: '#2EE58D',
      subtitle: '24H',
      fill: true,
      show_minmax: true,
      points: [64, 58, 61, 55, 49, 52, 47, 51, 44, 46, 40, 43, 39, 45, 41, 42],
    },
    data_source: { type: 'static' },
  },
  {
    key: 'kpi',
    name: 'Daily KPI',
    badge: 'KPI',
    id: 'active_users',
    title: 'ACTIVE USERS',
    layout: 'big_number',
    config: {
      value: '12.4',
      unit: 'k',
      delta: '+18.6%',
      progress: 78,
      color: '#FFF2CF',
      accent_color: '#FF8E3C',
    },
    data_source: { type: 'static' },
  },
  {
    key: 'climate',
    name: 'Climate',
    badge: 'Table',
    id: 'home_climate_table',
    title: 'CLIMATE',
    layout: 'key_value',
    config: {
      color: '#2EE58D',
      items: [
        { key: 'Living', value: '22° 44%', color: '#2EE58D' },
        { key: 'Office', value: '23° 41%', color: '#5BCEFA' },
        { key: 'Bedrm', value: '19° 48%', color: '#BA8AFF' },
        { key: 'Studio', value: '21° 45%', color: '#FF9E3D' },
      ],
    },
    data_source: { type: 'static' },
  },
  {
    key: 'ticker',
    name: 'Ticker',
    badge: 'Feed',
    id: 'deploy_feed',
    title: 'DEPLOY FEED',
    layout: 'marquee',
    config: {
      text: 'v2.4.1 LIVE · ALL REGIONS GREEN',
      subtitle: 'PROD CLUSTER',
      color: '#FFD98A',
      accent_color: '#FF9E3D',
    },
    data_source: { type: 'static' },
  },
]

const inputClass =
  'w-full rounded border border-[#3a2016] bg-[#120a10] px-2.5 py-1.5 text-xs text-core placeholder:text-[#6f4938] focus:border-flame focus:outline-none disabled:text-[#7a4a34]'
const miniInputClass =
  'min-w-0 rounded border border-[#3a2016] bg-[#120a10] px-2 py-1.5 text-xs text-core placeholder:text-[#6f4938] focus:border-flame focus:outline-none'
const ghostButtonClass =
  'rounded border border-[#3a2016] px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-gold transition-colors hover:bg-[#251009] disabled:opacity-45'

const panels = ref<Panel[]>([])
const loading = ref(false)
const saving = ref(false)
const previewing = ref(false)
const error = ref('')
const note = ref('')
const previewUrl = ref('')
const previewBroken = ref(false)
const previewSubject = ref('draft')
const activeTemplateKey = ref<string | null>(null)
const showCustomColors = ref(false)

/** null = creating a new panel; otherwise the id being edited. */
const editingId = ref<string | null>(null)

const draft = reactive<{
  id: string
  title: string
  layout: PanelLayout
  config: Record<string, unknown>
  data_source: DataSource
  skip_when_unhealthy: boolean
}>({
  id: '',
  title: '',
  layout: 'sparkline',
  config: {
    color: '#5BCEFA',
    points: [22, 28, 25, 34, 31, 42, 38, 46, 44, 52],
    fill: true,
    show_minmax: true,
  },
  data_source: { type: 'static' },
  skip_when_unhealthy: false,
})

const isEditing = computed(() => editingId.value !== null)
const sourceType = computed<SourceType>(() => draft.data_source.type ?? 'static')
const isStaticSource = computed(() => sourceType.value === 'static')
const isMappedSource = computed(() => !isStaticSource.value)
const activePrimaryColor = computed(() => {
  const c = configString('accent_color') || configString('color')
  return /^#[0-9a-f]{6}$/i.test(c) ? c.toUpperCase() : ''
})
const hasCustomColors = computed(() => COLOR_FIELDS.some((f) => Boolean(configString(f.key))))
const monitorStatus = computed(() => {
  if (previewing.value) return { label: 'Rendering…', tone: 'flame' as const }
  if (previewUrl.value && !previewBroken.value) {
    return isEditing.value
      ? { label: `Editing · ${editingId.value}`, tone: 'emerald' as const }
      : { label: `Live Preview · ${previewSubject.value}`, tone: 'emerald' as const }
  }
  return { label: 'Ready', tone: 'dim' as const }
})

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

function sourceBadge(value: SourceType | undefined): string {
  return SOURCES.find((s) => s.value === (value ?? 'static'))?.badge ?? 'STATIC'
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

function configBool(key: string, fallback: boolean): boolean {
  const value = draft.config[key]
  return typeof value === 'boolean' ? value : fallback
}

function mappingString(key: string, fallback = ''): string {
  return recordString(mappings(), key, fallback)
}

function configColor(key: string, fallback = '#ffffff'): string {
  const value = configString(key)
  return /^#[0-9a-f]{6}$/i.test(value) ? value : fallback
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

function setSourceOptionalNumber(key: string, event: Event): void {
  const raw = inputValue(event).trim()
  if (!raw) {
    delete draft.data_source[key]
    return
  }
  const parsed = Number(raw)
  if (Number.isFinite(parsed) && parsed > 0) {
    draft.data_source[key] = parsed
  } else {
    delete draft.data_source[key]
  }
}

function setConfigValue(key: string, event: Event): void {
  setRecordValue(draft.config, key, inputValue(event))
}

function setConfigOptionalNumber(key: string, event: Event): void {
  const raw = inputValue(event).trim()
  if (!raw) {
    delete draft.config[key]
    return
  }
  const parsed = Number(raw)
  if (Number.isFinite(parsed)) {
    draft.config[key] = Math.max(0, Math.min(100, parsed))
  } else {
    delete draft.config[key]
  }
}

function setConfigBool(key: string, event: Event): void {
  draft.config[key] = (event.target as HTMLInputElement).checked
}

function setMappingValue(key: string, event: Event): void {
  setRecordValue(mappings(), key, inputValue(event))
}

function applyPaletteSwatch(hex: string): void {
  if (draft.layout === 'big_number') {
    draft.config.accent_color = hex
    if (!draft.config.color) draft.config.color = '#FFF2CF'
  } else {
    draft.config.color = hex
    draft.config.accent_color = hex
  }
  if (previewUrl.value) {
    void doPreview()
  }
}

function resetColors(): void {
  for (const field of COLOR_FIELDS) {
    delete draft.config[field.key]
  }
  delete draft.config.delta_color
  if (previewUrl.value) {
    void doPreview()
  }
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
    if (current.has_token) next.has_token = true
  } else if (value === 'basic') {
    next.username = recordString(current, 'username')
    next.password = recordString(current, 'password')
    if (current.has_password) next.has_password = true
  } else {
    next.token = recordString(current, 'token')
    if (current.has_token) next.has_token = true
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
  return ensureRows(draft.config, 'items', { key: '', value: '', color: '#5bcefa' })
}

function mappedItems(): DraftRow[] {
  return ensureRows(mappings(), 'items', { key: '', value_path: '', transform: '', unit: '', color: '#5bcefa' })
}

function staticStats(): DraftRow[] {
  return ensureRows(draft.config, 'stats', { label: '', value: '', color: '#5bcefa' })
}

function mappedStats(): DraftRow[] {
  return ensureRows(mappings(), 'stats', {
    label: '',
    value_path: '',
    transform: '',
    unit: '',
    color: '#5bcefa',
  })
}

function addItemRow(): void {
  const rows = isStaticSource.value ? staticItems() : mappedItems()
  const palette = LED_SWATCHES[rows.length % LED_SWATCHES.length].hex
  rows.push(
    isStaticSource.value
      ? { key: '', value: '', color: palette }
      : { key: '', value_path: '', transform: '', unit: '', color: palette },
  )
}

function removeItemRow(index: number): void {
  const rows = isStaticSource.value ? staticItems() : mappedItems()
  rows.splice(index, 1)
  if (!rows.length) addItemRow()
}

function addStatRow(): void {
  const rows = isStaticSource.value ? staticStats() : mappedStats()
  const palette = LED_SWATCHES[rows.length % LED_SWATCHES.length].hex
  rows.push(
    isStaticSource.value
      ? { label: '', value: '', color: palette }
      : { label: '', value_path: '', transform: '', unit: '', color: palette },
  )
}

function removeStatRow(index: number): void {
  const rows = isStaticSource.value ? staticStats() : mappedStats()
  rows.splice(index, 1)
  if (!rows.length) addStatRow()
}

function selectLayout(nextLayout: PanelLayout): void {
  draft.layout = nextLayout
  activeTemplateKey.value = null
  ensureLayoutDefaults()
  if (previewUrl.value) {
    void doPreview()
  }
}

function selectSourceType(value: SourceType): void {
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

  if (value !== 'static') {
    if (previous.stale_after !== undefined) next.stale_after = previous.stale_after
    if (typeof previous.timestamp_path === 'string' && previous.timestamp_path) {
      next.timestamp_path = previous.timestamp_path
    }
  }

  draft.data_source = next
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
    draft.config.points = [22, 28, 25, 34, 31, 42, 38, 46, 44, 52]
  }
}

function applyTemplate(tpl: StarterTemplate): void {
  editingId.value = null
  activeTemplateKey.value = tpl.key
  error.value = ''
  note.value = `Loaded "${tpl.name}" starter template`
  draft.id = tpl.id
  draft.title = tpl.title
  draft.layout = tpl.layout
  draft.config = deepClone(tpl.config)
  draft.data_source = normalizeDataSource(tpl.data_source)
  draft.skip_when_unhealthy = false
  previewSubject.value = tpl.id
  void doPreview()
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
    return value.map(pruneEmpty).filter((item) => {
      if (Array.isArray(item)) return item.length > 0
      if (isRecord(item)) return Object.keys(item).length > 0
      return item !== '' && item !== undefined && item !== null
    })
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
    skip_when_unhealthy: draft.skip_when_unhealthy,
  }
}

function previewPayload(): Partial<Panel> {
  const body = payload()
  const config = { ...(body.config ?? {}) }
  if (body.data_source?.type === 'static') {
    if (draft.layout === 'big_number' && !config.value) {
      config.value = '42'
    } else if (draft.layout === 'key_value' && !Array.isArray(config.items)) {
      config.items = [
        { key: 'Node', value: 'ONLINE', color: '#2EE58D' },
        { key: 'Load', value: '0.42', color: '#5BCEFA' },
      ]
    } else if (draft.layout === 'marquee' && !config.text) {
      config.text = 'SYSTEM NOMINAL · ALL SERVICES HEALTHY'
    } else if (draft.layout === 'multi_stat' && !Array.isArray(config.stats)) {
      config.stats = [
        { label: 'CPU', value: '28%', color: '#5BCEFA' },
        { label: 'RAM', value: '62%', color: '#FF9E3D' },
      ]
    } else if (draft.layout === 'sparkline' && !Array.isArray(config.points)) {
      config.points = [22, 28, 25, 34, 31, 42, 38, 46, 44, 52]
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
  activeTemplateKey.value = null
  error.value = ''
  note.value = ''
  draft.id = ''
  draft.title = ''
  draft.layout = 'big_number'
  draft.config = {}
  draft.data_source = { type: 'static' }
  draft.skip_when_unhealthy = false
  previewSubject.value = 'draft'
  previewUrl.value = ''
}

function editPanel(p: Panel, autoPreview = true) {
  editingId.value = p.id
  activeTemplateKey.value = null
  error.value = ''
  note.value = ''
  draft.id = p.id
  draft.title = p.title
  draft.layout = p.layout
  draft.config = deepClone(p.config ?? {})
  draft.data_source = normalizeDataSource(p.data_source)
  draft.skip_when_unhealthy = Boolean(p.skip_when_unhealthy)
  previewSubject.value = p.id
  ensureLayoutDefaults()
  if (autoPreview) {
    void doPreview()
  }
}

async function previewSavedPanel(p: Panel) {
  previewing.value = true
  error.value = ''
  previewBroken.value = false
  previewSubject.value = p.id
  try {
    const res = await api.previewPanel({
      id: p.id,
      title: p.title,
      layout: p.layout,
      config: p.config,
      data_source: p.data_source,
    })
    if (res.error) {
      error.value = res.error
    } else if (res.preview_url) {
      previewUrl.value = res.preview_url
      note.value = `Previewed ${p.id}`
    }
  } catch {
    error.value = `Failed to preview panel "${p.id}".`
  } finally {
    previewing.value = false
  }
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
  previewBroken.value = false
  previewSubject.value = draft.id.trim() || draft.title.trim() || 'draft'
  try {
    const res = await api.previewPanel(previewPayload())
    if (res.error) {
      error.value = res.error
    } else if (res.preview_url) {
      previewUrl.value = res.preview_url
    } else {
      error.value = 'Preview returned no image.'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Preview request failed.'
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
    const savedId = body.id || editingId.value || ''
    const result = isEditing.value
      ? await api.updatePanel(editingId.value as string, body)
      : await api.createPanel(body)
    if ('error' in result) {
      error.value = result.error
      return
    }
    note.value = isEditing.value ? `Saved ${savedId}` : `Created ${savedId}`
    await load()
    const fresh = panels.value.find((p) => p.id === savedId)
    if (fresh) {
      editPanel(fresh, true)
    } else {
      resetForm()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to save panel.'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await load()
  if (panels.value.length > 0) {
    editPanel(panels.value[0], true)
  } else {
    applyTemplate(STARTER_TEMPLATES[1])
  }
})
</script>

<template>
  <div>
    <!-- Page header -->
    <div class="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="mb-1 text-[11px] uppercase tracking-[0.22em] text-ember">Panels</p>
        <h2 class="text-xl font-bold text-core">Panel Builder Studio</h2>
      </div>
      <div class="flex items-center gap-2">
        <button :class="ghostButtonClass" @click="resetForm">+ New blank</button>
        <button :class="ghostButtonClass" :disabled="previewing" @click="doPreview">
          {{ previewing ? 'Rendering…' : '⟳ Render Preview' }}
        </button>
        <button
          class="rounded bg-flame px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-[#160a0a] transition-opacity hover:opacity-90 disabled:opacity-50"
          :disabled="saving"
          @click="save"
        >
          {{ saving ? 'Saving…' : isEditing ? 'Save Panel' : 'Create Panel' }}
        </button>
      </div>
    </div>

    <div
      v-if="error"
      role="alert"
      class="mb-4 rounded border border-[#b3241a] bg-[#1e0a0e] px-3 py-2 text-xs text-[#ff7b5c]"
    >
      ▲ {{ error }}
    </div>

    <!-- Split-Pane Studio -->
    <div class="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <!-- LEFT STAGE (sticky on desktop): CRT Monitor + Templates + Saved Roster -->
      <aside class="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        <!-- Glowing 64x64 CRT Monitor -->
        <div
          class="relative rounded-2xl border-2 border-[#24121c] bg-[#0a0508] p-2.5"
          style="box-shadow: inset 0 0 26px #3a0f06, inset 0 0 0 2px #1c0e14, 0 0 30px -8px rgba(255, 90, 42, 0.4)"
        >
          <div class="relative aspect-square overflow-hidden rounded-lg bg-black">
            <img
              v-if="previewUrl && !previewBroken"
              :src="previewUrl"
              alt="64x64 panel preview"
              class="px h-full w-full object-contain"
              @error="previewBroken = true"
            />
            <div v-else class="grid h-full w-full place-items-center px-6 text-center">
              <div>
                <div class="text-[11px] uppercase tracking-widest text-dim">
                  {{ previewing ? 'rendering 64×64…' : 'no signal' }}
                </div>
                <button
                  v-if="!previewing"
                  class="mt-3 rounded border border-[#3a2016] px-3 py-1 text-[11px] uppercase tracking-wider text-flame hover:bg-[#251009]"
                  @click="doPreview"
                >
                  ⟳ Render preview
                </button>
              </div>
            </div>
            <!-- CRT scanline overlay -->
            <div
              class="pointer-events-none absolute inset-0"
              style="background: repeating-linear-gradient(0deg, transparent 0 2px, rgba(0, 0, 0, 0.28) 2px 3px); mix-blend-mode: multiply"
            ></div>
          </div>
        </div>

        <!-- Monitor status & instant preview bar -->
        <div class="flex flex-wrap items-center justify-between gap-2 rounded border border-[#3a2016] bg-panel px-3 py-2 text-[10px] uppercase tracking-[0.15em]">
          <div class="flex min-w-0 items-center gap-2">
            <span
              class="h-2 w-2 shrink-0 rounded-full"
              :class="
                monitorStatus.tone === 'emerald'
                  ? 'bg-[#2ee58d]'
                  : monitorStatus.tone === 'flame'
                    ? 'bg-flame blink'
                    : 'bg-[#7a4a34]'
              "
              :style="
                monitorStatus.tone === 'emerald'
                  ? 'box-shadow: 0 0 8px #2ee58d'
                  : monitorStatus.tone === 'flame'
                    ? 'box-shadow: 0 0 8px #ff9e3d'
                    : ''
              "
            ></span>
            <span class="truncate text-gold">{{ monitorStatus.label }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="rounded border border-[#3a2016] bg-[#120a10] px-1.5 py-0.5 text-[9px] text-dim">
              64×64 · {{ layoutLabel(draft.layout) }}
            </span>
          </div>
        </div>

        <p v-if="note" class="-mt-2 px-1 text-[10px] uppercase tracking-[0.14em] text-[#c78a5a]">
          {{ note }}
        </p>

        <!-- Starter Templates Strip -->
        <section class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>Starter Templates</span>
            <span class="text-muted">1-click</span>
          </div>
          <div class="grid grid-cols-5 gap-1.5">
            <button
              v-for="tpl in STARTER_TEMPLATES"
              :key="tpl.key"
              type="button"
              class="flex flex-col items-center rounded border px-1 py-1.5 text-center transition-colors"
              :class="
                activeTemplateKey === tpl.key
                  ? 'border-flame bg-[#251009] text-core'
                  : 'border-[#2a1620] bg-[#120a10] text-dim hover:border-[#523022] hover:text-gold'
              "
              :title="`Load ${tpl.name} (${tpl.layout}) template`"
              @click="applyTemplate(tpl)"
            >
              <span class="text-[9px] font-bold uppercase tracking-wider text-flame">{{ tpl.badge }}</span>
              <span class="mt-0.5 truncate text-[9px] tracking-wide">{{ tpl.name }}</span>
            </button>
          </div>
        </section>

        <!-- Saved Panels Roster -->
        <section class="rounded border border-[#3a2016] bg-panel p-3">
          <div class="mb-2.5 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] text-dim">
            <span>Saved Panels · {{ panels.length }}</span>
            <button class="text-gold hover:text-core" @click="load">Refresh</button>
          </div>

          <p v-if="loading" class="text-[11px] uppercase tracking-wider text-dim">Loading panels…</p>
          <p v-else-if="!panels.length" class="rounded border border-dashed border-[#2a1620] px-3 py-4 text-center text-[10px] uppercase tracking-wider text-muted">
            No saved panels yet. Pick a template or click Create Panel.
          </p>

          <div v-else class="space-y-2">
            <div
              v-for="panel in panels"
              :key="panel.id"
              class="rounded border bg-[#120a10] p-2.5 transition-colors"
              :class="
                editingId === panel.id
                  ? 'border-flame bg-[#1d0f15]'
                  : panel.health_status === 'unhealthy'
                    ? 'border-[#b3241a]'
                    : 'border-[#2a1620] hover:border-[#4b2b1e]'
              "
            >
              <div class="flex items-start justify-between gap-2">
                <div class="flex min-w-0 items-center gap-2">
                  <span
                    class="h-2 w-2 shrink-0 rounded-full"
                    :class="
                      panel.health_status === 'unhealthy'
                        ? 'bg-[#ff5a2a]'
                        : panel.health_status === 'healthy'
                          ? 'bg-[#2ee58d]'
                          : 'bg-flame/70'
                    "
                    :title="`Status: ${panel.health_status ?? 'unknown'}`"
                  ></span>
                  <span
                    class="truncate text-xs font-semibold"
                    :class="panel.health_status === 'unhealthy' ? 'text-[#ff8a6a]' : 'text-core'"
                  >
                    {{ panel.id }}
                  </span>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <span class="rounded border border-[#3a2016] bg-[#160b14] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-flame">
                    {{ sourceBadge(panel.data_source.type) }}
                  </span>
                  <span class="rounded border border-[#2a1620] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-dim">
                    {{ layoutLabel(panel.layout) }}
                  </span>
                </div>
              </div>

              <div class="mt-1 flex items-center justify-between gap-2 text-[10px]">
                <span class="truncate text-gold/85">{{ panel.title || '—' }}</span>
                <span
                  v-if="panel.health_status === 'unhealthy'"
                  class="shrink-0 rounded border border-[#b3241a] bg-[#2a0a0e] px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-[#ff6a4a]"
                >
                  {{ panel.skipped_unhealthy ? 'down · skip' : 'data down' }}
                </span>
                <span v-else-if="panel.skip_when_unhealthy" class="shrink-0 text-[9px] uppercase tracking-wider text-muted">
                  skip-if-down
                </span>
              </div>

              <div
                v-if="panel.health_status === 'unhealthy'"
                class="mt-2 rounded border border-[#b3241a]/70 bg-[#1e0a0e] px-2 py-1.5 text-[10px]"
              >
                <p class="text-[#ff8a6a]">{{ panel.health_reason || 'Data source unavailable or empty.' }}</p>
                <p class="mt-0.5 uppercase tracking-[0.12em] text-muted" :title="panel.last_healthy ?? undefined">
                  Last healthy: {{ panel.last_healthy_human || 'never' }}
                </p>
              </div>

              <div class="mt-2.5 flex items-center gap-1.5">
                <button
                  class="rounded border border-[#3a2016] px-2 py-0.5 text-[10px] uppercase tracking-wider text-gold hover:bg-[#251009]"
                  @click="editPanel(panel)"
                >
                  Edit
                </button>
                <button
                  class="rounded border border-[#2a1620] px-2 py-0.5 text-[10px] uppercase tracking-wider text-dim hover:bg-[#251009] hover:text-gold"
                  @click="previewSavedPanel(panel)"
                >
                  Preview
                </button>
                <button
                  class="ml-auto rounded border border-[#2a1620] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[#ff6a4a] hover:border-[#b3241a] hover:bg-[#251009]"
                  @click="del(panel.id)"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        </section>
      </aside>

      <!-- RIGHT INSPECTOR: Clean Sectioned Form -->
      <section class="flex flex-col gap-4">
        <!-- Section 1: Identity & Visual Layout Picker -->
        <div class="rounded border border-[#3a2016] bg-panel p-4">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-[0.18em] text-ember">
              1 · Identity &amp; Layout
            </span>
            <span class="rounded border border-[#2a1620] bg-[#120a10] px-2 py-0.5 text-[9px] uppercase tracking-[0.14em] text-dim">
              {{ isEditing ? `Editing ${editingId}` : 'New Panel' }}
            </span>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <div>
              <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Panel ID</label>
              <input
                v-model="draft.id"
                type="text"
                placeholder="api_latency"
                :disabled="isEditing"
                :class="inputClass"
              />
            </div>
            <div>
              <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Header Title</label>
              <input v-model="draft.title" type="text" placeholder="API P95" :class="inputClass" />
            </div>
          </div>

          <!-- Visual 5-Card Wireframe Layout Picker -->
          <div class="mt-4">
            <label class="mb-2 block text-[10px] uppercase tracking-[0.18em] text-dim">
              Layout · <span class="text-gold">{{ layoutLabel(draft.layout) }}</span>
            </label>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <button
                v-for="item in LAYOUTS"
                :key="item.value"
                type="button"
                class="group flex flex-col items-center rounded-md border p-2 text-center transition-all"
                :class="
                  draft.layout === item.value
                    ? 'border-flame bg-[#21100b] text-core shadow-[0_0_16px_-6px_rgba(255,142,60,0.65)]'
                    : 'border-[#2a1620] bg-[#120a10] text-dim hover:border-[#4c2b1c] hover:text-gold'
                "
                :title="item.hint"
                @click="selectLayout(item.value)"
              >
                <!-- Mini 64x64 pixel hardware wireframe SVG -->
                <svg viewBox="0 0 36 36" class="mb-1.5 h-10 w-10 rounded border border-[#24121c] bg-[#06080f]">
                  <!-- Top instrument header strip -->
                  <rect x="0" y="0" width="36" height="7" fill="#0f1522" />
                  <rect
                    x="3"
                    y="2.5"
                    width="2"
                    height="2"
                    :fill="draft.layout === item.value ? '#ff9e3d' : '#7a5a44'"
                  />
                  <rect x="7" y="2.5" width="12" height="2" fill="#5e6e85" />
                  <line x1="0" y1="7" x2="36" y2="7" stroke="#1e2a3f" stroke-width="1" />

                  <!-- big_number wireframe -->
                  <template v-if="item.value === 'big_number'">
                    <rect x="3" y="10" width="30" height="23" rx="1" fill="#0a101b" stroke="#1b263a" />
                    <rect x="9" y="14" width="18" height="6" rx="0.5" :fill="draft.layout === item.value ? '#fff2cf' : '#c79a6b'" />
                    <rect x="12" y="22" width="12" height="3.5" rx="0.5" fill="#174d35" />
                    <rect x="6" y="28.5" width="18" height="2" fill="#ff8e3c" />
                    <rect x="24" y="28.5" width="6" height="2" fill="#1b263a" />
                  </template>

                  <!-- sparkline wireframe -->
                  <template v-else-if="item.value === 'sparkline'">
                    <rect x="3" y="9.5" width="12" height="4" :fill="draft.layout === item.value ? '#fff2cf' : '#c79a6b'" />
                    <rect x="3" y="15.5" width="30" height="15" rx="1" fill="#0a101b" stroke="#1b263a" />
                    <polygon points="5,28 5,20 11,23 17,19 23,24 29,21 31,22 31,28" fill="#5bcefa" fill-opacity="0.28" />
                    <polyline points="5,20 11,23 17,19 23,24 29,21 31,22" fill="none" stroke="#5bcefa" stroke-width="1.4" />
                    <circle cx="31" cy="22" r="1.4" fill="#ffffff" />
                  </template>

                  <!-- multi_stat wireframe -->
                  <template v-else-if="item.value === 'multi_stat'">
                    <rect x="3" y="10" width="14" height="10.5" rx="1" fill="#0a101b" stroke="#1b263a" />
                    <line x1="4.5" y1="11.2" x2="15.5" y2="11.2" stroke="#5bcefa" stroke-width="1.2" />
                    <rect x="5" y="14.5" width="8" height="3.5" fill="#5bcefa" />

                    <rect x="19" y="10" width="14" height="10.5" rx="1" fill="#0a101b" stroke="#1b263a" />
                    <line x1="20.5" y1="11.2" x2="31.5" y2="11.2" stroke="#ff9e3d" stroke-width="1.2" />
                    <rect x="21" y="14.5" width="8" height="3.5" fill="#ff9e3d" />

                    <rect x="3" y="22.5" width="14" height="10.5" rx="1" fill="#0a101b" stroke="#1b263a" />
                    <line x1="4.5" y1="23.7" x2="15.5" y2="23.7" stroke="#2ee58d" stroke-width="1.2" />
                    <rect x="5" y="27" width="8" height="3.5" fill="#2ee58d" />

                    <rect x="19" y="22.5" width="14" height="10.5" rx="1" fill="#0a101b" stroke="#1b263a" />
                    <line x1="20.5" y1="23.7" x2="31.5" y2="23.7" stroke="#ba8aff" stroke-width="1.2" />
                    <rect x="21" y="27" width="8" height="3.5" fill="#ba8aff" />
                  </template>

                  <!-- key_value wireframe -->
                  <template v-else-if="item.value === 'key_value'">
                    <rect x="3" y="10" width="30" height="5" fill="#0d1422" />
                    <rect x="4.5" y="11.5" width="2" height="2" fill="#2ee58d" />
                    <rect x="8" y="11.5" width="10" height="2" fill="#6f829e" />
                    <rect x="24" y="11.5" width="7.5" height="2" fill="#2ee58d" />

                    <rect x="3" y="16" width="30" height="5" fill="#070b13" />
                    <rect x="4.5" y="17.5" width="2" height="2" fill="#5bcefa" />
                    <rect x="8" y="17.5" width="11" height="2" fill="#6f829e" />
                    <rect x="24" y="17.5" width="7.5" height="2" fill="#5bcefa" />

                    <rect x="3" y="22" width="30" height="5" fill="#0d1422" />
                    <rect x="4.5" y="23.5" width="2" height="2" fill="#ba8aff" />
                    <rect x="8" y="23.5" width="9" height="2" fill="#6f829e" />
                    <rect x="24" y="23.5" width="7.5" height="2" fill="#ba8aff" />

                    <rect x="3" y="28" width="30" height="5" fill="#070b13" />
                    <rect x="4.5" y="29.5" width="2" height="2" fill="#ff9e3d" />
                    <rect x="8" y="29.5" width="10" height="2" fill="#6f829e" />
                    <rect x="24" y="29.5" width="7.5" height="2" fill="#ff9e3d" />
                  </template>

                  <!-- marquee wireframe -->
                  <template v-else>
                    <rect x="3" y="13" width="30" height="13" rx="1" fill="#0a101b" stroke="#1e2a3f" />
                    <line x1="5" y1="14.5" x2="31" y2="14.5" stroke="#ff9e3d" stroke-opacity="0.55" />
                    <rect x="5" y="18" width="26" height="3.5" :fill="draft.layout === item.value ? '#ffd98a' : '#c79a6b'" />
                    <line x1="5" y1="24.5" x2="31" y2="24.5" stroke="#ff9e3d" stroke-opacity="0.3" />
                    <rect x="11" y="29.5" width="14" height="2" fill="#5e6e85" />
                  </template>
                </svg>

                <span class="text-[10px] font-semibold uppercase tracking-wider">{{ item.label }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Section 2: Data Source (Segmented Switcher) -->
        <div class="rounded border border-[#3a2016] bg-panel p-4">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-[0.18em] text-ember">2 · Data Source</span>
            <span class="text-[10px] uppercase tracking-[0.14em] text-muted">
              {{ sourceBadge(sourceType) }}
            </span>
          </div>

          <!-- Segmented control -->
          <div class="grid grid-cols-4 gap-1 rounded border border-[#2a1620] bg-[#0e070e] p-1">
            <button
              v-for="src in SOURCES"
              :key="src.value"
              type="button"
              class="rounded px-2 py-1.5 text-[10px] uppercase tracking-[0.14em] transition-colors"
              :class="
                sourceType === src.value
                  ? 'bg-flame font-bold text-[#160a0a]'
                  : 'text-dim hover:bg-[#1a0d14] hover:text-gold'
              "
              @click="selectSourceType(src.value)"
            >
              {{ src.label }}
            </button>
          </div>

          <div class="mt-3">
            <template v-if="sourceType === 'http'">
              <div class="grid gap-3">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">JSON Endpoint URL</label>
                  <input
                    :value="sourceString('url')"
                    type="text"
                    placeholder="https://api.example.com/metrics.json"
                    :class="inputClass"
                    @input="setSourceValue('url', $event)"
                  />
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Cache TTL (sec)</label>
                    <input
                      :value="sourceNumber('ttl', 300)"
                      type="number"
                      min="10"
                      :class="inputClass"
                      @input="setSourceNumber('ttl', $event, 300)"
                    />
                  </div>
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Authentication</label>
                    <select :value="authType()" :class="inputClass" @change="setAuthType">
                      <option v-for="auth in AUTH_TYPES" :key="auth.value" :value="auth.value">
                        {{ auth.label }}
                      </option>
                    </select>
                  </div>
                </div>

                <!-- Secret-safe auth inputs (preserving has_token / has_password masking) -->
                <div v-if="authType() === 'bearer'">
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Bearer Token</label>
                  <input
                    :value="recordString(authRecord(), 'token')"
                    type="password"
                    :placeholder="authRecord().has_token ? 'Stored (leave blank to keep)' : 'Enter bearer token'"
                    autocomplete="off"
                    data-1p-ignore
                    :class="inputClass"
                    @input="setAuthValue('token', $event)"
                  />
                </div>
                <div v-else-if="authType() === 'api_key'" class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Header Name</label>
                    <input
                      :value="recordString(authRecord(), 'header', 'X-API-Key')"
                      type="text"
                      :class="inputClass"
                      @input="setAuthValue('header', $event)"
                    />
                  </div>
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">API Key</label>
                    <input
                      :value="recordString(authRecord(), 'token')"
                      type="password"
                      :placeholder="authRecord().has_token ? 'Stored (leave blank to keep)' : 'Enter API key'"
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
                      :placeholder="authRecord().has_password ? 'Stored (leave blank to keep)' : 'Enter password'"
                      autocomplete="off"
                      data-1p-ignore
                      :class="inputClass"
                      @input="setAuthValue('password', $event)"
                    />
                  </div>
                </div>
              </div>
            </template>

            <template v-else-if="sourceType === 'ha'">
              <div class="grid grid-cols-[1fr_7.5rem] gap-3">
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
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">TTL (sec)</label>
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

            <template v-else-if="sourceType === 'mqtt'">
              <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">MQTT Topic</label>
              <input
                :value="sourceString('topic')"
                type="text"
                placeholder="sensors/office/telemetry"
                :class="inputClass"
                @input="setSourceValue('topic', $event)"
              />
            </template>

            <template v-else>
              <p class="text-[11px] text-muted">
                Values are stored directly in this panel — ideal for quick prototypes, desk labels, or testing layouts before wiring live telemetry.
              </p>
            </template>

            <!-- Freshness & auto-skip guardrails for live data sources -->
            <div v-if="isMappedSource" class="mt-3 grid gap-3 border-t border-[#24121c] pt-3">
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Stale After (sec)</label>
                  <input
                    :value="sourceString('stale_after')"
                    type="number"
                    min="1"
                    placeholder="optional (e.g. 900)"
                    :class="inputClass"
                    @input="setSourceOptionalNumber('stale_after', $event)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Timestamp Path</label>
                  <input
                    :value="sourceString('timestamp_path')"
                    type="text"
                    placeholder="optional (e.g. updated_at)"
                    :class="inputClass"
                    @input="setSourceValue('timestamp_path', $event)"
                  />
                </div>
              </div>
              <label class="flex cursor-pointer items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-gold">
                <input v-model="draft.skip_when_unhealthy" type="checkbox" class="accent-flame" />
                Skip in rotation when data is down or stale
              </label>
            </div>
          </div>
        </div>

        <!-- Section 3: Layout Fields & Mappings -->
        <div class="rounded border border-[#3a2016] bg-panel p-4">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-[0.18em] text-ember">
              3 · {{ layoutLabel(draft.layout) }} Fields
            </span>
            <span class="text-[10px] uppercase tracking-[0.14em] text-muted">
              {{ isStaticSource ? 'Direct values' : 'Dot-path mappings' }}
            </span>
          </div>

          <!-- big_number -->
          <template v-if="draft.layout === 'big_number'">
            <div class="grid gap-3 sm:grid-cols-2">
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">
                  {{ isStaticSource ? 'Hero Value' : 'Value Path' }}
                </label>
                <input
                  v-if="isStaticSource"
                  :value="configString('value')"
                  type="text"
                  placeholder="12.4"
                  :class="inputClass"
                  @input="setConfigValue('value', $event)"
                />
                <input
                  v-else
                  :value="mappingString('value')"
                  type="text"
                  :placeholder="sourceType === 'ha' ? 'state' : 'metrics.active_users'"
                  :class="inputClass"
                  @input="setMappingValue('value', $event)"
                />
              </div>
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Unit (optional)</label>
                <input
                  :value="configString('unit')"
                  type="text"
                  placeholder="k, %, °F, ms"
                  :class="inputClass"
                  @input="setConfigValue('unit', $event)"
                />
              </div>
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">
                  {{ isStaticSource ? 'Delta Pill (optional)' : 'Delta Path (optional)' }}
                </label>
                <input
                  v-if="isStaticSource"
                  :value="configString('delta')"
                  type="text"
                  placeholder="+18.6% or -2.1%"
                  :class="inputClass"
                  @input="setConfigValue('delta', $event)"
                />
                <input
                  v-else
                  :value="mappingString('delta')"
                  type="text"
                  placeholder="metrics.delta_pct"
                  :class="inputClass"
                  @input="setMappingValue('delta', $event)"
                />
              </div>
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">
                  Progress Bar % (optional)
                </label>
                <input
                  v-if="isStaticSource"
                  :value="configString('progress')"
                  type="number"
                  min="0"
                  max="100"
                  placeholder="0 – 100"
                  :class="inputClass"
                  @input="setConfigOptionalNumber('progress', $event)"
                />
                <input
                  v-else
                  :value="mappingString('progress')"
                  type="text"
                  placeholder="metrics.goal_pct"
                  :class="inputClass"
                  @input="setMappingValue('progress', $event)"
                />
              </div>
              <div class="sm:col-span-2">
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Subtitle (optional)</label>
                <input
                  :value="configString('subtitle')"
                  type="text"
                  placeholder="SOLAR OFFSET"
                  :class="inputClass"
                  @input="setConfigValue('subtitle', $event)"
                />
              </div>
              <div v-if="isMappedSource" class="sm:col-span-2">
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Transform</label>
                <input
                  :value="mappingString('transform')"
                  type="text"
                  placeholder="/ 100 | round 1 | format %.1f"
                  :class="inputClass"
                  @input="setMappingValue('transform', $event)"
                />
              </div>
            </div>
          </template>

          <!-- sparkline -->
          <template v-else-if="draft.layout === 'sparkline'">
            <div class="grid gap-3">
              <div v-if="isStaticSource">
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Series Points (comma-separated)</label>
                <input
                  :value="Array.isArray(draft.config.points) ? draft.config.points.join(', ') : configString('points')"
                  type="text"
                  placeholder="64, 58, 61, 55, 49, 52, 47, 42"
                  :class="inputClass"
                  @input="
                    draft.config.points = inputValue($event)
                      .split(',')
                      .map((p) => Number(p.trim()))
                      .filter((p) => Number.isFinite(p))
                  "
                />
              </div>
              <template v-else>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Points Array Path</label>
                  <input
                    :value="mappingString('points')"
                    type="text"
                    placeholder="history.latency_ms"
                    :class="inputClass"
                    @input="setMappingValue('points', $event)"
                  />
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Point Value Key</label>
                    <input
                      :value="mappingString('point_value')"
                      type="text"
                      placeholder="p95 (if objects)"
                      :class="inputClass"
                      @input="setMappingValue('point_value', $event)"
                    />
                  </div>
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Point Transform</label>
                    <input
                      :value="mappingString('point_transform')"
                      type="text"
                      placeholder="/ 1000"
                      :class="inputClass"
                      @input="setMappingValue('point_transform', $event)"
                    />
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Current Value Path</label>
                    <input
                      :value="mappingString('value')"
                      type="text"
                      placeholder="current_p95"
                      :class="inputClass"
                      @input="setMappingValue('value', $event)"
                    />
                  </div>
                  <div>
                    <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Current Transform</label>
                    <input
                      :value="mappingString('transform')"
                      type="text"
                      placeholder="round 0 | format %dms"
                      :class="inputClass"
                      @input="setMappingValue('transform', $event)"
                    />
                  </div>
                </div>
              </template>

              <div class="grid grid-cols-3 gap-3">
                <div v-if="isStaticSource">
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Readout Label</label>
                  <input
                    :value="configString('value')"
                    type="text"
                    placeholder="42ms"
                    :class="inputClass"
                    @input="setConfigValue('value', $event)"
                  />
                </div>
                <div v-else>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Unit</label>
                  <input
                    :value="configString('unit')"
                    type="text"
                    placeholder="ms"
                    :class="inputClass"
                    @input="setConfigValue('unit', $event)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Delta Badge</label>
                  <input
                    :value="configString('delta')"
                    type="text"
                    placeholder="-14%"
                    :class="inputClass"
                    @input="setConfigValue('delta', $event)"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Window Tag</label>
                  <input
                    :value="configString('subtitle')"
                    type="text"
                    placeholder="24H"
                    :class="inputClass"
                    @input="setConfigValue('subtitle', $event)"
                  />
                </div>
              </div>

              <div class="flex flex-wrap items-center gap-5 pt-1">
                <label class="flex cursor-pointer items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-gold">
                  <input
                    type="checkbox"
                    :checked="configBool('fill', true)"
                    class="accent-flame"
                    @change="setConfigBool('fill', $event)"
                  />
                  Shaded area fill
                </label>
                <label class="flex cursor-pointer items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-gold">
                  <input
                    type="checkbox"
                    :checked="configBool('show_minmax', true)"
                    class="accent-flame"
                    @change="setConfigBool('show_minmax', $event)"
                  />
                  Show min / max bounds
                </label>
              </div>
            </div>
          </template>

          <!-- multi_stat -->
          <template v-else-if="draft.layout === 'multi_stat'">
            <div class="space-y-2">
              <div
                v-for="(stat, index) in isStaticSource ? staticStats() : mappedStats()"
                :key="index"
                class="grid items-center gap-2"
                :class="isStaticSource ? 'grid-cols-[1fr_1fr_2.5rem_auto]' : 'grid-cols-[0.85fr_1.1fr_0.8fr_3.5rem_2.5rem_auto]'"
              >
                <input v-model="stat.label" type="text" placeholder="CPU" :class="miniInputClass" />
                <input
                  v-if="isStaticSource"
                  v-model="stat.value"
                  type="text"
                  placeholder="28%"
                  :class="miniInputClass"
                />
                <input
                  v-else
                  v-model="stat.value_path"
                  type="text"
                  placeholder="host.cpu_pct"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="stat.transform"
                  type="text"
                  placeholder="round 0"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="stat.unit"
                  type="text"
                  placeholder="%"
                  :class="miniInputClass"
                />
                <input
                  v-model="stat.color"
                  type="color"
                  title="Tile accent color"
                  class="h-8 w-10 cursor-pointer rounded border border-[#3a2016] bg-[#120a10] p-0.5"
                />
                <button :class="ghostButtonClass" @click="removeStatRow(index)">×</button>
              </div>
            </div>
            <div class="mt-2.5 flex items-center justify-between">
              <button :class="ghostButtonClass" @click="addStatRow">+ Add Stat Tile</button>
              <span class="text-[10px] uppercase tracking-wider text-muted">Up to 4 tiles (2×2 grid)</span>
            </div>
          </template>

          <!-- key_value -->
          <template v-else-if="draft.layout === 'key_value'">
            <div class="space-y-2">
              <div
                v-for="(item, index) in isStaticSource ? staticItems() : mappedItems()"
                :key="index"
                class="grid items-center gap-2"
                :class="isStaticSource ? 'grid-cols-[1fr_1fr_2.5rem_auto]' : 'grid-cols-[0.85fr_1.1fr_0.8fr_3.5rem_2.5rem_auto]'"
              >
                <input v-model="item.key" type="text" placeholder="Living" :class="miniInputClass" />
                <input
                  v-if="isStaticSource"
                  v-model="item.value"
                  type="text"
                  placeholder="22° 44%"
                  :class="miniInputClass"
                />
                <input
                  v-else
                  v-model="item.value_path"
                  type="text"
                  placeholder="rooms.living.temp"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="item.transform"
                  type="text"
                  placeholder="round 0"
                  :class="miniInputClass"
                />
                <input
                  v-if="isMappedSource"
                  v-model="item.unit"
                  type="text"
                  placeholder="°"
                  :class="miniInputClass"
                />
                <input
                  v-model="item.color"
                  type="color"
                  title="Row pip & value color"
                  class="h-8 w-10 cursor-pointer rounded border border-[#3a2016] bg-[#120a10] p-0.5"
                />
                <button :class="ghostButtonClass" @click="removeItemRow(index)">×</button>
              </div>
            </div>
            <div class="mt-2.5 flex items-center justify-between">
              <button :class="ghostButtonClass" @click="addItemRow">+ Add Row</button>
              <span class="text-[10px] uppercase tracking-wider text-muted">Up to 5 banded rows</span>
            </div>
          </template>

          <!-- marquee -->
          <template v-else-if="draft.layout === 'marquee'">
            <div class="grid gap-3">
              <div>
                <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">
                  {{ isStaticSource ? 'Ticker Message' : 'Text Path' }}
                </label>
                <input
                  v-if="isStaticSource"
                  :value="configString('text')"
                  type="text"
                  placeholder="v2.4.1 LIVE · ALL REGIONS GREEN"
                  :class="inputClass"
                  @input="setConfigValue('text', $event)"
                />
                <input
                  v-else
                  :value="mappingString('text')"
                  type="text"
                  placeholder="status.headline"
                  :class="inputClass"
                  @input="setMappingValue('text', $event)"
                />
              </div>
              <div class="grid gap-3 sm:grid-cols-2">
                <div>
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Footer Label (optional)</label>
                  <input
                    :value="configString('subtitle')"
                    type="text"
                    placeholder="PROD CLUSTER"
                    :class="inputClass"
                    @input="setConfigValue('subtitle', $event)"
                  />
                </div>
                <div v-if="isMappedSource">
                  <label class="mb-1 block text-[10px] uppercase tracking-[0.18em] text-dim">Transform</label>
                  <input
                    :value="mappingString('transform')"
                    type="text"
                    placeholder="prefix ALERT: "
                    :class="inputClass"
                    @input="setMappingValue('transform', $event)"
                  />
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- Section 4: Curated LED Palette & Fine-Grained Color Overrides -->
        <div class="rounded border border-[#3a2016] bg-panel p-4">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-[0.18em] text-ember">4 · LED Palette</span>
            <div class="flex items-center gap-3 text-[10px] uppercase tracking-[0.14em]">
              <button
                v-if="hasCustomColors"
                type="button"
                class="text-muted hover:text-gold"
                @click="resetColors"
              >
                Reset
              </button>
              <button
                type="button"
                class="text-dim hover:text-gold"
                @click="showCustomColors = !showCustomColors"
              >
                {{ showCustomColors ? 'Hide hex overrides ▾' : 'Hex overrides ▸' }}
              </button>
            </div>
          </div>

          <!-- Curated HUB75/WLED swatches -->
          <div class="grid grid-cols-3 gap-2 sm:grid-cols-6">
            <button
              v-for="swatch in LED_SWATCHES"
              :key="swatch.name"
              type="button"
              class="flex items-center gap-2 rounded border px-2 py-1.5 text-left transition-colors"
              :class="
                activePrimaryColor === swatch.hex.toUpperCase()
                  ? 'border-flame bg-[#24110b] text-core'
                  : 'border-[#2a1620] bg-[#120a10] text-dim hover:border-[#4b2b1e] hover:text-gold'
              "
              @click="applyPaletteSwatch(swatch.hex)"
            >
              <span
                class="h-3.5 w-3.5 shrink-0 rounded-sm border border-white/15"
                :style="{ backgroundColor: swatch.hex, boxShadow: `0 0 8px ${swatch.hex}66` }"
              ></span>
              <span class="truncate text-[10px] uppercase tracking-wider">{{ swatch.name }}</span>
            </button>
          </div>

          <!-- Fine-grained hex pickers -->
          <div v-if="showCustomColors" class="mt-3 grid grid-cols-3 gap-2.5 border-t border-[#24121c] pt-3 sm:grid-cols-6">
            <label
              v-for="field in COLOR_FIELDS"
              :key="field.key"
              class="text-[10px] uppercase tracking-[0.12em] text-muted"
            >
              {{ field.label }}
              <input
                type="color"
                :value="configColor(field.key, field.fallback)"
                class="mt-1 h-8 w-full cursor-pointer rounded border border-[#3a2016] bg-[#120a10] p-0.5"
                @input="setConfigValue(field.key, $event)"
              />
            </label>
          </div>
        </div>

        <!-- Bottom Action Bar -->
        <div class="flex flex-wrap items-center justify-between gap-3 rounded border border-[#3a2016] bg-panel px-4 py-3">
          <div class="flex items-center gap-2 text-[10px] uppercase tracking-[0.15em] text-muted">
            <span>{{ layoutLabel(draft.layout) }}</span>
            <span>·</span>
            <span class="text-gold">{{ sourceBadge(sourceType) }}</span>
            <span v-if="isEditing" class="text-dim">· panel_{{ editingId }}</span>
          </div>
          <div class="flex items-center gap-2">
            <button :class="ghostButtonClass" :disabled="previewing" @click="doPreview">
              {{ previewing ? 'Rendering…' : '⟳ Render Preview' }}
            </button>
            <button
              class="rounded bg-flame px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-[#160a0a] transition-opacity hover:opacity-90 disabled:opacity-50"
              :disabled="saving"
              @click="save"
            >
              {{ saving ? 'Saving…' : isEditing ? 'Save Changes' : 'Create Panel' }}
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
