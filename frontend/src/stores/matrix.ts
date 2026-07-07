import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api/client'
import type { AppItem, Config } from '@/api/types'

interface StatePush {
  apps: AppItem[]
  config: Config
  now_playing: string | null
}

export const useMatrixStore = defineStore('matrix', () => {
  const apps = ref<AppItem[]>([])
  const config = ref<Config | null>(null)
  const nowPlaying = ref<string | null>(null)
  const online = ref(false)
  const error = ref<string | null>(null)
  const tick = ref(0) // bumps on every state push / render — cache-busts the preview frame

  // The app the user is previewing in the UI. Independent of what's *physically*
  // playing (nowPlaying), so live rotation never yanks you off your selection.
  const selected = ref<string | null>(null)
  const note = ref<string | null>(null) // last render/preview message (e.g. "no data to display")

  const rotation = computed(() => [...apps.value].sort((a, b) => a.sort_order - b.sort_order))
  const previewApp = computed(() => selected.value ?? nowPlaying.value)
  const selectedApp = computed(() => apps.value.find((a) => a.name === previewApp.value) ?? null)
  const following = computed(() => selected.value === null)

  let ws: WebSocket | null = null
  let reconnect: ReturnType<typeof setTimeout> | undefined
  let closed = false

  function apply(s: StatePush): void {
    apps.value = s.apps
    config.value = s.config
    nowPlaying.value = s.now_playing
    online.value = true
    error.value = null
    tick.value++
  }

  async function refresh(): Promise<void> {
    try {
      const [a, c, np] = await Promise.all([api.listApps(), api.getConfig(), api.nowPlaying()])
      apply({ apps: a, config: c, now_playing: np.app })
    } catch (e) {
      online.value = false
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  function connect(): void {
    closed = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws/state`)
    ws.onmessage = (e) => apply(JSON.parse(e.data) as StatePush)
    ws.onclose = () => {
      online.value = false
      ws = null
      if (!closed) reconnect = setTimeout(connect, 2000)
    }
    ws.onerror = () => ws?.close()
  }

  function disconnect(): void {
    closed = true
    if (reconnect) clearTimeout(reconnect)
    ws?.close()
    ws = null
  }

  // --- preview selection (UI-only) ---

  function select(name: string): void {
    note.value = null
    selected.value = selected.value === name ? null : name // click again → follow live
  }
  function followLive(): void {
    selected.value = null
    note.value = null
  }

  /** Force-render an app's frame on demand (for apps with no rendered frame yet). */
  async function render(name: string): Promise<void> {
    note.value = 'rendering…'
    const r = await api.preview(name)
    note.value = r?.error ?? r?.info ?? null
    tick.value++
  }

  // --- actions (REST; the next state push reflects them) ---

  async function setBrightness(value: number): Promise<void> {
    config.value = await api.setConfig({ brightness: value })
  }

  async function toggle(app: AppItem): Promise<void> {
    const updated = app.enabled ? await api.disable(app.name) : await api.enable(app.name)
    replace(updated)
  }

  async function setPriority(name: string, priority: number): Promise<void> {
    replace(await api.setPriority(name, Math.max(0, priority))) // 0 = normal weight (×1)
  }

  /** Push an app to the physical display right now. */
  async function showNow(name: string): Promise<void> {
    await api.showNow(name)
    nowPlaying.value = name
  }

  function replace(updated: AppItem): void {
    const i = apps.value.findIndex((x) => x.name === updated.name)
    if (i >= 0) apps.value[i] = updated
  }

  return {
    apps, config, nowPlaying, online, error, tick, note,
    selected, rotation, previewApp, selectedApp, following,
    refresh, connect, disconnect, select, followLive, render,
    setBrightness, toggle, setPriority, showNow,
  }
})
