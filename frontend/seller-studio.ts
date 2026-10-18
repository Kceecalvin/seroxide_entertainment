export function setupSellerStudio() {
  const form = document.querySelector<HTMLFormElement>('[data-event-editor]');
  if (!form) return;
  const title = document.querySelector<HTMLElement>('[data-poster-title]');
  const venue = document.querySelector<HTMLElement>('[data-poster-venue]');
  const image = document.querySelector<HTMLImageElement>('[data-poster-image]');
  let previewUrl = '';
  for (const [name, target, fallback] of [['title', title, 'Your event. Their next memory.'], ['venue', venue, 'Somewhere unforgettable']] as const) {
    form.querySelector<HTMLInputElement>(`[name="${name}"]`)?.addEventListener('input', event => {
      if (target) target.textContent = (event.target as HTMLInputElement).value || fallback;
    });
  }
  form.querySelector<HTMLInputElement>('[name="cover_image"]')?.addEventListener('change', event => {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!image || !file || !file.type.startsWith('image/') || file.size > 5 * 1024 * 1024) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    image.src = previewUrl;
    image.hidden = false;
  });
  window.addEventListener('pagehide', () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, {once: true});
}
