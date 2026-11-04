// Portfolio import from a broker export (Tradeville) or a simple CSV.
// Flow: pick file -> POST /api/portfolio/import/preview (nothing is saved; tickers are
// checked against Yahoo) -> the user reviews / fixes tickers -> POST .../import/commit.
// Parsing lives in watchstock/importers.py; this file only shows the result.

let _import = null;  // { content, overrides: {fileSymbol: ticker}, preview }

function openImportModal() {
    _import = null;
    document.getElementById('importPick').style.display = 'block';
    document.getElementById('importPreview').style.display = 'none';
    document.getElementById('importPreview').innerHTML = '';
    document.getElementById('importFile').value = '';
    importError('');
    updateImportButton();
    document.getElementById('importModal').style.display = 'flex';
}

function closeImportModal() {
    document.getElementById('importModal').style.display = 'none';
}

function importError(msg) {
    const el = document.getElementById('importError');
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
}

// Tradeville exports are UTF-8; older Romanian Windows files can be Windows-1250.
async function readFileText(file) {
    const buf = await file.arrayBuffer();
    try {
        return new TextDecoder('utf-8', { fatal: true }).decode(buf);
    } catch (e) {
        return new TextDecoder('windows-1250').decode(buf);
    }
}

async function onImportFile(input) {
    const file = input.files[0];
    if (!file) return;
    importError('');
    if (file.size > 2_000_000) return importError(t('That file is too big for a portfolio export.'));
    _import = { content: await readFileText(file), overrides: {}, preview: null };
    await runImportPreview();
}

async function runImportPreview() {
    const box = document.getElementById('importPreview');
    box.style.display = 'block';
    box.innerHTML = `<div style="font-size:0.75rem; color:#888; padding:8px 0;"><span class="spinner" style="display:inline-block; width:12px; height:12px; border-width:2px; vertical-align:middle; margin-right:8px;"></span>${t('Reading the file and checking each stock...')}</div>`;
    importError('');
    try {
        _import.preview = await api('/api/portfolio/import/preview', {
            method: 'POST', body: { content: _import.content, overrides: _import.overrides },
        });
        document.getElementById('importPick').style.display = 'none';
        renderImportPreview();
    } catch (e) {
        box.style.display = 'none';
        _import.preview = null;
        importError(e.message);
    }
    updateImportButton();
}

const IMPORT_STATUS = {
    ok:        { color: '#4caf50', text: () => 'OK' },
    isin:      { color: '#ffb900', text: r => t('Matched by ISIN (file: {ticker})', { ticker: r.original_ticker }) },
    not_found: { color: '#f44336', text: () => 'Not found' },
};

