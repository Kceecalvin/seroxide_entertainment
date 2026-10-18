(() => {
  document.querySelectorAll('[data-ticket-presets]').forEach(group => {
    group.hidden = false;
    group.querySelectorAll('[data-ticket-name]').forEach(button => {
      button.addEventListener('click', () => {
        const input = group.closest('form').querySelector('[name="name"]');
        input.value = button.dataset.ticketName;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.focus();
      });
    });
  });
  const poster = document.querySelector('[data-studio-poster]');
  const colours = ['poster_accent', 'poster_secondary'].map(name => document.querySelector(`[name="${name}"]`));
  function updatePosterTheme() {
    const selected = document.querySelector('input[name="theme"]:checked');
    if (!poster || !selected) return;
    Array.from(poster.classList).filter(name => name.startsWith('theme-')).forEach(name => poster.classList.remove(name));
    poster.classList.add('theme-' + selected.value);
    poster.removeAttribute('style');
    if (selected.value === 'poster' && window.SeroTixPosterPalette) {
      const palette = window.SeroTixPosterPalette(colours[0]?.value, colours[1]?.value);
      Object.entries(palette).forEach(([key,value]) => poster.style.setProperty(key,value));
      const swatch = document.querySelector('.studio-theme-option.theme-poster');
      Object.entries(palette).forEach(([key,value]) => swatch?.style.setProperty(key,value));
    }
  }
  document.querySelectorAll('input[name="theme"]').forEach(input => input.addEventListener('change', updatePosterTheme));
  colours.forEach(input => input?.addEventListener('input', updatePosterTheme));
  updatePosterTheme();
  const dirtyForms = new Set();
  document.querySelectorAll('.studio-workspace form[method="post"]').forEach(form => {
    form.addEventListener('input', () => {
      dirtyForms.add(form);
      const status = form.querySelector('[data-save-status]');
      if (status) status.textContent = 'Unsaved changes';
    });
    form.addEventListener('submit', () => { dirtyForms.delete(form); });
  });
  window.addEventListener('beforeunload', event => {
    if (!dirtyForms.size) return;
    event.preventDefault();
    event.returnValue = '';
  });
  const errorSummary = document.querySelector('[data-studio-errors]');
  if (errorSummary) errorSummary.focus();
})();
