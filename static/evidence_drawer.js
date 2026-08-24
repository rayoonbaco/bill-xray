(() => {
  const drawer = document.getElementById('evidence-drawer');
  const backdrop = document.getElementById('evidence-backdrop');
  if (!drawer || !backdrop) return;

  const primaryCloseButton = drawer.querySelector('[data-evidence-close]');
  const status = document.getElementById('evidence-status-line');
  const section = document.getElementById('evidence-section');
  const location = document.getElementById('evidence-location');
  const anchor = document.getElementById('evidence-anchor');
  const documentRef = document.getElementById('evidence-document');
  const excerpt = document.getElementById('evidence-excerpt');
  const exactText = document.getElementById('evidence-exact-text');
  const sourceLink = document.getElementById('evidence-source-link');
  let returnFocus = null;

  function closeDrawer(event) {
    if (event && typeof event.preventDefault === 'function') event.preventDefault();
    drawer.classList.remove('open');
    backdrop.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('evidence-open');
    const target = returnFocus;
    returnFocus = null;
    if (target && typeof target.focus === 'function') target.focus();
  }

  function openShell(trigger) {
    returnFocus = trigger;
    drawer.classList.add('open');
    backdrop.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    backdrop.setAttribute('aria-hidden', 'false');
    document.body.classList.add('evidence-open');
    status.textContent = 'Verifying source anchor…';
    section.textContent = '';
    location.textContent = '';
    anchor.textContent = '';
    documentRef.textContent = '';
    excerpt.textContent = '';
    exactText.textContent = '';
    sourceLink.hidden = true;
    if (primaryCloseButton) primaryCloseButton.focus();
  }

  async function showEvidence(trigger) {
    const billId = trigger.dataset.billId;
    const anchorId = trigger.dataset.anchorId;
    if (!billId || !anchorId) return;
    openShell(trigger);
    try {
      const response = await fetch(`/api/evidence/${encodeURIComponent(billId)}/${encodeURIComponent(anchorId)}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Evidence could not be verified.');
      status.textContent = payload.verified ? '✓ Source anchor verified' : 'Source verification unavailable';
      section.textContent = payload.section_label || 'Source section';
      location.textContent = payload.location_marker || 'Exact location unavailable';
      anchor.textContent = payload.anchor_id || '';
      documentRef.textContent = payload.document_ref || '';
      excerpt.textContent = payload.excerpt || '';
      exactText.textContent = payload.exact_text || '';
      if (payload.source_url) {
        sourceLink.href = payload.source_url;
        sourceLink.hidden = false;
      }
    } catch (error) {
      status.textContent = 'Evidence verification failed';
      exactText.textContent = error instanceof Error ? error.message : 'Evidence could not be loaded.';
    }
  }

  document.addEventListener('click', (event) => {
    const close = event.target.closest('[data-evidence-close]');
    if (close) {
      closeDrawer(event);
      return;
    }
    const trigger = event.target.closest('[data-evidence-trigger]');
    if (trigger) {
      event.preventDefault();
      showEvidence(trigger);
    }
  });

  backdrop.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && drawer.classList.contains('open')) closeDrawer(event);
  });
})();
