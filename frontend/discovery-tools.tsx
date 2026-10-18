import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { AnimatePresence, LazyMotion, domAnimation, m, MotionConfig, useReducedMotion } from 'framer-motion';
import { getSaved, subscribe, toggleSaved, sharedSlugs, saveSlugs, shareUrl } from './discovery-state';

type EventPick = { slug: string; title: string; category: string; categoryLabel: string; city: string; venue: string; date: string; startAt: string; price: string | null; available: boolean; image: string; url: string };
type Mode = 'vibe' | 'squad';
const moods = [
  { id: 'up', symbol: '↗', title: 'Turn it up', description: 'Big sound. Late nights. All the energy.', categories: ['concert', 'festival', 'nightlife'] },
  { id: 'easy', symbol: '≈', title: 'Keep it easy', description: 'Live sounds, creative spaces, good company.', categories: ['concert', 'theatre', 'other'] },
  { id: 'laugh', symbol: '☺', title: 'Make me laugh', description: 'The kind of night your cheeks remember.', categories: ['comedy'] },
  { id: 'surprise', symbol: '✳', title: 'Surprise me', description: 'A new story. Something out of the ordinary.', categories: [] },
];
const money = (price: string) => `KES ${new Intl.NumberFormat('en-KE', { maximumFractionDigits: 2 }).format(Number(price))}`;
function Icon({ name }: { name: string }) { return <svg className="icon" aria-hidden="true"><use href={`#i-${name}`} /></svg>; }
async function getCatalog(slugs?: string[], signal?: AbortSignal): Promise<EventPick[]> {
  const endpoint = document.getElementById('discovery-tools')?.dataset.catalogUrl || '/discover/catalog/';
  const url = new URL(endpoint, location.origin);
  if (slugs) url.searchParams.set('slugs', slugs.join(','));
  const response = await fetch(url, { signal, credentials: 'same-origin' });
  if (!response.ok) throw new Error('Events could not load. Please try again.');
  return (await response.json()).events;
}

function PickCard({ event, onSave }: { event: EventPick; onSave: (slug: string) => void }) {
  const saved = useSyncExternalStore(subscribe, getSaved);
  const isSaved = saved.includes(event.slug);
  return <article className="tool-event-card"><a href={event.url} tabIndex={-1} aria-hidden="true"><img src={event.image} alt="" width="120" height="130" /></a><div><span className="eyebrow">{event.categoryLabel} / {event.city}</span><h3><a href={event.url}>{event.title}</a></h3><p>{event.date} EAT</p><p>{event.available && event.price !== null ? `From ${money(event.price)} + fee` : 'Check ticket availability'}</p><div className="tool-event-actions"><a href={event.url} className="text-link">{event.available ? 'Get tickets' : 'View event'} <span>↗</span></a><button type="button" aria-label={`${isSaved ? 'Remove' : 'Save'} ${event.title}`} aria-pressed={isSaved} onClick={() => onSave(event.slug)}><Icon name="bookmark" />{isSaved ? 'Saved' : 'Save for squad'}</button></div></div></article>;
}

