/** Native touch scrolling with optional controls; category links remain normal GETs. */
export function setupCategoryScroll() {
  const root = document.querySelector<HTMLElement>('[data-category-browser]');
  const rail = root?.querySelector<HTMLElement>('.category-filters');
  if (!root || !rail) return;
  const mobile = matchMedia('(max-width: 768px)');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const controls = root.querySelector<HTMLElement>('.category-scroll-controls')!;
  const track = root.querySelector<HTMLElement>('.category-scroll-track')!;
  const buttons = [...controls.querySelectorAll<HTMLButtonElement>('button')];
  const cards = [...rail.querySelectorAll<HTMLAnchorElement>('a')];
  const update = () => {
    const max = rail.scrollWidth - rail.clientWidth;
    const left = Math.max(0, Math.min(rail.scrollLeft, max));
    const overflows = mobile.matches && max > 2;
    controls.hidden = track.hidden = !overflows;
    root.dataset.scrollable = String(overflows);
    root.dataset.atStart = String(left <= 2);
    root.dataset.atEnd = String(left >= max - 2);
    buttons[0].disabled = left <= 2;
    buttons[1].disabled = left >= max - 2;
    const fraction = rail.clientWidth / Math.max(rail.scrollWidth, 1);
    track.style.setProperty('--thumb-width', `${fraction * 100}%`);
    track.style.setProperty('--thumb-left', `${max > 0 ? (left / max) * (1 - fraction) * 100 : 0}%`);
    const bounds = rail.getBoundingClientRect();
    cards.forEach(card => {
      const box = card.getBoundingClientRect();
      const distance = Math.max(-1, Math.min(1, (box.left + box.width / 2 - bounds.left - bounds.width / 2) / bounds.width));
      card.style.setProperty('--art-drift', `${mobile.matches && !reduced.matches ? distance * -9 : 0}px`);
      card.style.setProperty('--art-turn', `${mobile.matches && !reduced.matches ? distance * 14 - 8 : -8}deg`);
    });
  };
  const reveal = (link: HTMLElement, animate = true) => {
    if (!mobile.matches) return;
    const bounds = rail.getBoundingClientRect();
    const item = link.getBoundingClientRect();
    if (item.left >= bounds.left + 8 && item.right <= bounds.right - 8) return;
    rail.scrollTo({ left: rail.scrollLeft + item.left - bounds.left - (rail.clientWidth - item.width) / 2, behavior: animate && !reduced.matches ? 'smooth' : 'instant' });
  };
  buttons.forEach(button => button.addEventListener('click', () => {
    rail.scrollBy({ left: Number(button.dataset.categoryDirection) * rail.clientWidth * .7, behavior: reduced.matches ? 'instant' : 'smooth' });
  }));
  let frame = 0;
  rail.addEventListener('scroll', () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(update); }, { passive: true });
  reduced.addEventListener('change', update);
  rail.addEventListener('focusin', event => { if (event.target instanceof HTMLAnchorElement) reveal(event.target); });
  const layout = () => {
    const selected = rail.querySelector<HTMLElement>('[aria-current]');
    if (selected) reveal(selected, false);
    update();
  };
  new ResizeObserver(layout).observe(rail);
  document.fonts.ready.then(layout);
  const observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      root.dataset.revealed = 'true';
      observer.disconnect();
    }
  }, { threshold: .5 });
  observer.observe(root);
  layout();
}
