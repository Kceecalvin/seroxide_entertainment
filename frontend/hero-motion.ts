import { animate } from 'framer-motion/dom';

export function enhanceHero(root: HTMLElement) {
  const ticket = root.querySelector<HTMLElement>('[data-tilt]');
  const stage = root.querySelector<HTMLElement>('[data-ticket-stage]');
  const heading = document.querySelector<HTMLElement>('[data-hero-title]');
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!ticket || !stage || media.matches) return;
  if (heading) animate(heading, { opacity: [0.5, 1], y: [16, 0] }, { duration: 0.65, ease: [0.22, 1, 0.36, 1] });
  const baseRotation = innerWidth <= 800 ? 6 : 7;
  let currentAnimation: ReturnType<typeof animate> | undefined;
  let frame = 0;
  const reset = () => {
    currentAnimation?.stop();
    currentAnimation = animate(ticket, { rotateX: 0, rotateY: 0, rotateZ: baseRotation, y: 0 }, { type: 'spring', stiffness: 110, damping: 20 });
  };
  const move = (event: PointerEvent) => {
    if (media.matches || event.pointerType !== 'mouse') return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const bounds = stage.getBoundingClientRect();
      const x = (event.clientX - bounds.left) / bounds.width - 0.5;
      const y = (event.clientY - bounds.top) / bounds.height - 0.5;
      currentAnimation?.stop();
      currentAnimation = animate(ticket, { rotateX: -y * 14, rotateY: x * 18, rotateZ: baseRotation + x * 3, y: -6 }, { type: 'spring', stiffness: 100, damping: 20 });
    });
  };
  stage.addEventListener('pointermove', move, { passive: true });
  stage.addEventListener('pointerleave', reset);
  const stop = () => {
    if (!media.matches) return;
    cancelAnimationFrame(frame);
    currentAnimation?.stop();
    ticket.style.transform = '';
  };
  media.addEventListener('change', stop);
  window.addEventListener('pagehide', () => {
    cancelAnimationFrame(frame);
    currentAnimation?.stop();
    stage.removeEventListener('pointermove', move);
    stage.removeEventListener('pointerleave', reset);
    media.removeEventListener('change', stop);
  }, { once: true });
}
