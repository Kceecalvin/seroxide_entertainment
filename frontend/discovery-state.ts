const STORAGE_KEY = 'serotix:squad:v1';
const LIMIT = 8;
let saved: string[] = [];
const listeners = new Set<() => void>();
const validSlugs = (value: unknown): string[] => Array.isArray(value) ? [...new Set(value.filter((slug): slug is string => typeof slug === 'string' && /^[a-z0-9-]{1,220}$/.test(slug)))].slice(0, LIMIT) : [];
try { saved = validSlugs(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')); } catch { /* Private browsing can block storage. */ }
export const getSaved = () => saved;
export const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export function saveSlugs(slugs: string[]) {
  saved = validSlugs(slugs);
  let persisted = true;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(saved)); } catch { persisted = false; }
  listeners.forEach(listener => listener());
  return persisted;
}
export function toggleSaved(slug: string) {
  if (!saved.includes(slug) && saved.length >= LIMIT) return 'Your shortlist has 8 picks. Remove one to make room.';
  const removing = saved.includes(slug);
  const persisted = saveSlugs(removing ? saved.filter(item => item !== slug) : [...saved, slug]);
  return `${removing ? 'Removed from' : 'Saved to'} your squad shortlist.${persisted ? '' : ' This browser can only keep picks for this visit; share the link to save them.'}`;
}
export function sharedSlugs() { return validSlugs(new URLSearchParams(location.search).get('squad')?.split(',') || []); }
export function shareUrl(slugs: string[]) { const url = new URL('/', location.origin); url.searchParams.set('squad', validSlugs(slugs).join(',')); url.hash = 'squad'; return url.toString(); }
window.addEventListener('storage', event => { if (event.key === STORAGE_KEY) { try { saved = validSlugs(JSON.parse(event.newValue || '[]')); listeners.forEach(listener => listener()); } catch { /* Ignore malformed external changes. */ } } });

export function setupDiscovery() {
  let loaded: Promise<typeof import('./discovery-tools')> | undefined;
  const announce = (message: string) => {
    let notice = document.getElementById('discovery-status');
    if (!notice) { notice = document.createElement('div'); notice.id = 'discovery-status'; notice.className = 'discovery-toast'; notice.setAttribute('role', 'status'); document.body.appendChild(notice); }
    notice.textContent = message;
    notice.hidden = false;
    setTimeout(() => { if (notice?.textContent === message) notice.hidden = true; }, 4500);
  };
  const open = (mode: 'vibe' | 'squad') => {
    (loaded ||= import('./discovery-tools')).then(module => module.showDiscovery(mode)).catch(() => { loaded = undefined; announce('Could not open that just now. Please try again.'); });
  };
  const update = () => {
    document.querySelectorAll('[data-squad-count]').forEach(count => { count.textContent = String(saved.length); });
    document.querySelectorAll<HTMLButtonElement>('[data-save-event]').forEach(button => { const selected = saved.includes(button.dataset.saveEvent || ''); button.setAttribute('aria-pressed', String(selected)); button.title = selected ? 'Remove from squad shortlist' : 'Save to squad shortlist'; });
  };
  document.documentElement.classList.add('discovery-ready');
  document.querySelectorAll<HTMLElement>('[data-vibe-open]').forEach(button => button.addEventListener('click', event => { event.preventDefault(); open('vibe'); }));
  document.querySelectorAll<HTMLElement>('[data-squad-open]').forEach(button => button.addEventListener('click', () => open('squad')));
  document.querySelectorAll<HTMLElement>('[data-save-event]').forEach(button => button.addEventListener('click', () => announce(toggleSaved(button.dataset.saveEvent || ''))));
  subscribe(update); update();
  if (sharedSlugs().length) open('squad');
}
