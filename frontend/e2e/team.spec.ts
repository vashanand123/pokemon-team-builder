import { expect, test } from '@playwright/test'

// One end-to-end flow (single team keeps DB state unambiguous across the reload):
// build -> persist -> auto-fill -> counter-team, all via real clicks.
test('build, persist, auto-fill, and counter a team', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Pokémon Team Builder' })).toBeVisible()

  // Create a team and add Pikachu from the catalog.
  await page.getByRole('button', { name: '+ New team' }).click()
  await page.getByPlaceholder('Search name…').fill('pikachu')
  await page.getByRole('button', { name: '+ Add' }).first().click()
  await expect(page.getByRole('button', { name: 'Remove pikachu', exact: true })).toBeVisible()
  await page.screenshot({ path: 'e2e/_artifacts/team-built.png', fullPage: true })

  // Persists across a full reload (anonymous cookie + DB).
  await page.reload()
  await expect(page.getByRole('button', { name: 'Remove pikachu', exact: true })).toBeVisible()

  // Auto-fill the remaining slots -> 6 members total (6 remove buttons).
  await page.getByRole('button', { name: 'Auto-fill' }).click()
  await expect(page.getByRole('button', { name: /^Remove / })).toHaveCount(6)
  await page.screenshot({ path: 'e2e/_artifacts/autofilled.png', fullPage: true })

  // Generate the counter team -> result panel appears.
  await page.getByRole('button', { name: 'Counter this team' }).click()
  await expect(page.getByRole('heading', { name: 'Optimal counter team' })).toBeVisible()
  await page.screenshot({ path: 'e2e/_artifacts/counter.png', fullPage: true })

  // Simulate an upstream change to Pikachu (#25); the alert banner appears after refetch.
  // Admin endpoints are hit directly (not proxied through the frontend).
  await page.request.post('http://localhost:8000/admin/simulate-change?pokemon_id=25')
  await page.reload()
  await expect(page.getByText(/PokéAPI data changed/)).toBeVisible()
  await page.screenshot({ path: 'e2e/_artifacts/alert.png', fullPage: true })
})

