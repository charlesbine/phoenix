import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/views/Home.vue'

const CHUNK_RELOAD_KEY = 'phoenix.chunkReloadTarget'

function isChunkLoadError(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err)
  return (
    /Failed to fetch dynamically imported module/i.test(message) ||
    /Importing a module script failed/i.test(message) ||
    /error loading dynamically imported module/i.test(message) ||
    /Unable to preload CSS/i.test(message) ||
    /Loading chunk [\w-]+ failed/i.test(message)
  )
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/apps', component: () => import('@/views/Apps.vue') },
    { path: '/panels', component: () => import('@/views/Panels.vue') },
    { path: '/playlists', component: () => import('@/views/Playlists.vue') },
    { path: '/store', component: () => import('@/views/Store.vue') },
    { path: '/devices', component: () => import('@/views/Devices.vue') },
    { path: '/diagnostics', component: () => import('@/views/Diagnostics.vue') },
  ],
})

// Recover open tabs when a deploy rotates Vite chunk hashes or SSO expires on a lazy route import.
router.onError((err, to) => {
  if (!isChunkLoadError(err)) return
  const candidate = to?.fullPath || `${window.location.pathname}${window.location.search}${window.location.hash}`
  const target = candidate.startsWith('/') && !candidate.startsWith('//') ? candidate : '/'
  try {
    if (sessionStorage.getItem(CHUNK_RELOAD_KEY) === target) {
      sessionStorage.removeItem(CHUNK_RELOAD_KEY)
      return
    }
    sessionStorage.setItem(CHUNK_RELOAD_KEY, target)
  } catch {
    return
  }
  window.location.assign(target)
})

router.afterEach(() => {
  try {
    sessionStorage.removeItem(CHUNK_RELOAD_KEY)
  } catch {
    /* ignore storage restrictions */
  }
})
