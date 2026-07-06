import { onMounted, onUnmounted } from 'vue'

/**
 * Run `fn` immediately, then re-run `ms` after each completion (not on a fixed
 * interval, so slow requests can't stack up). Cleans up on unmount.
 */
export function usePoll(fn: () => void | Promise<void>, ms: number): void {
  let timer: ReturnType<typeof setTimeout> | undefined
  let stopped = false

  const tick = async () => {
    await fn()
    if (!stopped) timer = setTimeout(tick, ms)
  }

  onMounted(() => {
    void tick()
  })
  onUnmounted(() => {
    stopped = true
    if (timer) clearTimeout(timer)
  })
}
