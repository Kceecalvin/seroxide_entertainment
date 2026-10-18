import { test, expect, type Page } from '@playwright/test';

const eventUrl = '/e/coastal-sound-festival/';
const ignoredPageErrors = new Set(['Transition was skipped']);
function collectPageErrors(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', error => {
    if (!ignoredPageErrors.has(error.message)) errors.push(error.message);
  });
  return errors;
}

// All data and payments use config.settings.browser_test and a /tmp database.
test('discovery renders real events, preserves filters and handles no matches', async ({ page }) => {
  const errors = collectPageErrors(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /LESS SCROLL/ })).toBeVisible();
  await expect(page.locator('.experience-card')).toHaveCount(3);
  await expect(page.locator('.hero-pass')).toHaveAttribute('href', eventUrl);
  await expect(page.locator('.hero-pass img')).toHaveAttribute('src', '/media/events/covers/beach-cover.jpg');
  await page.getByRole('searchbox').fill('Kilifi');
  await page.getByRole('button', { name: 'Find events', exact: true }).click();
  await expect(page.locator('.experience-card')).toHaveCount(1);
  await page.getByRole('navigation', { name: 'Filter by event category' }).getByRole('link', { name: 'Festival', exact: true }).click();
  await expect(page).toHaveURL(/q=Kilifi/);
  await expect(page.locator('.experience-card')).toHaveCount(1);
  await page.getByRole('searchbox').fill('No such experience');
  await page.getByRole('button', { name: 'Find events', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A little too specific?' })).toBeVisible();
  await page.getByRole('link', { name: 'Explore all events', exact: true }).click();
  await expect(page.locator('.experience-card')).toHaveCount(3);
  expect(errors).toEqual([]);
});

test('checkout enforces quantity caps, shows ticket-price totals and traps keyboard focus', async ({ page }) => {
  await page.goto(eventUrl);
  const selector = page.getByTestId('ticket-selector');
  await expect(selector).toBeVisible();
  await expect(selector.getByRole('button', { name: 'Select your tickets', exact: true })).toBeDisabled();
  const add = selector.getByRole('button', { name: 'Add one General admission ticket', exact: true });
  await add.click();
  await expect(selector.getByTestId('checkout-total')).toHaveText('KES 2,000.50');
  await add.click(); await add.click();
  await expect(add).toBeDisabled();
  await expect(selector.getByTestId('checkout-total')).toHaveText('KES 6,001.50');
  await selector.getByRole('button', { name: 'Remove one General admission ticket', exact: true }).click();
  const continueButton = selector.getByRole('button', { name: 'Continue with 2 tickets', exact: true });
  await continueButton.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('Full name', { exact: true })).toBeFocused();
  await expect(dialog.getByTestId('checkout-total')).toHaveText('KES 4,001');
  for (let index = 0; index < 14; index++) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(continueButton).toBeFocused();
});

