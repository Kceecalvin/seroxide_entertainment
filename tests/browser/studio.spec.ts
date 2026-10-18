import { test, expect, type Page } from '@playwright/test';
test.use({ reducedMotion: 'reduce' });
async function login(page: Page) {
  await page.goto('/account/login/');
  await page.getByLabel('Email or username').fill('gate-owner');
  await page.getByLabel('Password', {exact:true}).fill('BrowserGate123!');
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.waitForURL('**/account/studio/');
}
async function fits(page: Page) {
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
}
test('mobile organizer creates a themed draft, fixes a ticket error and submits for review', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  const errors: string[]=[];
  page.on('pageerror', e=>{if(e.message!=='Transition was skipped') errors.push(e.message);});
  await login(page);
  await fits(page);
  await page.screenshot({path:'/tmp/serotix-studio-evidence/mobile-home.png',fullPage:true});
  await page.getByRole('link',{name:'+ Create an event',exact:true}).click();
  await page.getByLabel('Event name',{exact:true}).fill('Studio launch night');
  await page.getByLabel('Category',{exact:true}).selectOption('concert');
  await page.getByLabel('What should guests expect?').fill('An open-air concert and great food by the coast.');
  await page.getByLabel('Venue',{exact:true}).fill('Coastal Gardens');
  await page.getByLabel('City',{exact:true}).fill('Kilifi');
  await page.getByLabel('Starts (Nairobi time)',{exact:true}).fill(new Date(Date.now()+14*86400000).toISOString().slice(0,16));
  await page.getByLabel('Event poster / cover').setInputFiles('static/img/events/beach-cover.jpg');
  await page.getByRole('radio',{name:/Coastal/}).check();
  await expect(page.locator('[data-studio-poster]')).toHaveClass(/theme-coastal/);
  await expect(page.locator('[data-save-status]')).toHaveText('Unsaved changes');
  await fits(page);
  await page.getByRole('button',{name:'Save & continue to tickets'}).click();
  await expect(page).toHaveURL(/studio\/\d+\/#tickets/);
  const editUrl=page.url().split('#')[0];
  await expect(page.getByRole('radio',{name:/Coastal/})).toBeChecked();
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow','2');
  await expect(page.getByRole('button',{name:'Submit for approval ↗'})).toBeDisabled();
  const form=page.locator('[data-new-tier]');
  await form.getByRole('button',{name:'VIP',exact:true}).click();
  await form.getByLabel('Price (KES)',{exact:true}).fill('0');
  await form.getByLabel('Number of tickets',{exact:true}).fill('50');
  await form.getByRole('button',{name:'Add ticket tier +'}).click();
  await expect(page.locator('[data-studio-errors]')).toBeVisible();
  await expect(form.getByLabel('Name',{exact:true})).toHaveValue('VIP');
  await expect(form.getByLabel('Number of tickets',{exact:true})).toHaveValue('50');
  await expect(form).toContainText('Paid tickets must have a price greater than zero.');
  await form.getByLabel('Price (KES)',{exact:true}).fill('1500');
  await form.getByRole('button',{name:'Add ticket tier +'}).click();
  await expect(page).toHaveURL(/#tickets$/);
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow','3');
  await expect(page.getByRole('button',{name:'Submit for approval ↗'})).toBeEnabled();
  await fits(page);
  await page.screenshot({path:'/tmp/serotix-studio-evidence/mobile-editor.png',fullPage:true});
  await page.getByRole('link',{name:'Preview listing ↗'}).click();
  await expect(page.locator('.event-theme')).toHaveClass(/theme-coastal/);
  await expect(page.locator('main')).toContainText('Coastal theme');
  await fits(page);
  await page.goto(editUrl);
  await page.getByRole('button',{name:'Submit for approval ↗'}).click();
  await expect(page.locator('.market-callout')).toContainText('In review');
  await expect(page.getByLabel('Event name',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Manage gate team ↗'})).toBeVisible();
  expect(errors).toEqual([]);
});
test('organizer search, empty state, themes and unsaved-change protection work on desktop', async ({page}) => {
  await login(page);
  await page.getByLabel('Find an event',{exact:true}).fill('Client B not mine');
  await page.getByRole('button',{name:'Find events',exact:true}).click();
  await expect(page.getByRole('heading',{name:'No matching events.'})).toBeVisible();
  await page.getByRole('link',{name:'Clear filters'}).click();
  await expect(page.getByRole('heading',{name:'Coastal Sound Festival',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Nairobi After Dark',exact:true})).toHaveCount(0);
  await page.screenshot({path:'/tmp/serotix-studio-evidence/desktop-home.png',fullPage:true});
  await page.getByRole('link',{name:'+ Create an event',exact:true}).click();
  const colors = new Set<string>();
  for (const value of ['classic','after-dark','coastal','gold-night','electric']) {
    await page.locator(`input[name=theme][value="${value}"]`).check();
    colors.add(await page.locator('[data-studio-poster]').evaluate(el=>getComputedStyle(el).backgroundImage));
  }
  expect(colors.size).toBe(5);
  await page.getByRole('radio',{name:/SeroTix signature/}).check();
  await page.screenshot({path:'/tmp/serotix-studio-evidence/desktop-editor.png',fullPage:true});
  await fits(page);
  const dialog=page.waitForEvent('dialog');
  const navigation=page.getByRole('link',{name:'← All your events'}).click();
  const warning=await dialog;
  expect(warning.type()).toBe('beforeunload');
  await warning.dismiss();
  await navigation;
  await expect(page).toHaveURL(/studio\/new/);
});
test('organizer essential forms and theme selection work without JavaScript', async ({browser}) => {
  const context=await browser.newContext({javaScriptEnabled:false,viewport:{width:360,height:800}});
  const page=await context.newPage();
  await login(page);
  await page.getByRole('link',{name:'+ Create an event',exact:true}).click();
  await expect(page.getByLabel('Event name',{exact:true})).toBeVisible();
  await page.getByRole('radio',{name:/Gold Night/}).check();
  await expect(page.getByRole('radio',{name:/Gold Night/})).toBeChecked();
  await fits(page);
  await context.close();
});


test('public event keeps its chosen theme around real ticket controls', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/e/coastal-sound-festival/');
  const theme = page.locator('.event-theme.theme-coastal');
  await expect(theme).toBeVisible();
  const booking = page.getByTestId('ticket-selector');
  await expect(booking).toBeVisible();
  expect(await booking.evaluate(el=>getComputedStyle(el).getPropertyValue('--event-accent').trim())).toBe('#87e2d0');
  await booking.getByRole('button',{name:'Add one General admission ticket',exact:true}).click();
  await expect(booking.getByRole('button',{name:/Continue|Select your tickets|Book|Get/,exact:false}).last()).toBeEnabled();
  await fits(page);
  await page.screenshot({path:'/tmp/serotix-studio-evidence/mobile-public-coastal.png',fullPage:true});
});
