import { setupSellerStudio } from './seller-studio';
setupSellerStudio();
/** Small progressive-enhancement entry; checkout and WebGL are independent chunks. */
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
import { setupDiscovery } from './discovery-state';
import { setupCategoryScroll } from './category-scroll';
setupDiscovery();
setupCategoryScroll();
if (!reducedMotion.matches) {
  import('./interface-motion').then(({ enhanceInterface }) => enhanceInterface()).catch(() => {});
}

const checkout = document.getElementById('ticket-checkout');
const checkoutData = document.getElementById('checkout-data');
if (checkout && checkoutData) {
  import('./checkout').then(({ mountCheckout }) => {
    mountCheckout(checkout, JSON.parse(checkoutData.textContent || '{}'));
  }).catch(() => {
    // Keep the server-rendered purchase form available if the bundle can't load.
    checkout.dataset.enhancement = 'unavailable';
  });
}

// A real share action with a clipboard fallback and an announced outcome.
for (const button of document.querySelectorAll<HTMLButtonElement>('[data-share]')) {
  button.addEventListener('click', async () => {
    const status = button.parentElement?.querySelector<HTMLElement>('[role="status"]');
    try {
      if (navigator.share) {
        await navigator.share({ title: button.dataset.title, url: location.href });
      } else {
        await navigator.clipboard.writeText(location.href);
        if (status) {
          status.classList.remove('sr-only');
          status.textContent = 'Link copied';
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      if (status) {
        status.classList.remove('sr-only');
        status.textContent = 'Copy the page address to share this event.';
      }
    }
  });
}

for (const button of document.querySelectorAll<HTMLButtonElement>('[data-print-tickets]')) {
  button.addEventListener('click', () => window.print());
}

// Close the small-screen navigation after choosing an in-page destination.
const mobileMenu = document.querySelector<HTMLDetailsElement>('.mobile-menu');
mobileMenu?.querySelectorAll('a').forEach(link => link.addEventListener('click', () => { mobileMenu.open = false; }));
window.addEventListener('keydown', event => { if (event.key === 'Escape' && mobileMenu) mobileMenu.open = false; });

const hero = document.querySelector<HTMLElement>('[data-hero-art]');
if (hero && !reducedMotion.matches) {
  import('./hero-motion').then(({ enhanceHero }) => enhanceHero(hero)).catch(() => {});
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  // Heavy decoration waits until the page has loaded, and is omitted on data-saver
  // connections. CSS and the server-rendered ticket remain the baseline experience.
  if (!connection?.saveData && !/^(slow-)?2g$/.test(connection?.effectiveType || '')) {
    const loadScene = () => {
      if (reducedMotion.matches || !hero.isConnected) return;
      import('./ticket-scene').then(({ mountScene }) => {
        const scene = hero.querySelector<HTMLElement>('[data-three-scene]');
        if (scene) mountScene(scene);
      }).catch(() => {});
    };
    const schedule = () => {
      if ('requestIdleCallback' in window) window.requestIdleCallback(loadScene, { timeout: 2500 });
      else setTimeout(loadScene, 600);
    };
    if (document.readyState === 'complete') schedule();
    else window.addEventListener('load', schedule, { once: true });
  }
}

// Cross-document transitions can be skipped by browser navigation or reduced
// motion; a skipped decorative transition is not an application failure.
window.addEventListener('pagereveal', event => {
  const transition = (event as Event & {viewTransition?: {ready: Promise<void>; finished: Promise<void>}}).viewTransition;
  transition?.ready.catch(() => {});
  transition?.finished.catch(() => {});
});
