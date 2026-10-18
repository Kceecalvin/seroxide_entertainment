(() => {
  const safeHex = (value, fallback) => /^#[0-9a-f]{6}$/i.test(value || '') ? value : fallback;
  const rgb = value => [1,3,5].map(i => parseInt(value.slice(i,i+2),16));
  const hex = values => '#' + values.map(c => Math.max(0,Math.min(255,Math.round(c))).toString(16).padStart(2,'0')).join('');
  const luminance = values => values.map(c => c/255 <= .04045 ? c/255/12.92 : ((c/255+.055)/1.055)**2.4).reduce((sum,c,i)=>sum+c*[.2126,.7152,.0722][i],0);
  window.SeroTixPosterPalette = (accent, secondary) => {
    accent = safeHex(accent,'#e6ba70'); secondary = safeHex(secondary,'#255bea');
    const source=rgb(accent); let readable=source;
    for(let step=0;step<=20;step++) {
      readable=source.map(c=>c+(255-c)*step/20);
      if((luminance(readable)+.05)/(luminance([16,21,34])+.05)>=5)break;
    }
    return {'--event-accent':hex(readable),'--event-base':hex(source.map(c=>c*.13+6)), '--event-glow':accent,'--event-secondary':secondary,'--event-ink':'#101522'};
  };
  const root=document.querySelector('[data-poster-import]');
  if(!root)return;
  const form=root.closest('form');
  const upload=form.querySelector('[name="cover_image"]');
  const button=root.querySelector('[data-read-poster]');
  const status=root.querySelector('[data-import-status]');
  const review=root.querySelector('[data-import-review]');
  const fields=root.querySelector('[data-import-fields]');
  const image=root.querySelector('[data-import-image]');
  let result=null, controller=null, previewUrl='', generation=0;
  button.hidden=false;
  const labels={title:'Event name',venue:'Venue',city:'City',organizer_name:'Organizer name',start_at:'Starts (Nairobi time)'};
  upload.addEventListener('change',()=>{
    generation++; controller?.abort(); result=null;review.hidden=true;status.textContent='';button.disabled=false;
    if(previewUrl)URL.revokeObjectURL(previewUrl);
    const file=upload.files?.[0];
    if(file?.type.startsWith('image/')){previewUrl=URL.createObjectURL(file);image.src=previewUrl;image.hidden=false;}
  });
  button.addEventListener('click',async()=>{
    const file=upload.files?.[0];
    if(!file){status.textContent='Choose the poster file above first.';upload.focus();return;}
    if(file.size>5*1024*1024){status.textContent='Choose an image up to 5 MB.';return;}
    const current=++generation;
    controller?.abort();controller=new AbortController();
    const activeController=controller;
    const timer=setTimeout(()=>activeController.abort(),40000);
    button.disabled=true;review.hidden=true;status.textContent='Reading your poster and finding its colours…';
    const body=new FormData();body.append('poster',file);
    try {
      const response=await fetch(root.dataset.importUrl,{method:'POST',body,signal:controller.signal,headers:{'X-CSRFToken':form.querySelector('[name="csrfmiddlewaretoken"]').value},credentials:'same-origin'});
      if(current!==generation)return;
      if(!response.headers.get('content-type')?.includes('application/json'))throw Error(response.status===429?'Please wait a few minutes before reading another poster.':'Your session may have ended. Save your work, sign in again and retry.');
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'We could not read this poster.');
      result=data;fields.replaceChildren();
      Object.entries(data.fields).forEach(([name,value])=>{
        if(!labels[name])return;
        const row=document.createElement('div');row.className='poster-suggestion';
        const label=document.createElement('label');label.className='market-consent';
        const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.importSelect=name;
        checkbox.checked=!form.elements.namedItem(name)?.value;
        const caption=document.createElement('span');caption.textContent='Use suggested '+labels[name].toLowerCase();
        label.append(checkbox,caption);
        const input=document.createElement('input');input.type=name==='start_at'?'datetime-local':'text';input.value=value;input.dataset.importValue=name;
        input.setAttribute('aria-label','Suggested '+labels[name].toLowerCase());
        input.maxLength={title:200,venue:200,city:100,organizer_name:150}[name]||200;
        row.append(label,input);fields.append(row);
      });
      root.querySelector('[data-import-text]').value=data.text||'No readable text found. You can still use the colours.';
      root.querySelector('[data-import-note]').textContent=data.review_note;
      root.querySelector('[data-import-prices]').textContent=data.prices.length?'Prices spotted: '+data.prices.join(' · ')+'. Check these against your ticket tiers.':'';
      const swatches=root.querySelector('[data-import-swatches]');swatches.replaceChildren();
      data.palette.colours.forEach(colour=>{
        if(!/^#[0-9a-f]{6}$/i.test(colour))return;
        const swatch=document.createElement('span');swatch.style.backgroundColor=colour;swatch.title=colour;swatch.setAttribute('aria-label',colour);swatches.append(swatch);
      });
      review.hidden=false;
      status.textContent=data.warning||'Your poster is ready to review. Select what you want to use.';
    } catch(error) {
      if(current===generation)status.textContent=error.name==='AbortError'?'Reading took too long. Try again with a smaller or clearer poster.':error.message;
    } finally {clearTimeout(timer);if(current===generation)button.disabled=false;}
  });
  root.querySelector('[data-apply-poster]').addEventListener('click',()=>{
    if(!result)return;
    fields.querySelectorAll('[data-import-select]:checked').forEach(checkbox=>{
      const name=checkbox.dataset.importSelect;
      const input=form.elements.namedItem(name);
      const suggested=fields.querySelector(`[data-import-value="${name}"]`);
      if(input&&suggested){input.value=suggested.value;input.dispatchEvent(new Event('input',{bubbles:true}));}
    });
    if(root.querySelector('[data-apply-colours]').checked){
      [['poster_accent',result.palette.accent],['poster_secondary',result.palette.secondary]].forEach(([name,value])=>{
        const input=form.elements.namedItem(name);input.value=safeHex(value,'#e6ba70');input.dispatchEvent(new Event('input',{bubbles:true}));
      });
      const theme=form.querySelector('[name="theme"][value="poster"]');theme.checked=true;theme.dispatchEvent(new Event('change',{bubbles:true}));theme.dispatchEvent(new Event('input',{bubbles:true}));
    }
    status.textContent='Selected suggestions applied. Review your details below and save the draft.';
  });
  window.addEventListener('pagehide',()=>{controller?.abort();if(previewUrl)URL.revokeObjectURL(previewUrl);});
})();