function Discovery({ mode }: { mode: Mode }) {
  const saved = useSyncExternalStore(subscribe, getSaved);
  const [shared] = useState(sharedSlugs);
  const [events, setEvents] = useState<EventPick[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState(true);
  const [step, setStep] = useState(0);
  const [mood, setMood] = useState('');
  const [city, setCity] = useState('');
  const [budget, setBudget] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const reduce = useReducedMotion();
  const requestedSlugs = [...new Set([...shared, ...saved])];
  const slugKey = requestedSlugs.join(',');
  const currentSlugs = mode === 'squad' ? requestedSlugs : [];
  useLayoutEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    const element = dialog.current;
    element?.showModal();
    heading.current?.focus({ preventScroll: true });
    document.body.style.overflow = 'hidden';
    return () => { element?.close(); document.body.style.overflow = overflow; previous?.focus({ preventScroll: true }); };
  }, [open]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    const load = mode === 'squad'
      ? Promise.all([getCatalog(currentSlugs.slice(0, 8), controller.signal), ...(currentSlugs.length > 8 ? [getCatalog(currentSlugs.slice(8, 16), controller.signal)] : [])]).then(groups => groups.flat())
      : getCatalog(undefined, controller.signal);
    load.then(data => { setEvents(data); setLoading(false); }).catch(reason => { if (!controller.signal.aborted) { setError(reason.message || 'Please try again.'); setLoading(false); } });
    return () => controller.abort();
  }, [mode, mode === 'squad' ? slugKey : '', attempt]);
  useEffect(() => { if (open) heading.current?.focus({ preventScroll: true }); }, [step, open]);
  const chosenMood = moods.find(option => option.id === mood);
  const picks = events.filter(event => event.available && (!city || city === event.city) && (!budget || (event.price !== null && Number(event.price) <= Number(budget))) && (!chosenMood?.categories.length || chosenMood.categories.includes(event.category))).slice(0, 3);
  const cities = [...new Set(events.map(event => event.city))].sort();
  const save = (slug: string) => setNotice(toggleSaved(slug));
  const share = async () => {
    try { await navigator.clipboard.writeText(shareUrl(currentSlugs.slice(0, 8))); setNotice('Squad link copied. Drop it in the group chat.'); }
    catch { setNotice('Copy the link below to send it to your squad.'); }
  };
  const title = mode === 'squad' ? 'Good plans are a group thing.' : step === 0 ? 'What’s your energy?' : step === 1 ? 'Make it your kind of night.' : 'This feels like you.';
  if (!open) return null;
  return <dialog ref={dialog} className="discovery-dialog" aria-labelledby="discovery-title" onCancel={event => { event.preventDefault(); setOpen(false); }} onClick={event => { if (event.target === event.currentTarget) setOpen(false); }}>
    <m.div className="discovery-sheet" initial={{ opacity: 0, y: reduce ? 0 : 25, scale: reduce ? 1 : .97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: .28, ease: [0.22, 1, 0.36, 1] }}>
      <div className="tool-topline"><span className="eyebrow">{mode === 'squad' ? 'SQUAD SHORTLIST' : 'FIND MY VIBE'} <span className="gold">✳</span></span><button type="button" className="checkout-close" onClick={() => setOpen(false)} aria-label="Close discovery">×</button></div>
      <h2 id="discovery-title" ref={heading} tabIndex={-1}>{title}</h2>
      {mode === 'vibe' ? <div className="quiz-progress" aria-label={`Step ${step + 1} of 3`}>{[0, 1, 2].map(index => <span key={index} className={index <= step ? 'complete' : ''} />)}</div> : <p className="tool-description">Save the possibilities. Share the plan. Book when you're ready.</p>}
      {error ? <div className="tool-empty" role="alert"><p>{error}</p><button className="button button-outline" onClick={() => setAttempt(value => value + 1)}>Try again</button></div> : loading ? <div className="tool-loading" role="status"><span className="loading-orbit" />Finding the good stuff…</div> : mode === 'squad' ? <>
        {shared.length ? <div className="shared-notice"><Icon name="users" /><p>Your squad sent you {shared.length} pick{shared.length === 1 ? '' : 's'}. Save the ones you love to make them yours.</p></div> : null}
        {events.length ? <><div className="tool-event-list">{events.map(event => <PickCard key={event.slug} event={event} onSave={save} />)}</div>{events.length < currentSlugs.length ? <p className="tool-description">Some saved events have ended or are no longer available. <button className="inline-link" type="button" onClick={() => { saveSlugs(saved.filter(slug => events.some(event => event.slug === slug))); setNotice('Unavailable saved picks removed.'); }}>Clear unavailable picks</button></p> : null}<div className="squad-share"><button className="button button-gold" type="button" onClick={share}>Copy squad link <Icon name="share" /></button><a className="button button-outline" href={`https://wa.me/?text=${encodeURIComponent(`Our next night out? Pick your favourite: ${shareUrl(currentSlugs.slice(0, 8))}`)}`} target="_blank" rel="noopener">Share on WhatsApp ↗</a></div><label className="form-label share-link-label">Your planning link<input readOnly value={shareUrl(currentSlugs.slice(0, 8))} onFocus={event => event.target.select()} /></label><p className="tool-description">A shortlist holds up to 8 events. Saving a pick doesn't reserve tickets. Final prices and availability are shown when you book.</p></> : <div className="tool-empty"><Icon name="bookmark" /><h3>Your next story starts with a pick.</h3><p>Tap the bookmark on an event to save it here. Bring your friends in when you find your favourites.</p><button type="button" className="button button-gold" onClick={() => { setOpen(false); document.getElementById('events')?.scrollIntoView({ behavior: reduce ? 'instant' : 'smooth' }); }}>Explore events <Icon name="arrow" /></button></div>}
      </> : <AnimatePresence mode="wait"><m.div key={step} initial={{ opacity: 0, x: reduce ? 0 : 15 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: reduce ? 0 : -15 }} transition={{ duration: .18 }}>
        {step === 0 ? <><p className="tool-description">No wrong answers. Follow the feeling.</p><div className="mood-grid">{moods.map(option => <button key={option.id} type="button" className={`mood-card mood-${option.id}`} onClick={() => { setMood(option.id); setStep(1); }}><span className="mood-symbol">{option.symbol}</span><strong>{option.title}</strong><span>{option.description}</span><b aria-hidden="true">↗</b></button>)}</div></> : step === 1 ? <form className="vibe-preferences" onSubmit={event => { event.preventDefault(); setStep(2); }}><p className="tool-description">{chosenMood?.title}. Good choice. Let's find something that fits.</p><label className="form-label" htmlFor="vibe-city">Where are we going?<select id="vibe-city" value={city} onChange={event => setCity(event.target.value)}><option value="">I'm open — anywhere in Kenya</option>{cities.map(item => <option key={item} value={item}>{item}</option>)}</select></label><label className="form-label" htmlFor="vibe-budget">Your ticket budget<select id="vibe-budget" value={budget} onChange={event => setBudget(event.target.value)}><option value="">Show me everything</option><option value="1000">Up to KES 1,000</option><option value="2500">Up to KES 2,500</option><option value="5000">Up to KES 5,000</option></select></label><p className="tool-description">Budget applies to the ticket price. Service fees are shown at checkout.</p><button type="submit" className="button button-gold">Show my matches <Icon name="spark" /></button><button type="button" className="text-link" onClick={() => setStep(0)}>← Change my vibe</button></form> : <><p className="tool-description">{picks.length ? 'Real events that match your vibe, city and budget. Your move.' : 'Your vibe is a little ahead of the lineup. Try another city or a wider budget.'}</p><div className="tool-event-list">{picks.map(event => <PickCard key={event.slug} event={event} onSave={save} />)}</div>{!picks.length ? <div className="tool-empty"><Icon name="spark" /><h3>Keep a little room for spontaneity.</h3><p>New experiences are always worth coming back for.</p><a href="/#events" className="button button-outline">Explore all events ↗</a></div> : null}<button type="button" className="text-link quiz-restart" onClick={() => setStep(0)}>↻ Find a different feeling</button></>}
      </m.div></AnimatePresence>}
      <p className="tool-notice" role="status" aria-live="polite">{notice}</p>
    </m.div>
  </dialog>;
}
let root: Root | undefined;
let serial = 0;
export function showDiscovery(mode: Mode) {
  const element = document.getElementById('discovery-tools');
  if (!element) return;
  root ||= createRoot(element);
  root.render(<LazyMotion features={domAnimation} strict><MotionConfig reducedMotion="user"><Discovery key={++serial} mode={mode} /></MotionConfig></LazyMotion>);
}
