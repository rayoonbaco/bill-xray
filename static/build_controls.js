(() => {
  const buttons = [...document.querySelectorAll('[data-build-bill]')];
  if (!buttons.length) return;

  const STAGES = [
    ['ingest','Read the official bill','Acquire and normalize the exact government text.'],
    ['segment','Map the bill’s structure','Identify titles, subtitles, chapters, sections, and operative blocks.'],
    ['anchors','Lock exact citations','Create stable source anchors before interpretation begins.'],
    ['translate','Translate dense legal language','Convert statutory mechanics into bounded plain English.'],
    ['money','Trace money, taxes, grants, and revenue','Find operative fiscal mechanics and classify materiality.'],
    ['power','Map power, duties, and authority','Identify who gains duties, discretion, enforcement, or limits.'],
    ['barrel','Scan for exceptions, carve-outs, and surprises','Surface provisions that deserve closer public explanation.'],
    ['topics','Route provisions to subject-matter experts','Apply topic-aware review to the locked evidence.'],
    ['left','Build strongest progressive interpretation','Argue the strongest good-faith progressive reading of the same consequence.'],
    ['right','Build strongest conservative interpretation','Argue the strongest good-faith conservative reading of the same consequence.'],
    ['advocacy','Bind Left / Right / Text to the same evidence','Prevent competing lenses from talking past each other.'],
    ['skeptic','Run the Investigative Skeptic','Attack weak implications, missing context, and overstatement.'],
    ['referee','Run the Neutral Referee','Decide what survives adversarial review.'],
    ['synthesis','Build the public X-Ray','Compress the surviving evidence into the human-readable report.'],
    ['external','Pull official external evidence','Check CBO, JCT, and USAspending in separate provenance lanes.'],
    ['consequence','Build consequence context','Compare statutory mechanics with official estimates and related implementation activity without blending the sources.'],
    ['red_team','Run political-bias + selection red team','Challenge materiality, balance, and public-facing selection quality.'],
    ['audit','Reverify every citation','Check that every published factual claim resolves to its source anchor.'],
    ['challenge','Run hostile context challenge','Ask whether a technically correct excerpt could still mislead without surrounding law.']
  ];

  const session = document.querySelector('[data-build-session]');
  const q = (sel) => session ? session.querySelector(sel) : null;
  const fmt = (seconds) => {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, '0')}`;
  };
  const billName = (button) => button.dataset.buildName || button.closest('.bill-card')?.querySelector('h3, strong')?.textContent?.trim() || document.querySelector('.bill-head h1')?.textContent?.trim() || 'Bill';

  const setButton = (button, state, message) => {
    button.dataset.buildState = state || '';
    const label = button.querySelector('[data-build-label]') || button;
    if (state === 'verified') label.textContent = 'Open analysis';
    else if (['queued','fetching','running'].includes(state)) label.textContent = 'Building…';
    else if (state === 'hold') label.textContent = button.classList.contains('inline-build-button') ? 'Run analysis again' : 'Review hold';
    else if (state === 'error') label.textContent = 'Retry build';
    else label.textContent = 'Build full X-Ray';
    button.title = message || '';
    button.disabled = ['queued','fetching','running'].includes(state);
  };

  const lockOtherBuilds = (activeButton, locked) => {
    buttons.forEach((button) => {
      if (button === activeButton) return;
      if (locked && button.dataset.buildState !== 'verified') {
        button.disabled = true; button.dataset.sessionLocked = 'true';
        button.title = 'Finish the current analysis before starting another build.';
      } else if (!locked && button.dataset.sessionLocked === 'true') {
        button.disabled = false; delete button.dataset.sessionLocked;
      }
    });
  };

  const renderStageBoard = (p) => {
    const list = q('[data-progress-all-stages]');
    if (!list) return;
    const done = new Map((p.completed || []).map(item => [item.key, item]));
    const current = p.stage_key;
    list.replaceChildren();
    STAGES.forEach(([key, label, description], index) => {
      const li = document.createElement('li');
      const isDone = done.has(key);
      const isCurrent = key === current;
      li.className = `pipeline-stage ${isDone ? 'done' : isCurrent ? 'active' : 'upcoming'}`;
      const mark = document.createElement('span');
      mark.className = 'stage-mark';
      mark.textContent = isDone ? '✓' : isCurrent ? '→' : String(index + 1).padStart(2, '0');
      const copy = document.createElement('div');
      const strong = document.createElement('strong'); strong.textContent = label;
      const small = document.createElement('span');
      const summary = done.get(key)?.summary;
      small.textContent = isDone && summary ? summary : description;
      copy.append(strong, small); li.append(mark, copy); list.appendChild(li);
    });
  };

  const updateSession = (data, button) => {
    if (!session) return;
    const active = ['queued','fetching','running'].includes(data.state);
    session.hidden = !active;
    document.body.classList.toggle('build-active', active);
    if (!active) { lockOtherBuilds(button, false); return; }
    lockOtherBuilds(button, true);
    const p = data.progress || {};
    const percent = Math.max(1, Math.min(99, Number(p.percent) || (data.state === 'fetching' ? 2 : 1)));
    q('[data-progress-title]').textContent = `Building ${billName(button)}`;
    q('[data-progress-percent]').textContent = `${percent}%`;
    q('[data-progress-bar]').style.width = `${percent}%`;
    q('[data-progress-stage]').textContent = p.stage_label || (data.state === 'fetching' ? 'Securing the official government source' : 'Starting the evidence pipeline');
    q('[data-progress-step]').textContent = p.stage_index ? `${p.stage_index} of ${p.total_stages || 19}` : 'Preparing';
    q('[data-progress-description]').textContent = p.stage_description || data.message || 'Bill X-Ray is working through the evidence pipeline.';
    q('[data-progress-elapsed]').textContent = `Elapsed: ${fmt(p.elapsed_seconds)}`;
    q('[data-progress-eta]').textContent = p.eta_label || 'Estimating remaining time…';
    renderStageBoard(p);
  };

  const poll = async (billId, button) => {
    try {
      const response = await fetch(`/api/build-status/${encodeURIComponent(billId)}`, {cache:'no-store'});
      const data = await response.json();
      setButton(button, data.state, data.message); updateSession(data, button);
      const status = document.querySelector(`[data-build-status="${CSS.escape(billId)}"]`);
      if (status) status.textContent = data.message || '';
      if (data.state === 'verified') {
        if (session) {
          session.hidden = false;
          q('[data-progress-percent]').textContent = '100%'; q('[data-progress-bar]').style.width = '100%';
          q('[data-progress-stage]').textContent = 'Verified report ready'; q('[data-progress-step]').textContent = '19 of 19';
          q('[data-progress-description]').textContent = 'The referee, red team, citation audit, and hostile context challenge cleared the report. Opening it now…';
          q('[data-progress-eta]').textContent = 'Complete';
          const p = data.progress || {}; p.completed = STAGES.map(([key,label]) => ({key,label})); p.stage_key = null; renderStageBoard(p);
        }
        document.body.classList.remove('build-active');
        window.setTimeout(() => window.location.assign(`/bill/${encodeURIComponent(billId)}`), 650); return;
      }
      if (['queued','fetching','running'].includes(data.state)) window.setTimeout(() => poll(billId, button), 1200);
      else lockOtherBuilds(button, false);
    } catch (err) {
      setButton(button, 'error', 'Could not read build status.'); document.body.classList.remove('build-active'); lockOtherBuilds(button, false);
    }
  };

  buttons.forEach((button) => {
    const billId = button.dataset.buildBill;
    button.addEventListener('click', async (event) => {
      event.preventDefault();
      if (button.dataset.buildState === 'verified') { window.location.assign(`/bill/${encodeURIComponent(billId)}`); return; }
      if (button.dataset.buildState === 'hold' && !button.classList.contains('inline-build-button')) { window.location.assign(`/bill/${encodeURIComponent(billId)}`); return; }
      setButton(button, 'queued', 'Starting build…'); updateSession({state:'queued', message:'Starting build…'}, button);
      try {
        const response = await fetch(`/api/build/${encodeURIComponent(billId)}`, {method:'POST'}); const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Build could not start');
        setButton(button, data.state, data.message); updateSession(data, button); poll(billId, button);
      } catch (err) { setButton(button, 'error', err.message || 'Build could not start'); lockOtherBuilds(button, false); }
    });
    if (['queued','fetching','running'].includes(button.dataset.buildState)) poll(billId, button);
  });
})();
