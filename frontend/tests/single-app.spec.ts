import { expect, test } from '@playwright/test'

test('Single layout saves an app for this panel', async ({ page, request }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text())
  })

  const id = 'e2e_single_app'
  await request.delete(`/api/devices/${id}`)
  expect((await request.post('/api/devices', {
    data: { id, name: 'Single App Test Panel', backend: 'web' },
  })).ok()).toBe(true)

  try {
    const registered = await (await request.get('/api/apps')).json()
    for (const name of ['clock', 'pixel_planet']) {
      if (!registered.some((app: { name: string }) => app.name === name)) {
        expect((await request.post(`/api/apps/${name}/add`)).ok()).toBe(true)
      }
      expect((await request.post(`/api/apps/${name}/add?device=${id}`)).ok()).toBe(true)
    }
    await page.addInitScript((device) => localStorage.setItem('phoenix.activeDevice', device), id)
    await page.goto('/')
    await expect(page).toHaveTitle(/Phoenix/)

    const layout = page.getByRole('combobox', { name: 'Layout', exact: true })
    const single = page.getByRole('combobox', { name: 'Single app', exact: true })
    await expect(layout).toHaveValue('cycle')
    await expect(single).toHaveCount(0)
    await layout.selectOption('single')
    await expect(single).toHaveValue('')
    await single.selectOption('pixel_planet')
    await expect(single).toBeEnabled()
    await page.reload()
    await expect(single).toHaveValue('pixel_planet')

    const controls = page.getByText('Panel controls', { exact: true }).locator('../..')
    await controls.screenshot({ path: info.outputPath('single-app-desktop.png') })
    await layout.selectOption('cycle')
    await expect(single).toHaveCount(0)
    await layout.selectOption('single')
    await expect(single).toHaveValue('pixel_planet')

    await page.setViewportSize({ width: 390, height: 844 })
    await expect(single).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await controls.screenshot({ path: info.outputPath('single-app-mobile.png') })

    const rotation = await (await request.get(`/api/apps?device=${id}`)).json()
    expect(rotation.map((app: { name: string }) => app.name)).toEqual(['clock', 'pixel_planet'])
    expect((await request.post(`/api/apps/pixel_planet/disable?device=${id}`)).ok()).toBe(true)
    await expect(single).toHaveValue('')
    await expect(single.locator('option[value="pixel_planet"]')).toHaveCount(0)
    expect(errors).toEqual([])
  } finally {
    await request.delete(`/api/devices/${id}`)
  }
})
