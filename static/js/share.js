document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-copy-url]');
  if (!button) return;

  const url = button.dataset.copyUrl || '';
  if (!url) return;

  try {
    if (!navigator.clipboard || !window.isSecureContext) {
      throw new Error('clipboard unavailable');
    }
    await navigator.clipboard.writeText(url);
    showToast(T.linkCopied || 'Link copied', 'success');
  } catch (error) {
    const input = button.closest('tr')?.querySelector('.share-url-input');
    if (input) {
      input.focus();
      input.select();
    }
    showToast(T.copyManually || 'Copy failed. Please copy the link manually.');
  }
});

document.querySelectorAll('[data-confirm-delete]').forEach((form) => {
  form.addEventListener('submit', (event) => {
    const message = T.confirmDeleteShareLink || 'Delete this share link?';
    if (!window.confirm(message)) {
      event.preventDefault();
    }
  });
});
