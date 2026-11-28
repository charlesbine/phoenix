import { expect, test, type Page } from '@playwright/test'

const APPS_CHUNK_RE = /(?:\/assets\/Apps-[^/?]+\.js|\/src\/views\/Apps\.vue)(?:\?.*)?$/

async function stubDashboardApis(page: Page): Promise<void> {
  await page.routeWebSocket(/\/ws\/state\?/, () => {})
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    const responses: Record<string, unknown> = {
      '/api/apps': [],
      '/api/apps/available': [],
      '/api/config': { layout_mode: 'cycle', cycle_interval: 10, brightness: 128 },
      '/api/now-playing': { app: null, is_live: false },
      '/api/devices': [{ id: 'main', name: 'Main', backend: 'web', enabled: true }],
      '/api/playlists': [],
      '/api/status': { status: 'ok' },
    }
    await route.fulfill({ json: responses[path] ?? {} })
  })
}

test('recovers nav clicks with a full navigation when a lazy route chunk returns 404', async ({ page }) => {
  await stubDashboardApis(page)

  let misses = 0
  await page.route(APPS_CHUNK_RE, async (route) => {
    misses += 1
    if (misses === 1) {
      await route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not Found' })
      return
    }
    await route.continue()
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Apps', exact: true }).click()

  await expect(page).toHaveURL(/\/apps$/)
  await expect(page.getByText('Rotation & configuration')).toBeVisible()
  expect(misses).toBeGreaterThanOrEqual(2)
})

test('stops after one retry when a lazy route chunk keeps failing', async ({ page }) => {
  await stubDashboardApis(page)

  let attempts = 0
  await page.route(APPS_CHUNK_RE, async (route) => {
    attempts += 1
    await route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not Found' })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Apps', exact: true }).click()

  await expect(page).toHaveURL(/\/apps$/)
  await page.waitForTimeout(500)
  expect(attempts).toBe(2)
})
