import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api/client'
import type { AppItem, Config, Device } from '@/api/types'

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

  // Which physical panel the UI is driving. 'main' is seeded server-side, so it
  // always exists; all apps/config/now-playing calls are scoped to this device.
  // Persisted so a browser refresh keeps you on the same panel.
  const DEVICE_KEY = 'phoenix.activeDevice'
  const devices = ref<Device[]>([])
  const activeDevice = ref(readStoredDevice())
  const activeDeviceObj = computed(
    () => devices.value.find((d) => d.id === activeDevice.value) ?? null,
  )

  function readStoredDevice(): string {
    try {
      return localStorage.getItem(DEVICE_KEY) ?? 'main'
    } catch {
      return 'main'
    }
  }
  function rememberDevice(id: string): void {
    activeDevice.value = id
    try {
      localStorage.setItem(DEVICE_KEY, id)
    } catch {
      /* private mode / storage disabled — in-memory only */
    }
  }

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
    const d = activeDevice.value
    try {
      const [a, c, np] = await Promise.all([api.listApps(d), api.getConfig(d), api.nowPlaying(d)])
      apply({ apps: a, config: c, now_playing: np.app })
    } catch (e) {
      online.value = false
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  async function loadDevices(): Promise<void> {
    try {
      devices.value = await api.listDevices()
      // If the active device is gone or disabled, land on the first enabled one
      // — via setActiveDevice so the live socket reconnects to it.
      const active = devices.value.find((d) => d.id === activeDevice.value)
      if (devices.value.length && (!active || !active.enabled)) {
        const target = devices.value.find((d) => d.enabled) ?? devices.value[0]
        await setActiveDevice(target.id)
      }
    } catch {
      /* devices are optional; the switcher just won't populate */
    }
  }

  /** Switch which panel the UI drives — reconnect the socket + reload state. */
  async function setActiveDevice(id: string): Promise<void> {
    if (id === activeDevice.value) return
    rememberDevice(id)
    selected.value = null
    disconnect()
    await refresh()
    connect()
  }

  function connect(): void {
    disconnect() // idempotent — drop any existing socket before opening a new one
    closed = false
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws/state?device=${encodeURIComponent(activeDevice.value)}`)
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
    config.value = await api.setConfig({ brightness: value }, activeDevice.value)
  }

  /** Switch the active panel's content mode (apps | audio | nowplaying). */
  async function setContentMode(mode: Device['content_mode']): Promise<void> {
    await api.updateDevice(activeDevice.value, { content_mode: mode })
    await loadDevices()
  }

  async function toggle(app: AppItem): Promise<void> {
    const d = activeDevice.value
    const updated = app.enabled ? await api.disable(app.name, d) : await api.enable(app.name, d)
    replace(updated)
  }

  async function setPriority(name: string, priority: number): Promise<void> {
    replace(await api.setPriority(name, Math.max(0, priority), activeDevice.value)) // 0 = normal weight (×1)
  }

  /** Push an app to the physical display right now. */
  async function showNow(name: string): Promise<void> {
    await api.showNow(name, activeDevice.value)
    nowPlaying.value = name
  }

  function replace(updated: AppItem): void {
    const i = apps.value.findIndex((x) => x.name === updated.name)
    if (i >= 0) apps.value[i] = updated
  }

  return {
    apps, config, nowPlaying, online, error, tick, note,
    devices, activeDevice, activeDeviceObj,
    selected, rotation, previewApp, selectedApp, following,
    refresh, connect, disconnect, select, followLive, render,
    loadDevices, setActiveDevice, setContentMode,
    setBrightness, toggle, setPriority, showNow,
  }
})
