import { test, expect, type Page } from '@playwright/test';
async function login(page: Page, username: string) {
  await page.goto('/account/login/');
  await page.getByLabel('Email or username').fill(username);
  await page.getByLabel('Password', { exact: true }).fill('BrowserGate123!');
  await page.getByRole('button', { name: 'Log in', exact: true }).click();
  await page.waitForURL(url => !url.pathname.endsWith('/login/'));
}
async function post(page: Page, url: string, data: Record<string,string> = {}) {
  return page.evaluate(async ({url,data}) => {
    const csrf = (document.querySelector('[name=csrfmiddlewaretoken]') as HTMLInputElement | null)?.value || decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('csrftoken='))?.split('=').slice(1).join('=') || '');
    const response = await fetch(url,{method:'POST',headers:{'X-CSRFToken':csrf},body:new URLSearchParams(data)});
    const contentType=response.headers.get('content-type')||'';
    return {status:response.status,body:contentType.includes('json')?await response.json():null};
  },{url,data});
}
test('organizer invites a guard, guard selects event, supervisor sees activity, revoke blocks the signed-in scanner', async ({browser}) => {
  const ownerContext=await browser.newContext({baseURL:'http://127.0.0.1:8766',viewport:{width:390,height:844},reducedMotion:'reduce'});
  const guardContext=await browser.newContext({baseURL:'http://127.0.0.1:8766',viewport:{width:390,height:844},reducedMotion:'reduce'});
  const owner=await ownerContext.newPage();const guard=await guardContext.newPage();
  await login(owner,'gate-owner');
  await owner.getByRole('link',{name:'Gate team ↗',exact:true}).click();
  const match=owner.url().match(/studio\/(\d+)\/gate-team/)!;const eventId=match[1];
  const teamUrl=new URL(owner.url()).pathname;
  await owner.getByLabel('Guard’s account email').fill('gate-invitee@example.test');
  await owner.getByLabel('Gate / entrance').fill('North gate');
  // Input values are explicitly Nairobi time, independent of browser timezone.
  const local=(time:number)=>new Date(time+3*3600000).toISOString().slice(0,16);
  await owner.getByLabel('Shift starts (Nairobi time)').fill(local(Date.now()-3600000));
  await owner.getByLabel('Shift ends (Nairobi time)').fill(local(Date.now()+3600000));
  await owner.getByLabel('Gate supervisor').check();
  await owner.getByRole('button',{name:'Send gate invitation ↗'}).click();
  const invite=await owner.locator('#invitation-link').inputValue();
  expect(await owner.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await owner.screenshot({path:'/tmp/serotix-gates-evidence/mobile-team.png',fullPage:true});
  await guard.goto(invite);
  await expect(guard).toHaveURL(/account\/login/);
  await guard.getByLabel('Email or username').fill('gate-invitee');
  await guard.getByLabel('Password',{exact:true}).fill('BrowserGate123!');
  await guard.getByRole('button',{name:'Log in',exact:true}).click();
  await guard.getByRole('button',{name:'Accept my shift ↗'}).click();
  await expect(guard).toHaveURL(/tickets\/scan\/$/);
  await expect(guard.getByRole('heading',{name:'Coastal Sound Festival',exact:true})).toBeVisible();
  await expect(guard.getByRole('heading',{name:'Nairobi After Dark',exact:true})).toHaveCount(0);
  expect(await guard.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await guard.screenshot({path:'/tmp/serotix-gates-evidence/mobile-event-selection.png',fullPage:true});
  await guard.getByRole('button',{name:'Scan this event ↗',exact:true}).click();
  await guard.waitForFunction(() => Boolean((window as any).Alpine && (document.querySelector('[x-data^=ticketScanner]') as any)?._x_dataStack?.length));
  await guard.evaluate(() => (window as any).Alpine.$data(document.querySelector('[x-data^=ticketScanner]')).handleCode('/tickets/verify/22222222-2222-4222-8222-222222222222/'));
  await expect(guard.getByText('Wrong event',{exact:true})).toBeVisible();
  await expect(guard.getByText('Wrong event',{exact:true})).toBeHidden();
  const accepted=await post(guard,'/tickets/scan/api/11111111-1111-4111-8111-111111111111/',{event_id:eventId});
  expect(accepted.body.ok).toBe(true);
  const duplicate=await post(guard,'/tickets/scan/api/11111111-1111-4111-8111-111111111111/',{event_id:eventId});
  expect(duplicate.body.result).toBe('already_used');
  const overview=await guardContext.newPage();
  await overview.goto(`/tickets/scan/events/${eventId}/supervisor/`);
  await expect(overview.getByText('Admissions by guard',{exact:true})).toBeVisible();
  await expect(overview.getByText('Wrong event',{exact:true}).first()).toBeVisible();
  expect(await guard.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await overview.screenshot({path:'/tmp/serotix-gates-evidence/mobile-supervisor.png',fullPage:true});
  await owner.goto(teamUrl);
  await owner.getByRole('button',{name:'Revoke access for gate-invitee',exact:true}).click();
  // Use the old scanner page, retaining the same authenticated guard session.
  const denied=await post(guard,'/tickets/scan/api/11111111-1111-4111-8111-111111111111/',{event_id:eventId});
  expect(denied.status).toBe(403);expect(denied.body.result).toBe('not_assigned');
  await guard.evaluate(() => (window as any).Alpine.$data(document.querySelector('[x-data^=ticketScanner]')).handleCode('/tickets/verify/33333333-3333-4333-8333-333333333333/'));
  await expect(guard.getByText('Access ended',{exact:true})).toBeVisible();
  expect(await guard.evaluate(() => (window as any).Alpine.$data(document.querySelector('[x-data^=ticketScanner]')).stopped)).toBe(true);
  await overview.reload();
  await expect(overview.locator('body')).not.toContainText('Admissions by guard');
  await ownerContext.close();await guardContext.close();
});
