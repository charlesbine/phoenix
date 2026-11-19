// Shapes mirror Phoenix's FastAPI responses. TODO: generate from /openapi.json.

export interface AppItem {
  name: string
  enabled: boolean
  active: boolean
  refresh_interval: number
  last_updated: string | null
  last_updated_human: string
  priority: number
  sort_order: number
  pixlet_config: Record<string, unknown>
  refresh_preset: string | null
  app_type: 'star' | 'python' | 'static' | 'panel' | 'live_audio' | 'live_nowplaying' | 'unknown'
  is_live: boolean
  source: string | null
}

export interface Config {
  layout_mode: 'cycle' | 'random' | 'single'
  cycle_interval: number
  brightness: number
  single_app?: string | null
  brightness_schedule_status?: 'daytime' | 'dimmed' | 'off' | 'custom' | null
}

export type NodeSyncStatus = 'pending' | 'offline' | 'synced'

export interface NowPlaying {
  app: string | null
  is_live: boolean
  node_sync?: NodeSyncStatus
}

export interface BrightnessSchedule {
  enabled: boolean
  mode: 'night' | 'custom'
  steps: { time: string; brightness: number }[]
}

export interface DisplaySettings {
  timezone: string
  latitude: number | null
  longitude: number | null
}

/** A physical panel. Content (rotation), brightness and layout are per-device;
 * mirror_of makes this panel follow another. */
export interface Device {
  id: string
  name: string
  backend: 'web' | 'serial' | 'wled' | 'matrix'
  brightness: number
  brightness_schedule: BrightnessSchedule | null
  layout_mode: 'cycle' | 'random' | 'single'
  cycle_interval: number
  mirror_of: string | null
  sort_order: number
  enabled: boolean
  content_mode: 'apps' | 'audio' | 'nowplaying'
  audio_mode: 'bars' | 'vu' | 'spectrogram'
  address: string
}

export interface Health {
  status: string
  issues?: string[]
  player?: { name: string; status: NodeSyncStatus }
  m4?: {
    connected?: boolean
    port?: string
  }
  mqtt?: {
    connected?: boolean
    broker?: string | null
  }
  memory?: {
    total_mb?: number
    available_mb?: number
    used_pct?: number
  }
  load?: {
    '1m'?: number
    '5m'?: number
    '15m'?: number
  }
  uptime?: string
  [key: string]: unknown
}

export interface LogLines {
  lines: string[]
}

export interface Stats {
  render_times?: Record<string, number>
  load?: {
    '1m'?: number
    '5m'?: number
    '15m'?: number
  }
  memory?: {
    total_mb?: number
    available_mb?: number
    used_mb?: number
  }
  [key: string]: unknown
}

export interface NotificationItem {
  id: number
  text: string
  color: string
  duration: number
  layout: string
  created_at: number
  displayed: boolean
}

export interface CacheEntry {
  url: string
  age_seconds: number
  ttl: number
  fresh: boolean
  size_bytes: number
}

/** A field extracted from a Starlark app's get_schema(). */
export interface SchemaField {
  type: string // text | toggle | dropdown | color | location | datetime | oauth2 | …
  id: string
  name?: string
  desc?: string
  default?: string
  step?: string
  icon?: string
  options?: { display: string; value: string }[]
}

export type PanelLayout = 'big_number' | 'key_value' | 'marquee' | 'multi_stat' | 'sparkline'

export interface DataSource {
  type?: 'static' | 'http' | 'mqtt' | 'ha'
  url?: string
  ttl?: number
  json_path?: string
  entity_id?: string
  topic?: string
  label?: string
  mappings?: Record<string, unknown>
  auth?: Record<string, unknown>
  headers?: Record<string, string>
  [key: string]: unknown
}

export interface Panel {
  id: string
  layout: PanelLayout
  title: string
  config: Record<string, unknown>
  data_source: DataSource
}

export interface Playlist {
  id: string
  name: string
  app_names: string[]
}

export interface ScheduleRule {
  id: number
  playlist_id: string
  playlist_name?: string
  start_time: string
  end_time: string
  days: string[]
}

export interface Schedule {
  rules: ScheduleRule[]
  active_playlist: string | null
}

export interface StoreApp {
  name: string
  summary: string
  description: string
  author: string
  category: string
  tags: string[]
  supports_2x: boolean
  installed: boolean
}
