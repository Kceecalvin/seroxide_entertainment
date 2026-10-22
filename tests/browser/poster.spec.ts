import {test, expect, type Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';
test.use({reducedMotion:'reduce'});
async function login(page: Page, username='gate-owner'){
  await page.goto('/account/login/');
  await page.getByLabel('Email or username').fill(username);
  await page.getByLabel('Password',{exact:true}).fill('BrowserGate123!');
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.waitForURL(url=>!url.pathname.endsWith('/login/'));
}

test('mobile poster import uses real OCR, keeps existing details until selected and saves exact poster colours',async({page})=>{
  test.setTimeout(90_000);
  await page.setViewportSize({width:390,height:844});
  await login(page);
  await page.goto('/account/studio/new/');
  await page.getByLabel('Event name',{exact:true}).fill('My chosen event name');
  await page.getByLabel('Event poster / cover').setInputFiles('/tmp/serotix-browser-poster.png');
  await page.getByRole('button',{name:'Read poster & import colours ↗'}).click();
  await expect(page.getByRole('region',{name:'Review poster suggestions'})).toBeVisible({timeout:30_000});
  await expect(page.getByLabel('Suggested event name',{exact:true})).toHaveValue('COASTAL RHYTHMS');
  await expect(page.getByLabel('Use suggested event name',{exact:true})).not.toBeChecked();
  await expect(page.getByLabel('Event name',{exact:true})).toHaveValue('My chosen event name');
  await page.getByRole('button',{name:'Use selected suggestions'}).click();
  await expect(page.getByLabel('Event name',{exact:true})).toHaveValue('My chosen event name');
  await expect(page.getByRole('radio',{name:/From your poster/})).toBeChecked();
  await page.getByLabel('Use suggested event name',{exact:true}).check();
  await page.getByLabel('Use suggested city',{exact:true}).check();
  await page.getByRole('button',{name:'Use selected suggestions'}).click();
  await expect(page.getByLabel('Event name',{exact:true})).toHaveValue('COASTAL RHYTHMS');
  await expect(page.getByLabel('Starts (Nairobi time)',{exact:true})).toHaveValue('2030-12-20T19:00');
  await expect(page.getByLabel('City',{exact:true})).toHaveValue('KILIFI');
  await page.getByLabel('What should guests expect?').fill('Live music by the coast, with great food and space to dance.');
  const accent=await page.getByLabel('Main poster colour').inputValue();
  expect(['#102a43','#d78232']).toContain(accent);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.locator('[data-import-review]').screenshot({path:'/tmp/serotix-poster-evidence/mobile-import-review.png'});
  await page.getByRole('button',{name:'Save & continue to tickets'}).click();
  await expect(page).toHaveURL(/studio\/\d+\/#tickets/);
  await expect(page.getByLabel('Main poster colour')).toHaveValue(accent);
  await expect(page.getByRole('radio',{name:/From your poster/})).toBeChecked();
  await page.getByRole('link',{name:'Preview listing ↗'}).click();
  const themed=page.locator('.event-theme.theme-poster');
  expect(await themed.evaluate(el=>getComputedStyle(el).getPropertyValue('--event-glow').trim())).toBe(accent);
  await page.getByText('View the full event poster ↗',{exact:true}).click();
  await expect(page.locator('.event-full-poster img')).toBeVisible();
});

test('promotion workspace exports adverts, saves an offer enquiry and admin tracks follow-up',async({page,browser})=>{
  await page.setViewportSize({width:390,height:844});
  await login(page);
  const response=await page.goto('/account/studio/');
  expect(response?.status()).toBe(200);
  const card=page.locator('.market-event').filter({has:page.getByRole('heading',{name:'Coastal Sound Festival',exact:true})});
  await card.getByRole('link',{name:'Promote ↗',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Made from your event.'})).toBeVisible();
  const [square]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Download square advert'}).click()]);
  await square.saveAs('/tmp/serotix-poster-evidence/advert-square.png');
  const sq=await readFile('/tmp/serotix-poster-evidence/advert-square.png');
  expect(sq.readUInt32BE(16)).toBe(1080);expect(sq.readUInt32BE(20)).toBe(1080);
  await page.addScriptTag({path:'static/js/jsQR.js'});
  const decoded=await page.evaluate(async encoded=>{
    const img=new Image();img.src='data:image/png;base64,'+encoded;await img.decode();
    const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;
    const ctx=canvas.getContext('2d')!;ctx.drawImage(img,0,0);const pixels=ctx.getImageData(0,0,img.width,img.height);
    return (window as any).jsQR(pixels.data,pixels.width,pixels.height)?.data;
  },sq.toString('base64'));
  expect(decoded).toBe('https://serotix.co.ke/e/coastal-sound-festival/');
  const [story]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Download story advert'}).click()]);
  await story.saveAs('/tmp/serotix-poster-evidence/advert-story.png');
  const st=await readFile('/tmp/serotix-poster-evidence/advert-story.png');
  expect(st.readUInt32BE(16)).toBe(1080);expect(st.readUInt32BE(20)).toBe(1920);
  await page.getByLabel('Instagram',{exact:true}).check();
  await page.getByLabel('SeroTix placement',{exact:true}).check();
  await page.getByLabel('Who are you trying to reach?').fill('Nairobi and Kilifi music fans');
  await page.getByLabel('Budget guide (KES)').fill('5000');
  await page.getByRole('button',{name:'Request my promotion offer ↗'}).click();
  await expect(page.locator('.site-messages')).toContainText('No campaign has been booked or charged.');
  await expect(page.locator('.promotion-request')).toContainText('Offer requested');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'/tmp/serotix-poster-evidence/mobile-promote.png',fullPage:true});
  const context=await browser.newContext({baseURL:'http://127.0.0.1:8766',viewport:{width:390,height:844},reducedMotion:'reduce'});
  const admin=await context.newPage();await login(admin,'promo-admin');
  await admin.getByRole('link',{name:'Promotion enquiries',exact:true}).click();
  await expect(admin.getByRole('heading',{name:/Coastal Sound Festival/})).toBeVisible();
  await admin.getByLabel('Follow-up status').selectOption('contacted');
  await admin.getByRole('button',{name:/Update request/}).click();
  await page.reload();
  await expect(page.locator('.promotion-request')).toContainText('Team has followed up');
  await context.close();
});

for(const unbroken of [false,true]){
  test(`advert exports keep ${unbroken?'unbroken':'long'} event details clear of the QR and within the canvas`,async({page})=>{
    await login(page);
    await page.addInitScript(()=>{
      (window as any).advertText=[];
      const original=CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText=function(text,x,y,...rest){
        if(this.canvas.width===1080){
          const m=this.measureText(text);
          (window as any).advertText.push({text,left:x-m.actualBoundingBoxLeft,right:x+m.actualBoundingBoxRight,
            top:y-m.actualBoundingBoxAscent,bottom:y+m.actualBoundingBoxDescent});
        }
        return original.call(this,text,x,y,...rest);
      };
    });
    await page.route('**/account/studio/*/promote/',async route=>{
      const response=await route.fetch();
      const body=(await response.text()).replace(/(<script id="promotion-ad-data" type="application\/json">)(.*?)(<\/script>)/s,(_match,start,raw,end)=>{
        const data=JSON.parse(raw);
        data.title=unbroken?'W'.repeat(200):'The East African Coastal Music and Arts Festival — A Celebration of Live Performances, Food, Culture and Community Featuring Independent Artists from Nairobi, Mombasa, Kilifi and Beyond';
        data.venue=('The Waterfront Gardens and Open Air Amphitheatre, near the main entrance and northern beach access, ').repeat(3).slice(0,200)+', '+('Kilifi Coastal Arts District ').repeat(4).slice(0,100);
        data.organizer=('Coastal Music Arts and Community Collective ').repeat(4).slice(0,150);
        return start+JSON.stringify(data)+end;
      });
      await route.fulfill({response,body});
    });
    await page.goto('/account/studio/');
    await page.locator('.market-event').filter({has:page.getByRole('heading',{name:'Coastal Sound Festival',exact:true})}).getByRole('link',{name:'Promote ↗',exact:true}).click();
    for(const format of ['square','story']){
      await page.evaluate(()=>{(window as any).advertText=[];});
      const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:`Download ${format} advert`}).click()]);
      const path=`/tmp/serotix-advert-${unbroken?'unbroken':'long'}-${format}.png`;
      await download.saveAs(path);
      const height=format==='story'?1920:1080;
      const rows=await page.evaluate(()=>(window as any).advertText as Array<{text:string,left:number,right:number,top:number,bottom:number}>);
      expect(rows.length).toBeGreaterThan(8);
      for(const row of rows){
        expect(row.left,row.text).toBeGreaterThanOrEqual(0);
        expect(row.right,row.text).toBeLessThanOrEqual(1080);
        expect(row.top,row.text).toBeGreaterThanOrEqual(0);
        expect(row.bottom,row.text).toBeLessThanOrEqual(height);
        expect(row.right>816&&row.left<1016&&row.bottom>height-240&&row.top<height-40,`QR overlaps ${row.text}`).toBe(false);
      }
      for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){
        const a=rows[i],b=rows[j];
        expect(a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top,`Text overlaps: ${a.text} / ${b.text}`).toBe(false);
      }
      if(unbroken)await expect(page.locator('[data-export-status]')).toContainText('Shortened to fit:');
      else expect(rows.map(row=>row.text).join(' ')).toContain('Kilifi and Beyond');
    }
  });
}
