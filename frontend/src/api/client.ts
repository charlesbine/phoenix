import type {
  AppItem,
  Config,
  NowPlaying,
  Health,
  SchemaField,
  Panel,
  Playlist,
  ScheduleRule,
  Schedule,
  StoreApp,
} from './types'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${path} → ${res.status}`)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const enc = encodeURIComponent

export const api = {
  // --- apps ---
  listApps: () => req<AppItem[]>('/api/apps'),
  availableApps: () => req<string[]>('/api/apps/available'),
  getConfig: () => req<Config>('/api/config'),
  setConfig: (patch: Partial<Config>) =>
    req<Config>('/api/config', { method: 'PUT', body: JSON.stringify(patch) }),
  nowPlaying: () => req<NowPlaying>('/api/now-playing'),
  health: () => req<Health>('/api/health'),

  enable: (name: string) => req<AppItem>(`/api/apps/${enc(name)}/enable`, { method: 'POST' }),
  disable: (name: string) => req<AppItem>(`/api/apps/${enc(name)}/disable`, { method: 'POST' }),
  activate: (name: string) => req<AppItem>(`/api/apps/${enc(name)}/activate`, { method: 'POST' }),
  deactivate: (name: string) => req<AppItem>(`/api/apps/${enc(name)}/deactivate`, { method: 'POST' }),
  addApp: (name: string) => req<AppItem>(`/api/apps/${enc(name)}/add`, { method: 'POST' }),
  deleteApp: (name: string) => req<{ ok: boolean }>(`/api/apps/${enc(name)}`, { method: 'DELETE' }),
  showNow: (name: string) => req<void>(`/api/apps/${enc(name)}/show`, { method: 'POST' }),
  preview: (name: string) =>
    req<{ name?: string; info?: string; error?: string }>(`/api/apps/${enc(name)}/preview`, {
      method: 'POST',
    }),
  render: (name: string) =>
    req<{ info?: string; error?: string }>(`/api/apps/${enc(name)}/render`, { method: 'POST' }),

  getSchema: (name: string) => req<SchemaField[]>(`/api/apps/${enc(name)}/schema`),
  setAppConfig: (name: string, config: Record<string, unknown>) =>
    req<AppItem>(`/api/apps/${enc(name)}/config`, { method: 'PUT', body: JSON.stringify(config) }),
  setPriority: (name: string, priority: number) =>
    req<AppItem>(`/api/apps/${enc(name)}/priority`, { method: 'PUT', body: JSON.stringify({ priority }) }),
  setPreset: (name: string, preset: string) =>
    req<AppItem>(`/api/apps/${enc(name)}/preset`, { method: 'PUT', body: JSON.stringify({ preset }) }),
  setRefreshInterval: (name: string, refresh_interval: number) =>
    req<AppItem>(`/api/apps/${enc(name)}/refresh-interval`, {
      method: 'PUT',
      body: JSON.stringify({ refresh_interval }),
    }),
  reorder: (order: string[]) =>
    req<{ ok: boolean }>('/api/reorder', { method: 'PUT', body: JSON.stringify({ order }) }),

  // --- panels ---
  listPanels: () => req<Panel[]>('/api/panels'),
  getPanel: (id: string) => req<Panel>(`/api/panels/${enc(id)}`),
  createPanel: (p: Partial<Panel>) =>
    req<Panel | { error: string }>('/api/panels', { method: 'POST', body: JSON.stringify(p) }),
  updatePanel: (id: string, p: Partial<Panel>) =>
    req<Panel | { error: string }>(`/api/panels/${enc(id)}`, { method: 'PUT', body: JSON.stringify(p) }),
  deletePanel: (id: string) => req<{ ok: boolean }>(`/api/panels/${enc(id)}`, { method: 'DELETE' }),
  previewPanel: (p: Partial<Panel>) =>
    req<{ preview_url?: string; error?: string }>('/api/panels/preview', {
      method: 'POST',
      body: JSON.stringify(p),
    }),

  // --- playlists & schedule ---
  listPlaylists: () => req<Playlist[]>('/api/playlists'),
  createPlaylist: (p: { id: string; name: string; app_names: string[] }) =>
    req<Playlist | { error: string }>('/api/playlists', { method: 'POST', body: JSON.stringify(p) }),
  updatePlaylist: (id: string, p: Partial<Playlist>) =>
    req<Playlist>(`/api/playlists/${enc(id)}`, { method: 'PUT', body: JSON.stringify(p) }),
  deletePlaylist: (id: string) => req<{ ok: boolean }>(`/api/playlists/${enc(id)}`, { method: 'DELETE' }),
  getSchedule: () => req<Schedule>('/api/schedule'),
  createRule: (r: { playlist_id: string; start_time: string; end_time: string; days: string[] }) =>
    req<ScheduleRule>('/api/schedule', { method: 'POST', body: JSON.stringify(r) }),
  deleteRule: (id: number) => req<{ ok: boolean }>(`/api/schedule/${id}`, { method: 'DELETE' }),

  // --- community store ---
  listStore: (q = '', category = '') =>
    req<StoreApp[]>(`/api/store?q=${enc(q)}&category=${enc(category)}`),
  storeCategories: () => req<string[]>('/api/store/categories'),
  installStore: (name: string) =>
    req<AppItem | { error: string }>(`/api/store/${enc(name)}/install`, { method: 'POST' }),
  previewStore: (name: string) =>
    req<{ preview_url?: string; error?: string }>(`/api/store/${enc(name)}/preview`, { method: 'POST' }),
  syncStore: () => req<{ ok: boolean }>('/api/store/sync', { method: 'POST' }),

  /** Latest rendered frame for an app (magnified webp), cache-busted by the caller. */
  frameUrl: (name: string) => `/static/outputs/${enc(name)}.large.webp`,
}
