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
  function linesFor(context,text,width){
    const lines=[];let line='';
    for(const word of String(text).trim().split(/\s+/)){
      const candidate=line?line+' '+word:word;
      if(context.measureText(candidate).width<=width){line=candidate;continue;}
      if(line){lines.push(line);line='';}
      // Long names and URLs must also fit, even when they contain no spaces.
      for(const character of word){
        if(line&&context.measureText(line+character).width>width){lines.push(line);line='';}
        line+=character;
      }
    }
    if(line)lines.push(line);
    return lines;
  }
  function fitted(context,text,{x=64,y,width=952,height,size,minSize=size,bold=false}){
    let lines,lineHeight;
    for(;;){
      context.font=`${bold?'bold ':''}${size}px Arial`;
      lineHeight=Math.ceil(size*1.2);
      lines=linesFor(context,text,width);
      if(lines.length*lineHeight<=height||size<=minSize)break;
      size=Math.max(minSize,size-2);
    }
    const maxLines=Math.max(1,Math.floor(height/lineHeight));
    const shortened=lines.length>maxLines;
    lines=lines.slice(0,maxLines);
    if(shortened){
      const last=Array.from(lines.at(-1));
      while(last.length&&context.measureText(last.join('')+'…').width>width)last.pop();
      lines[lines.length-1]=last.join('')+'…';
    }
    lines.forEach((line,index)=>context.fillText(line,x,y+size+index*lineHeight));
    return shortened;
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
      const shortened=[];
      const draw=(label,text,options)=>{if(fitted(ctx,text,options))shortened.push(label);};
      ctx.fillStyle=accent;
      draw('organizer name',data.organizer.toUpperCase(),{y:40,width:740,height:30,size:24,minSize:18,bold:true});
      ctx.font='bold 24px Arial';
      ctx.textAlign='right';ctx.fillText('serotix',1016,64);ctx.textAlign='left';
      const area={x:64,y:105,w:952,h:story?1120:450};
      ctx.fillStyle='#080b12';ctx.fillRect(area.x,area.y,area.w,area.h);
      const scale=Math.min(area.w/image.naturalWidth,area.h/image.naturalHeight);
      const w=image.naturalWidth*scale,h=image.naturalHeight*scale;
      ctx.drawImage(image,area.x+(area.w-w)/2,area.y+(area.h-h)/2,w,h);
      // Separate text regions reserve space for the QR and prevent long details
      // from pushing the call to action or link outside the exported image.
      const textWidth=data.qr?720:952;
      ctx.fillStyle=accent;
      draw('category',data.category.toUpperCase(),{y:story?1253:583,height:28,size:20,bold:true});
      ctx.fillStyle='#f4f0e6';
      draw('event name',data.title,{y:story?1290:619,height:story?264:148,size:story?64:48,minSize:26,bold:true});
      ctx.fillStyle='#c6d1e3';
      draw('date',data.date,{y:story?1580:789,width:textWidth,height:36,size:26,minSize:22});
      draw('venue',data.venue,{y:story?1630:835,width:textWidth,height:story?144:100,size:26,minSize:20});
      ctx.fillStyle=accent;
      draw('call to action',data.cta+' ↗',{y:story?1806:954,width:textWidth,height:40,size:28,bold:true});
      ctx.fillStyle='#b0bfd6';
      draw('event link',data.url||'Public booking link available after publication',{y:canvas.height-65,width:textWidth,height:48,size:18,minSize:16});
      if(data.qr){
        const qr=new Image();qr.src=data.qr;await qr.decode();
        ctx.imageSmoothingEnabled=false;ctx.drawImage(qr,816,canvas.height-240,200,200);
      }
      const blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(Error('Export failed')),'image/png'));
      const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`${data.slug}-${story?'story':'square'}.png`;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
      status.textContent=`${story?'Story':'Square'} advert downloaded. `+(shortened.length?`Shortened to fit: ${shortened.join(', ')}. Review the download and sharing caption before sharing.`:'Review the details before sharing.');
    }catch{status.textContent='The advert could not be exported. Try reloading the page or use your original poster.';}
    finally{controls.querySelectorAll('button').forEach(b=>b.disabled=false);}
  }));
})();
