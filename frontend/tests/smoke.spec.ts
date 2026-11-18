import { test, expect, type Page } from '@playwright/test'

const NAV = ['Home', 'Apps', 'Panels', 'Playlists', 'Store', 'Devices'] as const

/** Collect console errors + uncaught page errors so tests can assert none. */
function trackErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })
  page.on('pageerror', (e) => errors.push(String(e)))
  return errors
}

test.describe('Phoenix control UI — smoke', () => {
  test('nav shell + Home render, live preview, no console errors', async ({ page }) => {
    const errors = trackErrors(page)
    await page.goto('/')

    for (const label of NAV) {
      await expect(page.getByRole('button', { name: label, exact: true })).toBeVisible()
    }
    await expect(page.getByText(/Rotation ·/)).toBeVisible()
    // the live matrix preview frame actually loads
    await expect(page.locator('img[src*="/static/outputs/"]').first()).toBeVisible({ timeout: 15_000 })

    expect(errors, `console errors:\n${errors.join('\n')}`).toEqual([])
  })

  test('Apps: selecting an app opens the config editor + preview', async ({ page }) => {
    await page.goto('/apps')
    await expect(page.getByText('Rotation & configuration')).toBeVisible()
    await expect(page.getByText(/Select an app to configure/)).toBeVisible()

    // click the first app in the rotation list
    await page.locator('ul li button').first().click()

    // detail panel appears with real controls
    await expect(page.getByRole('button', { name: 'remove' })).toBeVisible()
    await expect(page.getByText('weight')).toBeVisible()
    await expect(page.locator('img[src*="/static/outputs/"]').first()).toBeVisible({ timeout: 20_000 })
  })

  test('Panels: builder renders a live preview', async ({ page }) => {
    test.slow() // pixlet render
    await page.goto('/panels')
    await expect(page.getByText('Panel Builder')).toBeVisible()

    await page.getByRole('button', { name: 'Preview', exact: true }).first().click()
    await expect(page.locator('img[src*="panel_"]')).toBeVisible({ timeout: 30_000 })
  })

  test('Playlists & Schedule render with controls', async ({ page }) => {
    await page.goto('/playlists')
    await expect(page.getByRole('button', { name: /^mon$/i }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /^sun$/i }).first()).toBeVisible()
    await expect(page.locator('input[type="time"]').first()).toBeVisible()
  })

  test('Devices: switcher drives an independent per-device rotation', async ({ page }) => {
    // self-cleaning: ensure no leftover from a prior run, delete again at the end
    await page.request.delete('/api/devices/e2e_panel').catch(() => {})
    page.on('dialog', (d) => void d.accept())

    await page.goto('/devices')
    await expect(page.getByRole('heading', { name: 'Panels' })).toBeVisible()
    const switcher = page.getByRole('banner').getByRole('button', { name: 'E2E Panel', exact: true })

    // create a panel
    await page.getByPlaceholder('id (e.g. apollo)').fill('e2e_panel')
    await page.getByPlaceholder('Name').fill('E2E Panel')
    await page.getByRole('button', { name: 'Add panel' }).click()
    await expect(switcher).toBeVisible()

    // switch to it — its rotation is empty and independent of Main's
    await switcher.click()
    await page.getByRole('button', { name: 'Apps', exact: true }).click()
    await expect(page.getByText(/Rotation · 0/)).toBeVisible()

    // the selection survives a hard refresh (persisted to localStorage)
    await page.reload()
    await expect(page.getByText(/Rotation · 0/)).toBeVisible()

    await page.request.delete('/api/devices/e2e_panel')
  })

  test('Store: catalog loads and a community app renders a preview', async ({ page }) => {
    test.slow() // first run may clone the community repo + pixlet render
    await page.goto('/store')
    await expect(page.getByText('Community Store')).toBeVisible()

    const firstPreview = page.getByRole('button', { name: 'Preview', exact: true }).first()
    await expect(firstPreview).toBeVisible({ timeout: 60_000 }) // catalog load
    await firstPreview.click()

    // the rendered pixel-art frame is displayed
    await expect(page.locator('img[src*="/static/outputs/"]').first()).toBeVisible({ timeout: 30_000 })
  })
})
