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
  document.querySelectorAll('input[name="theme"]').forEach(input => {
    input.addEventListener('change', () => {
      if (!poster || !input.checked) return;
      Array.from(poster.classList).filter(name => name.startsWith('theme-')).forEach(name => poster.classList.remove(name));
      poster.classList.add('theme-' + input.value);
    });
  });
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