test('guest M-Pesa purchase issues real QR tickets in the isolated simulation', async ({ page }) => {
  const errors = collectPageErrors(page);
  await page.goto(eventUrl);
  await page.getByRole('button', { name: 'Add one General admission ticket', exact: true }).click();
  await page.getByRole('button', { name: 'Continue with 1 ticket', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Full name', { exact: true }).fill('Browser Test Guest');
  await dialog.locator('[name="buyer_email"]').fill('browser-test@example.com');
  await dialog.getByLabel('M-Pesa phone number', { exact: true }).fill('0712345678');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Pay KES 2,000.50 with M-Pesa', exact: true }).click();
  await expect(page).toHaveURL(/\/tickets\/order\/SRX-.*\/success\//);
  await expect(page.getByRole('heading', { name: /You're going/ })).toBeVisible();
  await expect(page.getByRole('img', { name: 'Ticket QR code' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save or print your tickets' })).toBeVisible();
  const qr = page.getByRole('img', { name: 'Ticket QR code' });
  expect(await qr.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  expect(errors).toEqual([]);
});

test('card checkout requires email and completes the simulated Paystack path', async ({ page }) => {
  await page.goto(eventUrl);
  await page.getByRole('button', { name: 'Add one VIP ticket', exact: true }).click();
  await page.getByRole('button', { name: 'Continue with 1 ticket', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Debit / credit card', exact: true }).click();
  await expect(dialog.locator('[name="buyer_email"]')).toHaveAttribute('required', '');
  await dialog.getByLabel('Full name', { exact: true }).fill('Card Test Guest');
  await dialog.locator('[name="buyer_email"]').fill('card-test@example.com');
  await dialog.getByLabel('Phone number', { exact: true }).fill('0712345679');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Continue to card payment', exact: true }).click();
  await expect(page).toHaveURL(/\/tickets\/order\/SRX-.*\/success\//);
  await expect(page.getByRole('img', { name: 'Ticket QR code' })).toBeVisible();
});

test('sold-out waitlist submits and closed sales cannot be bought', async ({ page }) => {
  await page.goto(eventUrl);
  const selector = page.getByTestId('ticket-selector');
  await expect(selector.getByText('Sales ended', { exact: true })).toBeVisible();
  await expect(selector.getByRole('button', { name: 'Add one Closed release ticket' })).toHaveCount(0);
  const waitlist = selector.locator('.waitlist-form');
  await waitlist.getByText('Join the Early bird waitlist').click();
  await waitlist.getByLabel('Full name').fill('Waitlist Guest');
  await waitlist.getByLabel('Email').fill('waitlist@example.com');
  expect(await waitlist.locator('form').evaluate((form: HTMLFormElement) => form.checkValidity())).toBe(true);
  await waitlist.getByRole('button', { name: 'Notify me when tickets return' }).click();
  await expect(page.getByRole('status').filter({ hasText: "You're on the waitlist" })).toBeVisible();
  await page.goto('/e/a-night-of-comedy/');
  await expect(page.getByRole('heading', { name: "This one's a memory." })).toBeVisible();
  await expect(page.getByTestId('ticket-selector')).toHaveCount(0);
});

test('mobile layout, menu and sticky checkout work without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.locator('.mobile-menu summary').click();
  await expect(page.getByRole('navigation', { name: 'Mobile navigation' })).toBeVisible();
  await page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Discover events', exact: true }).click();
  await expect(page.locator('.mobile-menu')).not.toHaveAttribute('open', '');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => document.querySelectorAll('[data-reveal]').forEach(element => element.classList.add('is-visible')));
  await page.screenshot({ path: '/tmp/serotix-mobile-discovery.png', fullPage: true });
  await page.goto(eventUrl);
  await expect(page.locator('.mobile-booking-bar')).toBeVisible();
  await page.locator('.mobile-booking-bar').getByRole('button', { name: 'Get tickets', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Add one General admission ticket', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Add one General admission ticket', exact: true }).click();
  await page.locator('.mobile-booking-bar').getByRole('button', { name: 'Continue to checkout', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '/tmp/serotix-mobile-checkout.png' });
});

test('reduced motion omits WebGL and every breakpoint fits the viewport', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('.hero-pass')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('[data-three-scene] canvas')).toHaveCount(0);
  for (const width of [320, 375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.screenshot({ path: '/tmp/serotix-desktop-full.png', fullPage: true });
});

test('HTML fallback can purchase when JavaScript is disabled', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL: 'http://127.0.0.1:8766' });
  const page = await context.newPage();
  await page.goto(eventUrl);
  const form = page.locator('.checkout-fallback form');
  await expect(form).toBeVisible();
  await expect(form.getByText('Sales ended', { exact: true })).toBeVisible();
  await form.getByRole('spinbutton', { name: 'General admission ticket quantity', exact: true }).fill('1');
  await form.getByLabel('Full name', { exact: true }).fill('No Script Guest');
  await form.getByLabel('M-Pesa phone number', { exact: true }).fill('0712345680');
  const terms = form.locator('#fallback-terms');
  await terms.check();
  await expect(terms).toBeChecked();
  await form.getByRole('button', { name: 'Pay with M-Pesa' }).click();
  await expect(page).toHaveURL(/\/tickets\/order\/SRX-.*\/success\//);
  await expect(page.getByRole('img', { name: 'Ticket QR code' })).toBeVisible();
  void context.close().catch(() => undefined);
});

test('vibe quiz finds relevant real events and squad picks survive a reload', async ({ page }) => {
  const errors = collectPageErrors(page);
  await page.goto('/');
  await page.locator('[data-vibe-open]').first().click();
  const dialog = page.getByRole('dialog', { name: /energy/ });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', { name: /Turn it up/ }).click();
  const preferences = page.getByRole('dialog');
  await preferences.getByLabel('Where are we going?').selectOption('Nairobi');
  await preferences.getByLabel('Your ticket budget').selectOption('2500');
  await preferences.getByRole('button', { name: 'Show my matches' }).click();
  await expect(preferences.locator('.tool-event-card')).toHaveCount(1);
  await expect(preferences.getByRole('heading', { name: 'Nairobi After Dark' })).toBeVisible();
  await preferences.getByRole('button', { name: 'Save Nairobi After Dark', exact: true }).click();
  await expect(preferences.getByRole('button', { name: 'Remove Nairobi After Dark', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.screenshot({ path: '/tmp/serotix-vibe-results.png' });
  await preferences.getByRole('button', { name: 'Close discovery', exact: true }).click();
  await page.reload();
  await expect(page.locator('[data-squad-count]')).toHaveText('1');
  await page.getByRole('button', { name: 'Open squad shortlist', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('heading', { name: 'Nairobi After Dark' })).toBeVisible();
  await expect(page.getByRole('dialog').getByLabel('Your planning link')).toHaveValue(/squad=nairobi-after-dark/);
  expect(errors).toEqual([]);
});

test('shared squad links work in a fresh browser and reveal only public upcoming events', async ({ page }) => {
  await page.goto('/?squad=coastal-sound-festival,nairobi-after-dark,a-night-of-comedy#squad');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('.tool-event-card')).toHaveCount(2);
  await expect(dialog.getByText('Some saved events have ended', { exact: false })).toBeVisible();
  await dialog.getByRole('button', { name: 'Save Coastal Sound Festival', exact: true }).click();
  await expect(page.locator('[data-squad-count]')).toHaveText('1');
  await page.screenshot({ path: '/tmp/serotix-squad.png' });
});

test('an optional VIP upgrade changes the selected tier and discloses the exact price', async ({ page }) => {
  await page.goto(eventUrl);
  const selector = page.getByTestId('ticket-selector');
  await selector.getByRole('button', { name: 'Add one General admission ticket', exact: true }).click();
  await expect(selector.locator('.ticket-upgrade')).toContainText('+KES 2,499.50');
  await selector.getByRole('button', { name: /Switch to VIP/ }).click();
  await expect(selector.getByRole('status', { name: 'General admission quantity', exact: true })).toHaveText('0');
  await expect(selector.getByRole('status', { name: 'VIP quantity', exact: true })).toHaveText('1');
  await expect(selector.getByTestId('checkout-total')).toHaveText('KES 4,500');
  await expect(selector.locator('.ticket-upgrade')).toHaveCount(0);
});
