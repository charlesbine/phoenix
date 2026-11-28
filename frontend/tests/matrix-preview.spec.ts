import { expect, test } from '@playwright/test'

test('matrix_clock renders and displays an animated preview on Render preview click', async ({ page }) => {
  await page.request.post('/api/apps/matrix_clock/add?device=main')

  await page.goto('/apps')
  await expect(page.getByText(/Rotation ·/)).toBeVisible()

  await page.locator('ul li button', { hasText: 'matrix_clock' }).first().click()

  const renderBtn = page.getByRole('button', { name: /render preview/i })
  await expect(renderBtn).toBeVisible()
  await renderBtn.click()

  const preview = page.getByRole('img', { name: 'Matrix preview' })
  await expect(preview).toBeVisible({ timeout: 10_000 })
  await expect(preview).toHaveAttribute('src', /\/static\/outputs\/matrix_clock\.large\.webp\?t=/)
  await expect.poll(async () => preview.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
})
