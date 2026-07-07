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
  app_type: 'star' | 'python' | 'static' | 'panel' | 'unknown'
  source: string | null
}

export interface Config {
  layout_mode: 'cycle' | 'random' | 'single'
  cycle_interval: number
  brightness: number
}

export interface NowPlaying {
  app: string | null
}

export interface Health {
  status: string
  [key: string]: unknown
}

/** A field extracted from a Starlark app's get_schema(). */
export interface SchemaField {
  type: string // text | toggle | dropdown | color | location | datetime | oauth2 | …
  id: string
  name?: string
  desc?: string
  default?: string
  icon?: string
  options?: { display: string; value: string }[]
}

export type PanelLayout = 'big_number' | 'key_value' | 'marquee' | 'multi_stat' | 'sparkline'

export interface DataSource {
  type?: 'http' | 'mqtt' | 'ha'
  url?: string
  json_path?: string
  entity?: string
  topic?: string
  label?: string
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
