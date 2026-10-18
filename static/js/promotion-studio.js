(() => {
  const copy=document.querySelector('[data-copy-caption]');
  if(copy){
    copy.hidden=false;
    copy.addEventListener('click',async()=>{
      const input=document.querySelector('#promotion-caption');
      const status=document.querySelector('[data-copy-status]');
      try{await navigator.clipboard.writeText(input.value);status.textContent='Caption copied. Paste it with your poster.';}
      catch{input.focus();input.select();status.textContent='Select and copy the caption above.';}
    });
  }
  const controls=document.querySelector('[data-ad-exports]');
  const board=document.querySelector('[data-ad-board]');
  const image=document.querySelector('[data-ad-image]');
  const raw=document.querySelector('#promotion-ad-data');
  if(!controls||!board||!image||!raw)return;
  const data=JSON.parse(raw.textContent);
  controls.hidden=false;
  function wrapped(context,text,x,y,maxWidth,lineHeight,maxLines=3){
    const words=String(text).split(/\s+/);let line='',lines=[];
    for(const word of words){
      if(context.measureText((line?line+' ':'')+word).width>maxWidth&&line){lines.push(line);line=word;}
      else line+=(line?' ':'')+word;
    }
    if(line)lines.push(line);
    lines=lines.slice(0,maxLines);
    lines.forEach(value=>{
      while(context.measureText(value).width>maxWidth&&value.length>1)value=value.slice(0,-2)+'…';
      context.fillText(value,x,y);y+=lineHeight;
    });
    return y;
  }
  controls.querySelectorAll('button').forEach(button=>button.addEventListener('click',async()=>{
    const status=document.querySelector('[data-export-status]');
    controls.querySelectorAll('button').forEach(b=>b.disabled=true);
    status.textContent='Preparing your advert…';
    try {
      await image.decode();
      const story=button.dataset.exportSize==='story';
      const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=story?1920:1080;
      const ctx=canvas.getContext('2d');
      const style=getComputedStyle(board);
      const accent=style.getPropertyValue('--event-accent').trim()||'#e6ba70';
      const base=style.getPropertyValue('--event-base').trim()||'#102348';
      const glow=style.getPropertyValue('--event-glow').trim()||'#255bea';
      const gradient=ctx.createLinearGradient(0,0,1080,canvas.height);gradient.addColorStop(0,base);gradient.addColorStop(1,'#080b12');
      ctx.fillStyle=gradient;ctx.fillRect(0,0,1080,canvas.height);
      ctx.fillStyle=glow;ctx.globalAlpha=.25;ctx.beginPath();ctx.arc(1050,80,320,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;
      ctx.fillStyle=accent;ctx.font='bold 24px Arial';wrapped(ctx,data.organizer.toUpperCase(),64,64,740,30,1);
      ctx.textAlign='right';ctx.fillText('serotix',1016,64);ctx.textAlign='left';
      const area={x:64,y:105,w:952,h:story?1190:515};
      ctx.fillStyle='#080b12';ctx.fillRect(area.x,area.y,area.w,area.h);
      const scale=Math.min(area.w/image.naturalWidth,area.h/image.naturalHeight);
      const w=image.naturalWidth*scale,h=image.naturalHeight*scale;
      ctx.drawImage(image,area.x+(area.w-w)/2,area.y+(area.h-h)/2,w,h);
      let y=area.y+area.h+48;
      ctx.fillStyle=accent;ctx.font='bold 20px Arial';wrapped(ctx,data.category.toUpperCase(),64,y,952,24,1);y+=44;
      ctx.fillStyle='#f4f0e6';ctx.font='bold '+(story?64:48)+'px Arial';y=wrapped(ctx,data.title,64,y,952,story?72:54,story?3:2)+14;
      ctx.fillStyle='#c6d1e3';ctx.font='26px Arial';y=wrapped(ctx,data.date,64,y,952,32,1);y=wrapped(ctx,data.venue,64,y,data.qr?720:952,32,2)+25;
      ctx.fillStyle=accent;ctx.font='bold 28px Arial';ctx.fillText(data.cta+' ↗',64,Math.min(y,canvas.height-80));
      ctx.fillStyle='#b0bfd6';ctx.font='18px Arial';wrapped(ctx,data.url||'Public booking link available after publication',64,canvas.height-35,data.qr?730:952,22,1);
      if(data.qr){
        const qr=new Image();qr.src=data.qr;await qr.decode();
        ctx.imageSmoothingEnabled=false;ctx.drawImage(qr,816,canvas.height-240,200,200);
      }
      const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(Error('Export failed')),'image/png'));
      const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`${data.slug}-${story?'story':'square'}.png`;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
      status.textContent=`${story?'Story':'Square'} advert downloaded. Review the details before sharing.`;
    }catch{status.textContent='The advert could not be exported. Try reloading the page or use your original poster.';}
    finally{controls.querySelectorAll('button').forEach(b=>b.disabled=false);}
  }));
})();
