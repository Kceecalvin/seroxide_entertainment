import { animate, inView, scroll, stagger } from 'framer-motion/dom';

/** Fine-grained interaction motion, shared by every app page. */
export function enhanceInterface() {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
  const cleanups: Array<() => void> = [];
  const controls = new Set<ReturnType<typeof animate>>();
  const play = (...args: Parameters<typeof animate>) => {
    if (reduced.matches) return;
    const control = animate(...args);
    controls.add(control);
    Promise.resolve(control).finally(() => controls.delete(control));
    return control;
  };

  // Spring-driven navigation underline follows hover and keyboard focus.
  const nav = document.querySelector<HTMLElement>('.desktop-nav');
  if (nav) {
    const links = [...nav.querySelectorAll<HTMLAnchorElement>('a')];
    const indicator = document.createElement('span');
    indicator.className = 'nav-cursor';
    indicator.setAttribute('aria-hidden', 'true');
    nav.appendChild(indicator);
    nav.classList.add('has-motion');
    let navigationAnimation: ReturnType<typeof animate> | undefined;
    const move = (link?: HTMLAnchorElement) => {
      navigationAnimation?.stop();
      if (!link) { indicator.style.opacity = '0'; return; }
      if (reduced.matches) { indicator.style.opacity = '0'; return; }
      navigationAnimation = animate(indicator, { x: link.offsetLeft, width: link.offsetWidth, opacity: 1 }, { type: 'spring', stiffness: 330, damping: 30 });
    };
    const restore = () => move(links.find(link => link.hasAttribute('aria-current')));
    for (const link of links) {
      const enter = () => move(link);
      link.addEventListener('pointerenter', enter);
      link.addEventListener('focus', enter);
      cleanups.push(() => { link.removeEventListener('pointerenter', enter); link.removeEventListener('focus', enter); });
    }
    nav.addEventListener('pointerleave', restore);
    nav.addEventListener('focusout', restore);
    const resize = new ResizeObserver(restore);
    resize.observe(nav);
    restore();
    cleanups.push(() => { navigationAnimation?.stop(); nav.removeEventListener('pointerleave', restore); nav.removeEventListener('focusout', restore); resize.disconnect(); indicator.remove(); nav.classList.remove('has-motion'); });
  }

  // Icon motion provides feedback while the button's click target stays still.
  document.querySelectorAll<HTMLElement>('.button, .text-link, .share-button, .back-top, .header-login').forEach(button => {
    const icon = button.querySelector<SVGElement>('.icon');
    if (!icon) return;
    let movement: ReturnType<typeof animate> | undefined;
    const enter = () => { if (reduced.matches) return; movement?.stop(); movement = animate(icon, { x: 3, y: -2, rotate: 5 }, { type: 'spring', stiffness: 330, damping: 16 }); };
    const leave = () => { movement?.stop(); if (reduced.matches) { icon.style.transform = ''; return; } movement = animate(icon, { x: 0, y: 0, rotate: 0 }, { type: 'spring', stiffness: 220, damping: 16 }); };
    button.addEventListener('pointerenter', enter); button.addEventListener('pointerleave', leave);
    button.addEventListener('focus', enter); button.addEventListener('blur', leave);
    cleanups.push(() => { movement?.stop(); button.removeEventListener('pointerenter', enter); button.removeEventListener('pointerleave', leave); button.removeEventListener('focus', enter); button.removeEventListener('blur', leave); icon.style.transform = ''; });
  });

  // Local light follows the cursor on event imagery. There is no global cursor hijack.
  document.querySelectorAll<HTMLElement>('.experience-card').forEach(card => {
    let frame = 0;
    const move = (event: PointerEvent) => {
      if (reduced.matches || !finePointer.matches) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const box = card.getBoundingClientRect();
        card.style.setProperty('--pointer-x', `${event.clientX - box.left}px`);
        card.style.setProperty('--pointer-y', `${event.clientY - box.top}px`);
      });
    };
    card.addEventListener('pointermove', move, { passive: true });
    cleanups.push(() => { cancelAnimationFrame(frame); card.removeEventListener('pointermove', move); });
  });

  // The footer gets its own reveal, with a subtle letter cascade and orbiting arrow.
  const footer = document.querySelector<HTMLElement>('[data-footer]');
  if (footer) {
    cleanups.push(inView(footer, () => {
      if (reduced.matches) return;
      const title = footer.querySelector<HTMLElement>('.footer-next');
      if (title) play(title, { y: [24, 0], opacity: [0.45, 1] }, { duration: .75, ease: [0.22, 1, 0.36, 1] });
    }, { amount: .12 }));
    const monogram = footer.querySelector<HTMLElement>('.footer-monogram');
    if (monogram) cleanups.push(inView(monogram, () => {
      play(monogram.querySelectorAll('span'), { y: [40, 0], opacity: [.15, 1], rotateX: [18, 0] }, { duration: .9, delay: stagger(.12), ease: [0.22, 1, 0.36, 1] });
    }, { amount: .2 }));
  }

  const hero = document.querySelector<HTMLElement>('.hero-stage');
  const photo = document.querySelector<HTMLElement>('.hero-photo');
  if (hero && photo && finePointer.matches) {
    const parallax = animate(photo, { y: [0, 60] }, { ease: 'linear' });
    cleanups.push(scroll(parallax, { target: hero, offset: ['start start', 'end start'] }));
    cleanups.push(() => { parallax.stop(); photo.style.transform = ''; });
  }

  const mark = document.querySelector<HTMLElement>('.site-header .wordmark img');
  const markLink = mark?.parentElement;
  if (mark && markLink) {
    let spin: ReturnType<typeof animate> | undefined;
    const rotate = () => { if (reduced.matches) return; spin?.stop(); spin = animate(mark, { rotateY: [0, 180, 360] }, { duration: .65, ease: [0.22, 1, 0.36, 1] }); };
    markLink.addEventListener('pointerenter', rotate);
    cleanups.push(() => { spin?.stop(); markLink.removeEventListener('pointerenter', rotate); mark.style.transform = ''; });
  }

  function teardown() { controls.forEach(control => control.stop()); cleanups.splice(0).forEach(clean => clean()); }
  const motionChanged = () => { if (reduced.matches) teardown(); };
  reduced.addEventListener('change', motionChanged);
  window.addEventListener('pagehide', event => { if (!event.persisted) { teardown(); reduced.removeEventListener('change', motionChanged); } }, { once: true });
}
