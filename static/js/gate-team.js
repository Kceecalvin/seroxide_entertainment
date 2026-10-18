const copyInvite = document.querySelector('[data-copy-invite]');
copyInvite?.addEventListener('click', async () => {
  const field = document.getElementById('invitation-link');
  const status = document.querySelector('[data-copy-status]');
  try {
    await navigator.clipboard.writeText(field.value);
    status.textContent = 'Copied. Share this link privately with the invited guard.';
  } catch {
    field.focus(); field.select();
    status.textContent = 'Link selected. Use your device’s Copy action.';
  }
});
