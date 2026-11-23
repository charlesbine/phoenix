import { expect, test, type WebSocketRoute } from '@playwright/test'

test('a rendered animation keeps playing across unrelated panel updates', async ({ page }) => {
  const planet = {
    name: 'procedural_planet', enabled: true, active: true, is_live: false,
    pixlet_config: {}, health_status: 'healthy', priority: 0, sort_order: 0,
    last_updated: '2026-11-23T18:00:00',
  }
  const config = { layout_mode: 'cycle', cycle_interval: 10, brightness: 128 }
  let socket: WebSocketRoute | undefined
  await page.routeWebSocket(/\/ws\/state\?/, (route) => { socket = route })
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    const responses: Record<string, unknown> = {
      '/api/apps': [planet],
      '/api/config': config,
      '/api/now-playing': { app: planet.name, is_live: false, node_sync: 'synced' },
      '/api/devices': [],
      '/api/status': { status: 'ok' },
    }
    await route.fulfill({ json: responses[path] ?? {} })
  })
  await page.route('**/static/outputs/**', (route) => route.fulfill({
    contentType: 'image/gif',
    body: Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64'),
  }))
  await page.goto('/')

  const preview = page.getByRole('img', { name: 'Matrix preview' })
  await expect(preview).toBeVisible()
  await expect.poll(() => Boolean(socket)).toBe(true)
  const original = await preview.getAttribute('src')
  const state = { apps: [planet], config, now_playing: planet.name, now_playing_is_live: false }
  socket!.send(JSON.stringify({ ...state, node_sync: 'pending' }))
  await expect(page.getByText('Player update pending')).toBeVisible()
  expect(await preview.getAttribute('src')).toBe(original)

  planet.last_updated = '2026-11-23T18:30:00'
  socket!.send(JSON.stringify({ ...state, node_sync: 'synced' }))
  await expect(preview).toHaveAttribute('src', new RegExp(encodeURIComponent(planet.last_updated)))
})
