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
    await expect(panel.getByText('Night Mode enabled')).toBeVisible()
    await panel.getByRole('button', { name: 'Turn off Night Mode' }).click()
    await expect(panel.getByText('Manual control')).toBeVisible()
    await panel.getByRole('button', { name: 'Use Night Mode' }).click()
    await expect(panel.getByText('Night Mode enabled')).toBeVisible()
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
    await expect(panel.getByText('Night Mode enabled')).toBeVisible()

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

test('Panel Controls keeps the schedule note on one line as the phase changes', async ({ page, request }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text())
  })

  const id = 'e2e_night_phase'
  const { settings, timezones } = await (await request.get('/api/settings/display')).json()
  const offsetZones = (timezones as string[]).filter((zone) => zone.startsWith('Etc/GMT'))
  const now = new Date()
  const zoneFor = (hour: number) => {
    const zone = offsetZones.find((candidate) => new Intl.DateTimeFormat('en-GB', {
      timeZone: candidate, hour: '2-digit', hourCycle: 'h23',
    }).format(now) === String(hour).padStart(2, '0'))
    if (!zone) throw new Error(`No test time zone for local hour ${hour}`)
    return zone
  }

  await request.delete(`/api/devices/${id}`)
  expect((await request.post('/api/devices', {
    data: { id, name: 'Night Mode Test Panel', backend: 'serial', brightness: 200 },
  })).ok()).toBe(true)

  try {
    await page.addInitScript((device) => localStorage.setItem('phoenix.activeDevice', device), id)
    await page.goto('/')
    await expect(page).toHaveTitle(/Phoenix/)
    await expect(page.getByText('Panel controls', { exact: true })).toBeVisible()
    const controls = page.getByText('Panel controls', { exact: true }).locator('../..')

    for (const [hour, label] of [[12, 'Night Mode enabled'], [21, 'Night Mode dimming'], [4, 'Night Mode · panel off']] as const) {
      expect((await request.put('/api/settings/display', { data: { timezone: zoneFor(hour) } })).ok()).toBe(true)
      const note = controls.getByRole('link', { name: label, exact: true })
      for (const width of [1280, 768, 390]) {
        await page.setViewportSize({ width, height: 844 })
        await expect(note).toBeVisible()
        expect(await note.evaluate((element) => {
          const range = document.createRange()
          range.selectNodeContents(element)
          return range.getClientRects().length
        })).toBe(1)
        const noteBox = await note.boundingBox()
        const sliderBox = await controls.getByRole('slider').boundingBox()
        expect(noteBox!.x + noteBox!.width).toBeLessThanOrEqual(sliderBox!.x + sliderBox!.width + 1)
        await controls.screenshot({ path: info.outputPath(`night-phase-${hour}-${width}.png`) })
      }
      await expect(note).toHaveAttribute('href', '/devices')
    }

    expect((await request.put(`/api/devices/${id}/brightness-schedule`, {
      data: { enabled: false, mode: 'night', steps: [] },
    })).ok()).toBe(true)
    await expect(controls.getByRole('link', { name: /Night Mode/ })).toHaveCount(0)
    expect(errors).toEqual([])
  } finally {
    await request.put('/api/settings/display', { data: settings })
    await request.delete(`/api/devices/${id}`)
  }
})
