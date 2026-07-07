import { test, expect, type Page } from '@playwright/test'

const NAV = ['Home', 'Apps', 'Panels', 'Playlists', 'Store'] as const

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
    await expect(page.getByRole('button', { name: 'delete' })).toBeVisible()
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
