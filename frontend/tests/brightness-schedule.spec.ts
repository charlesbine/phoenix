import { expect, test } from '@playwright/test'

test('Night Mode is default, and global time zone and custom steps can be changed', async ({ page, request }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text())
  })

  const id = 'e2e_brightness'
  const initialSettings = (await (await request.get('/api/settings/display')).json()).settings
  await request.delete(`/api/devices/${id}`)
  const created = await request.post('/api/devices', {
    data: { id, name: 'Schedule Test Panel', backend: 'wled', brightness: 64 },
  })
  expect(created.ok()).toBe(true)

  try {
    await page.goto('/devices')
    await expect(page).toHaveTitle(/Phoenix/)
    await expect(page.getByRole('heading', { name: 'Panels', exact: true })).toBeVisible()
    const zone = page.getByRole('combobox', { name: 'Time zone' })
    await zone.selectOption('America/New_York')
    await page.getByRole('button', { name: 'Save settings' }).click()
    await expect(page.getByText('Display settings saved.')).toBeVisible()

    const panel = page.locator('section').filter({ hasText: id })
    await expect(panel.getByText('Night Mode active')).toBeVisible()
    await panel.getByRole('button', { name: 'Turn off Night Mode' }).click()
    await expect(panel.getByText('Manual control')).toBeVisible()
    await panel.getByRole('button', { name: 'Use Night Mode' }).click()
    await expect(panel.getByText('Night Mode active')).toBeVisible()
    await panel.screenshot({ path: info.outputPath('night-mode-desktop.png') })

    await panel.getByText('Custom schedule', { exact: true }).click()
    await panel.getByLabel('Use custom schedule').check()
    for (const [index, brightness] of ['16', '64', '24', '0'].entries()) {
      await panel.getByRole('button', { name: 'Add time' }).click()
      await panel.getByLabel('Brightness (0–255)', { exact: true }).nth(index).fill(brightness)
    }
    await panel.getByRole('button', { name: 'Save custom schedule' }).click()
    await expect(panel.getByText('Custom schedule active')).toBeVisible()
    await panel.getByRole('button', { name: 'Use Night Mode' }).click()
    await expect(panel.getByText('Night Mode active')).toBeVisible()

    await page.reload()
    await expect(zone).toHaveValue('America/New_York')
    await panel.getByText('Custom schedule', { exact: true }).click()
    await expect(panel.getByLabel('Use custom schedule')).not.toBeChecked()
    await expect(panel.getByLabel('Start time').last()).toHaveValue('23:00')
    await expect(panel.getByLabel('Brightness (0–255)', { exact: true }).last()).toHaveValue('0')
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(panel.getByRole('button', { name: 'Save custom schedule' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    await panel.screenshot({ path: info.outputPath('night-mode-mobile.png') })

    const device = await (await request.get(`/api/devices/${id}`)).json()
    expect(device.brightness).toBe(64)
    expect(device.brightness_schedule).toMatchObject({ enabled: true, mode: 'night' })
    expect(errors).toEqual([])
  } finally {
    await request.put('/api/settings/display', { data: initialSettings })
    await request.delete(`/api/devices/${id}`)
  }
})
