import { expect, test } from '@playwright/test'

test('Home settings save and render the selected app while preserving custom keys', async ({ page, request }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text())
  })

  const id = 'e2e_settings'
  const app = 'procedural_planet'
  const original = (await (await request.get('/api/apps')).json())
    .find((row: { name: string }) => row.name === app)
  await request.delete(`/api/devices/${id}`)
  expect((await request.post('/api/devices', {
    data: { id, name: 'Desk Test Panel', backend: 'web' },
  })).ok()).toBe(true)

  try {
    if (!original) expect((await request.post(`/api/apps/${app}/add`)).ok()).toBe(true)
    expect((await request.post(`/api/apps/${app}/add?device=${id}`)).ok()).toBe(true)
    expect((await request.put(`/api/apps/${app}/config`, {
      data: { n_frames: '1', light_x: '0.35', seed: '42', planet_type: 'ice' },
    })).ok()).toBe(true)
    expect((await (await request.post(`/api/apps/${app}/preview`)).json()).preview).toBe(true)
    const before = await (await request.get(`/static/outputs/${app}.webp`)).body()

    let playerStatus = 'synced'
    await page.route('**/api/status', (route) => route.fulfill({ json: {
      status: playerStatus === 'offline' ? 'degraded' : 'ok',
      issues: playerStatus === 'offline' ? ['Desk player offline'] : [],
      player: { name: 'Desk', status: playerStatus },
    } }))
    await page.addInitScript((device) => localStorage.setItem('phoenix.activeDevice', device), id)
    await page.goto('/')
    await expect(page).toHaveTitle(/Phoenix/)
    await expect(page.getByText('Desk · synced', { exact: true })).toBeVisible()
    playerStatus = 'offline'
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await expect(page.getByText('Desk player offline', { exact: true })).toBeVisible()
    playerStatus = 'synced'
    await page.getByRole('button', { name: 'Refresh', exact: true }).click()
    await expect(page.getByText('Desk · synced', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: app, exact: true }).click()
    await page.getByText('Settings', { exact: true }).click()
    const planet = page.getByRole('combobox', { name: 'Planet type' })
    await expect(planet).toHaveValue('ice')
    await expect(page.getByText('Applies to all panels.')).toBeVisible()
    await planet.selectOption('lava')
    await page.getByRole('spinbutton', { name: 'Animation speed' }).fill('0.2')
    await page.getByRole('button', { name: 'Save & render' }).click()
    await expect(page.getByText('Preview updated.')).toBeVisible()
    const config = (await (await request.get(`/api/apps/${app}`)).json()).pixlet_config
    expect(config).toEqual({
      n_frames: '1', light_x: '0.35', seed: '42', planet_type: 'lava', time_speed: '0.2',
    })
    const after = await request.get(`/static/outputs/${app}.webp`)
    expect(after.ok()).toBe(true)
    expect((await after.body()).equals(before)).toBe(false)
    await page.locator('details').filter({ has: planet }).screenshot({ path: info.outputPath('settings-desktop.png') })

    await page.setViewportSize({ width: 390, height: 844 })
    await expect(planet).toHaveValue('lava')
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await page.locator('details').filter({ has: planet }).screenshot({ path: info.outputPath('settings-mobile.png') })
    expect(errors).toEqual([])
  } finally {
    await request.delete(`/api/devices/${id}`)
    if (original) await request.put(`/api/apps/${app}/config`, { data: original.pixlet_config })
    else await request.delete(`/api/apps/${app}`)
  }
})

test('Store shows a catalog error separately from empty search results', async ({ page }) => {
  let unavailable = true
  await page.route('**/api/store/categories', (route) => route.fulfill({ json: [] }))
  await page.route(/\/api\/store\?/, (route) => unavailable
    ? route.fulfill({ status: 503, json: { detail: 'Community catalog is unavailable.' } })
    : route.fulfill({ json: [] }))
  await page.goto('/store')
  await expect(page.getByRole('alert')).toHaveText('Community catalog is unavailable.')
  await expect(page.getByText('No apps found.', { exact: false })).toHaveCount(0)
  unavailable = false
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.getByText('No apps found.', { exact: false })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})