function renderImportPreview() {
    const p = _import.preview;
    const notFound = p.rows.filter(r => r.status === 'not_found').length;
    const rows = p.rows.map((r, i) => {
        const st = IMPORT_STATUS[r.status] || IMPORT_STATUS.not_found;
        const ticker = r.status === 'not_found'
            ? `<input class="hm-input imp-fix" data-src="${esc(r.source_symbol)}" value="${esc(r.ticker)}" style="width:90px; padding:3px 6px; font-size:0.72rem;">`
            : `<b>${esc(r.ticker)}</b>`;
        const held = r.in_portfolio ? `<div style="font-size:0.6rem; color:#666;">${t('already in portfolio')}</div>` : '';
        return `<tr>
            <td><input type="checkbox" class="imp-row" data-i="${i}" ${r.status === 'not_found' ? 'disabled' : 'checked'} onchange="updateImportButton()"></td>
            <td style="color:#888;">${esc(r.source_symbol)}</td>
            <td>${ticker}</td>
            <td class="no-i18n" style="text-align:left; font-family:inherit; color:#aaa; max-width:180px; overflow:hidden; text-overflow:ellipsis;" title="${esc(r.name)}">${esc(r.name)}</td>
            <td>${r.shares.toLocaleString(LOCALE, { maximumFractionDigits: 4 })}</td>
            <td>${fmtMoney(r.avg_cost, r.currency || 'USD')}</td>
            <td style="text-align:left; font-family:inherit; color:${st.color}; white-space:normal;">${esc(st.text(r))}${held}</td>
        </tr>`;
    }).join('');

    const skipped = p.skipped.map(s => s.reason === 'cash'
        ? t('{cur} cash ({amount}) is not imported.', { cur: s.currency || '', amount: fmtN(s.amount, 2) ?? '—' })
        : s.reason === 'no shares or cost'
            ? t('{symbol}: no shares or cost, skipped.', { symbol: s.symbol })
            : t('{symbol}: skipped ({reason}).', { symbol: s.symbol, reason: s.reason }));

    const fixHint = notFound ? `
        <div style="margin-top:10px; padding:8px 10px; background:#151515; border-left:2px solid #f44336; font-size:0.68rem; color:#aaa; line-height:1.5;">
            ${esc(t(notFound === 1 ? '{n} stock was not found on Yahoo Finance.' : '{n} stocks were not found on Yahoo Finance.', { n: notFound }))}
            ${t('Type the Yahoo ticker in the red rows (e.g. BRK-B, TLV.RO), then check again. Rows that stay red are left out.')}
            <div style="margin-top:8px;"><button class="pf-edit" onclick="recheckImport()">CHECK AGAIN</button></div>
        </div>` : '';

    const choice = p.currently_held ? `
        <div style="margin-top:16px;">
            <label class="imp-mode"><input type="radio" name="importMode" value="replace" checked onchange="updateImportButton()">
                <span><b>${t('Replace my portfolio with this file')}</b><br>
                <span class="imp-sub">${t('Best for a full Tradeville export. Your "why I own it" notes are kept for stocks that stay.')}</span></span></label>
            <label class="imp-mode"><input type="radio" name="importMode" value="merge" onchange="updateImportButton()">
                <span><b>${t('Add and update only')}</b><br>
                <span class="imp-sub">${t('Positions that are not in the file stay as they are.')}</span></span></label>
            <div id="importRemoved" style="font-size:0.68rem; color:#ff9800; margin-top:6px;"></div>
        </div>` : '';

    document.getElementById('importPreview').innerHTML = `
        <div style="font-size:0.72rem; color:#ccc; margin-bottom:10px;">
            ${esc(t(p.format === 'tradeville' ? 'Tradeville export: {n} positions found.' : 'CSV file: {n} positions found.', { n: p.rows.length }))}
            <button class="pf-edit" style="margin-left:8px;" onclick="openImportModal()">PICK ANOTHER FILE</button></div>
        <div style="max-height:42vh; overflow:auto; border:1px solid #222;">
            <table class="pf-table imp-table">
                <thead><tr><th></th><th>In the file</th><th>Ticker</th><th style="text-align:left;">Name</th><th>Shares</th><th>Avg cost</th><th style="text-align:left;">Status</th></tr></thead>
                <tbody>${rows}</tbody></table></div>
        ${fixHint}
        ${skipped.length ? `<div style="font-size:0.65rem; color:#666; margin-top:8px; line-height:1.5;">${skipped.map(esc).join('<br>')}</div>` : ''}
        ${choice}`;
}

function selectedImportRows() {
    if (!_import?.preview) return [];
    return [...document.querySelectorAll('.imp-row:checked')].map(cb => _import.preview.rows[Number(cb.dataset.i)]);
}

function importMode() {
    return document.querySelector('input[name="importMode"]:checked')?.value || 'replace';
}

function updateImportButton() {
    const btn = document.getElementById('btnCommitImport');
    const sel = selectedImportRows();
    btn.disabled = !sel.length;
    btn.style.opacity = sel.length ? '1' : '0.4';
    btn.textContent = sel.length ? t(sel.length === 1 ? 'IMPORT {n} POSITION' : 'IMPORT {n} POSITIONS', { n: sel.length }) : t('IMPORT');
    const removedEl = document.getElementById('importRemoved');
    if (removedEl) {
        const kept = sel.filter(r => r.in_portfolio).length;
        const removed = Math.max(0, _import.preview.currently_held - kept);
        removedEl.textContent = importMode() === 'replace' && removed
            ? t(removed === 1 ? '1 position you hold now is not selected and will be removed.' : '{n} positions you hold now are not selected and will be removed.', { n: removed })
            : '';
    }
}

async function recheckImport() {
    document.querySelectorAll('.imp-fix').forEach(inp => {
        const v = inp.value.trim();
        if (v) _import.overrides[inp.dataset.src] = v;
    });
    await runImportPreview();
}

async function commitImport() {
    const sel = selectedImportRows();
    if (!sel.length) return;
    const btn = document.getElementById('btnCommitImport');
    btn.disabled = true;
    btn.textContent = t('SAVING...');
    try {
        const res = await api('/api/portfolio/import/commit', {
            method: 'POST',
            body: { mode: importMode(), rows: sel.map(r => ({ ticker: r.ticker, shares: r.shares, avg_cost: r.avg_cost, currency: r.currency })) },
        });
        closeImportModal();
        showToast(t(res.imported === 1 ? 'Imported {n} position.' : 'Imported {n} positions.', { n: res.imported }), 3500);
        _infoPolls = 0;
        await loadPortfolio();
        loadToday();
    } catch (e) {
        importError(e.message);
        updateImportButton();
    }
}

function initImport() {
    document.getElementById('importModal').addEventListener('click', function (e) {
        if (e.target === this) closeImportModal();
    });
}
