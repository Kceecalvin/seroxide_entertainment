import { test, expect } from '@playwright/test';

test('mobile categories scroll, retain filters and reveal the selected category', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?city=Nairobi&when=month');
  const rail = page.getByRole('navigation', { name: 'Filter by event category' });
  await rail.scrollIntoViewIfNeeded();
  const next = page.getByRole('button', { name: 'Scroll categories right' });
  await expect(next).toBeVisible();
  await expect(page.getByRole('button', { name: 'Scroll categories left' })).toBeDisabled();
  await next.click();
  await expect.poll(() => rail.evaluate(el => el.scrollLeft)).toBeGreaterThan(100);
  await expect(page.getByRole('button', { name: 'Scroll categories left' })).toBeEnabled();
  await rail.getByRole('link', { name: 'Other', exact: true }).click();
  await expect(page).toHaveURL(/category=other/);
  expect(new URL(page.url()).searchParams.get('city')).toBe('Nairobi');
  expect(new URL(page.url()).searchParams.get('when')).toBe('month');
  const selected = rail.locator('[aria-current]');
  await expect(selected).toHaveAccessibleName('Other');
  await expect.poll(() => selected.evaluate(el => {
    const item = el.getBoundingClientRect();
    const container = el.parentElement!.getBoundingClientRect();
    return item.left >= container.left && item.right <= container.right + 1;
  })).toBe(true);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(selected).toHaveCSS('animation-name', 'none');
  await page.screenshot({ path: '/tmp/serotix-mobile-filters.png' });
});

test('mobile categories remain usable without JavaScript', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 320, height: 800 } });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:8766/');
  const rail = page.getByRole('navigation', { name: 'Filter by event category' });
  await rail.getByRole('link', { name: 'Festival', exact: true }).click();
  await expect(page).toHaveURL(/category=festival/);
  await expect(rail.locator('[aria-current]')).toHaveAccessibleName('Festival');
  await expect(page.getByRole('button', { name: 'Scroll categories right' })).toBeHidden();
  await context.close();
});
