(() => {
  const root = document.querySelector('[data-bill-search]');
  if (!root) return;
  const input = root.querySelector('[data-bill-search-input]');
  const results = root.querySelector('[data-search-results]');
  const spinner = root.querySelector('[data-search-spinner]');
  const hint = root.querySelector('[data-search-hint]');
  let timer = null;
  let controller = null;
  let token = '';

  const hide = () => { results.hidden = true; results.replaceChildren(); };
  const message = (text, cls='search-empty') => {
    results.replaceChildren(); const div = document.createElement('div'); div.className = cls; div.textContent = text; results.appendChild(div); results.hidden = false;
  };
  const select = async (item) => {
    hint.textContent = `Confirming ${item.bill_number} · ${item.version_label}…`;
    try {
      const r = await fetch('/api/search-select', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({search_token:token, package_id:item.package_id})});
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || 'Could not select this bill version');
      window.location.assign(`/bill/${encodeURIComponent(data.bill.id)}`);
    } catch (err) {
      message(err.message || 'Could not select this bill version', 'search-error');
    }
  };
  const render = (data) => {
    token = data.search_token || '';
    results.replaceChildren();
    if (!data.results?.length) { message('No official GovInfo bill versions matched. Try a broader keyword or bill number.'); return; }
    data.results.forEach((item) => {
      const row = document.createElement('div'); row.className='search-result';
      const copy = document.createElement('div');
      const strong = document.createElement('strong'); strong.textContent = item.title;
      const small = document.createElement('small'); small.textContent = `${item.bill_number} · ${item.congress}th Congress · ${item.version_label}${item.date_issued ? ' · '+item.date_issued : ''}`;
      copy.append(strong, small);
      const button = document.createElement('button'); button.type='button'; button.textContent='Select version'; button.addEventListener('click', () => select(item));
      row.append(copy, button); results.appendChild(row);
    });
    results.hidden = false;
  };
  const run = async () => {
    const q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    if (controller) controller.abort(); controller = new AbortController();
    spinner.hidden=false; hint.textContent='Searching official GovInfo congressional bill versions…';
    try {
      const r = await fetch(`/api/search-bills?q=${encodeURIComponent(q)}`, {cache:'no-store', signal:controller.signal});
      const data = await r.json(); if (!r.ok) throw new Error(data.detail || 'Search unavailable'); render(data);
      hint.textContent='Pick the exact version you want Bill X-Ray to analyze. Different versions can contain different lawmaking choices.';
    } catch (err) {
      if (err.name !== 'AbortError') { message(err.message || 'Official bill search is temporarily unavailable.', 'search-error'); hint.textContent='Search uses the official U.S. Government Publishing Office source.'; }
    } finally { spinner.hidden=true; }
  };

  document.querySelectorAll('[data-search-query]').forEach((button) => {
    button.addEventListener('click', () => {
      input.value = button.dataset.searchQuery || '';
      input.focus();
      clearTimeout(timer);
      run();
      root.scrollIntoView({behavior:'smooth', block:'center'});
    });
  });

  input.addEventListener('input', () => { clearTimeout(timer); timer=setTimeout(run, 350); });
  input.addEventListener('keydown', (e) => { if (e.key==='Escape') hide(); });
  document.addEventListener('click', (e) => { if (!root.contains(e.target)) hide(); });
})();
