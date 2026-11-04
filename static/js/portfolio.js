// Portfolio: totals, holdings table, allocation doughnuts, add/edit position modal.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

let _portfolio = null;
let _allocCharts = [];

async function loadPortfolio() {
    try {
        _portfolio = await api('/api/portfolio');
        renderPortfolio();
    } catch (e) {
        document.getElementById('portfolioTable').innerHTML =
            `<div style="font-size:0.7rem; color:#ff6b6b; padding:12px 0;">${esc(t("Couldn't load the portfolio: {msg}", { msg: e.message }))}</div>`;
    }
}

function plColor(v) {
    return v == null ? '#888' : v >= 0 ? '#4caf50' : '#f44336';
}

function fmtSigned(v, fmt) {
    return v == null ? '—' : (v > 0 ? '+' : '') + fmt(v);
}

function fmtPctSigned(v) {
    return fmtSigned(v, x => fmtN(x, 2) + '%');
}

function renderPortfolio() {
    const p = _portfolio;
    const summary = document.getElementById('portfolioSummary');
    const table = document.getElementById('portfolioTable');
    const charts = document.getElementById('portfolioCharts');
    const flags = document.getElementById('portfolioFlags');
    _allocCharts.forEach(c => c.destroy());
    _allocCharts = [];

    if (!p.positions.length) {
        summary.innerHTML = '';
        charts.style.display = 'none';
        flags.innerHTML = '';
        table.innerHTML = `<div style="background:#1a1a1a; border:1px dashed #333; padding:18px; font-size:0.75rem; color:#888; line-height:1.6; text-align:center;">
            No positions yet. Add the stocks you own to see their value, profit/loss,<br>allocation and expected dividends in one place.</div>`;
        return;
    }

    // One row of cards per currency (no FX conversion; see watchstock/portfolio.py).
    summary.innerHTML = Object.entries(p.totals).map(([cur, tot]) => `
        <div class="pf-cards">
            <div class="pf-card"><div class="k">${Object.keys(p.totals).length > 1 ? esc(t('Value · {cur}', { cur })) : t('Value')}</div>
                <div class="v">${fmtMoney(tot.value, cur)}</div>
                <div class="s" style="color:#666;">${t(tot.positions === 1 ? '{n} position' : '{n} positions', { n: tot.positions })}</div></div>
            <div class="pf-card"><div class="k">Profit / loss</div>
                <div class="v" style="color:${plColor(tot.pl)};">${fmtSigned(tot.pl, v => fmtMoney(v, cur))}</div>
                <div class="s" style="color:${plColor(tot.pl)};">${fmtPctSigned(tot.pl_pct)}</div></div>
            <div class="pf-card"><div class="k">Today</div>
                <div class="v" style="color:${plColor(tot.day_change)};">${fmtSigned(tot.day_change, v => fmtMoney(v, cur))}</div>
                <div class="s" style="color:${plColor(tot.day_change)};">${fmtPctSigned(tot.day_change_pct)}</div></div>
            <div class="pf-card"><div class="k">Dividends / year</div>
                <div class="v">${fmtMoney(tot.annual_dividends, cur)}</div>
                <div class="s" style="color:#666;">expected, at current rates</div></div>
        </div>`).join('');

    const rows = p.positions.map(pos => `
        <tr>
            <td class="pf-stock" onclick="quickSearch(${esc(JSON.stringify(pos.name))}, ${esc(JSON.stringify(pos.ticker))})" title="${esc(t('Open {name}', { name: pos.name }))}">
                <b>${esc(pos.ticker)}</b><span>${esc(pos.name.length > 18 ? pos.name.slice(0, 17) + '…' : pos.name)}</span></td>
            <td>${pos.shares.toLocaleString(LOCALE, { maximumFractionDigits: 4 })}</td>
            <td>${fmtMoney(pos.avg_cost, pos.currency)}</td>
            <td>${fmtMoney(pos.price, pos.currency)}</td>
            <td style="color:${plColor(pos.change_pct)};">${fmtPctSigned(pos.change_pct)}</td>
            <td>${fmtMoney(pos.value, pos.currency)}</td>
            <td style="color:${plColor(pos.pl)};">${fmtSigned(pos.pl, v => fmtMoney(v, pos.currency))}<br><span style="font-size:0.62rem;">${fmtPctSigned(pos.pl_pct)}</span></td>
            <td>${pos.weight != null ? fmtN(pos.weight, 1) + '%' : '—'}</td>
            <td>${thesisBadge(pos)}</td>
            <td><button class="pf-edit" onclick="openHoldingModal(${esc(JSON.stringify(pos.ticker))})" title="Edit or remove">EDIT</button></td>
        </tr>`).join('');
    table.innerHTML = `<table class="pf-table">
        <thead><tr><th>Stock</th><th>Shares</th><th>Avg cost</th><th>Price</th><th>Today</th><th>Value</th><th>P/L</th><th>Weight</th><th title="Does your reason for owning it still hold?">Thesis</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table>`;

    // Allocation charts for the biggest currency group (by number of positions).
    const [mainCur] = Object.entries(p.totals).sort((a, b) => b[1].positions - a[1].positions)[0];
    const alloc = p.allocation[mainCur];
    if (alloc && alloc.positions.length >= 2) {
        charts.style.display = 'grid';
        document.getElementById('allocPositionsTitle').textContent =
            Object.keys(p.totals).length > 1 ? t('BY POSITION ({cur})', { cur: mainCur }) : t('BY POSITION');
        _allocCharts.push(doughnut('allocPositions', alloc.positions));
        _allocCharts.push(doughnut('allocSectors', alloc.sectors));
    } else {
        charts.style.display = 'none';
    }

    flags.innerHTML = p.flags.map(f =>
        `<div style="font-size:0.68rem; color:#ff9800; background:#1a1a1a; border:1px solid #333; padding:7px 10px; margin-top:8px;">⚠ ${esc(f)}</div>`
    ).join('');
}

function doughnut(canvasId, items) {
    const colors = items.map((_, i) => TERMINAL_COLORS[i % TERMINAL_COLORS.length]);
    return new Chart(document.getElementById(canvasId), {
        type: 'doughnut',
        data: {
            labels: items.map(i => i.label),
            datasets: [{ data: items.map(i => i.weight), backgroundColor: colors, borderColor: '#1a1a1a', borderWidth: 2 }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '60%',
            plugins: {
                legend: { position: 'right', labels: { color: '#bbb', boxWidth: 10, font: { size: 11 } } },
                tooltip: { callbacks: { label: ctx => `${ctx.label}: ${fmtN(ctx.parsed, 1)}%` } },
            },
        },
    });
}

// ---- Add / edit position modal ----

function parseNumber(text) {
    const n = Number(String(text).trim().replace(/\s/g, '').replace(',', '.'));  // accept "182,50"
    return Number.isFinite(n) ? n : NaN;
}

function openHoldingModal(ticker) {
    const existing = ticker ? _portfolio?.positions.find(p => p.ticker === ticker) : null;
    const tickerEl = document.getElementById('holdingTicker');
    document.getElementById('holdingModalTitle').textContent = existing ? t('Edit {ticker}', { ticker: existing.ticker }) : t('Add position');
    tickerEl.value = existing ? existing.ticker : (ticker || '');
    tickerEl.readOnly = !!existing;
    document.getElementById('holdingShares').value = existing ? existing.shares : '';
    document.getElementById('holdingCost').value = existing ? existing.avg_cost : '';
    document.getElementById('holdingNotes').value = existing ? existing.notes : '';
    document.getElementById('holdingError').style.display = 'none';
    const del = document.getElementById('btnDeleteHolding');
    del.style.display = existing ? 'inline-block' : 'none';
    del.textContent = 'REMOVE';
    del.dataset.armed = '';
    document.getElementById('holdingModal').style.display = 'flex';
    (existing ? document.getElementById('holdingShares') : tickerEl).focus();
}

function closeHoldingModal() {
    document.getElementById('holdingModal').style.display = 'none';
    document.getElementById('holdingDropdown').style.display = 'none';
}

function holdingError(msg) {
    const el = document.getElementById('holdingError');
    el.textContent = msg;
    el.style.display = 'block';
}

async function saveHolding() {
    const ticker = document.getElementById('holdingTicker').value.trim().toUpperCase();
    const shares = parseNumber(document.getElementById('holdingShares').value);
    const avgCost = parseNumber(document.getElementById('holdingCost').value);
    const notes = document.getElementById('holdingNotes').value;
    if (!ticker) return holdingError('Pick a stock first.');
    if (!(shares > 0)) return holdingError('Shares must be a number above 0.');
    if (!(avgCost >= 0)) return holdingError('Average cost must be a number (0 or more).');

    const btn = document.getElementById('btnSaveHolding');
    btn.disabled = true;
    btn.textContent = 'CHECKING...';
    try {
        const res = await api('/api/portfolio', { method: 'PUT', body: { ticker, shares, avg_cost: avgCost, notes } });
        closeHoldingModal();
        showToast(t('Saved {ticker} ({name}).', { ticker: res.ticker, name: res.company_name }));
        await loadPortfolio();
        loadToday();
    } catch (e) {
        holdingError(e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'SAVE';
    }
}

// Two clicks to remove instead of a browser confirm() dialog.
async function deleteHolding() {
    const btn = document.getElementById('btnDeleteHolding');
    const ticker = document.getElementById('holdingTicker').value.trim().toUpperCase();
    if (!btn.dataset.armed) {
        btn.dataset.armed = '1';
        btn.textContent = 'CLICK AGAIN TO REMOVE';
        return;
    }
    try {
        await api(`/api/portfolio/${encodeURIComponent(ticker)}`, { method: 'DELETE' });
        closeHoldingModal();
        showToast(t('Removed {ticker} from the portfolio.', { ticker }));
        await loadPortfolio();
        loadToday();
    } catch (e) {
        holdingError(e.message);
    }
}

// ---- Thesis check ("does my reason for owning it still hold?") ----

const THESIS_STYLE = {
    intact:    { color: '#4caf50', label: 'INTACT' },
    weakening: { color: '#ffb900', label: 'WEAKENING' },
    broken:    { color: '#f44336', label: 'BROKEN' },
    unclear:   { color: '#888',    label: 'UNCLEAR' },
};

function thesisBadge(pos) {
    const tj = JSON.stringify(pos.ticker);
    if (!pos.notes) {
        return `<button class="pf-edit" onclick="openHoldingModal(${esc(tj)})" title="Add a 'why I own it' note to enable thesis checks">ADD WHY</button>`;
    }
    const c = pos.thesis_check;
    if (!c) return `<button class="pf-edit" onclick="showThesis(${esc(tj)}, true)" title="Ask the AI whether your reason still holds">CHECK</button>`;
    const st = THESIS_STYLE[c.status] || THESIS_STYLE.unclear;
    return `<button class="pf-edit" onclick="showThesis(${esc(tj)}, false)" title="${esc(t('Checked {when}', { when: timeAgo(c.created_at) }))}"
        style="color:${st.color}; border-color:${st.color}66;">${st.label}</button>`;
}

function openInfoModal(title, html) {
    document.getElementById('scoreModalTitle').innerText = title;
    document.getElementById('scoreModalBody').innerHTML = html;
    document.getElementById('scoreModal').style.display = 'flex';
}

async function showThesis(ticker, runNew) {
    openInfoModal(t('{ticker} — thesis check', { ticker }), '<div style="font-size:0.75rem; color:#888;"><span class="spinner" style="display:inline-block; width:12px; height:12px; border-width:2px; vertical-align:middle; margin-right:8px;"></span>' +
        (runNew ? 'Asking the AI whether your reason still holds...' : 'Loading...') + '</div>');
    try {
        let result = runNew ? null : await api(`/api/portfolio/${encodeURIComponent(ticker)}/thesis`);
        if (!result) result = await api(`/api/portfolio/${encodeURIComponent(ticker)}/thesis`, { method: 'POST' });
        renderThesis(ticker, result);
        loadPortfolio();
    } catch (e) {
        openInfoModal(t('{ticker} — thesis check', { ticker }), `<div style="font-size:0.75rem; color:#ff6b6b;">${esc(e.message)}</div>`);
    }
}

function renderThesis(ticker, r) {
    const st = THESIS_STYLE[r.status] || THESIS_STYLE.unclear;
    const list = (title, items, color) => items?.length ? `
        <div style="margin-top:12px;"><div style="font-size:0.6rem; letter-spacing:1.5px; color:${color}; margin-bottom:4px;">${title}</div>
        <ul style="margin:0 0 0 16px; padding:0; list-style:disc;">${items.map(i => `<li style="font-size:0.72rem; color:#ccc; margin:3px 0; line-height:1.45;">${esc(i)}</li>`).join('')}</ul></div>` : '';
    openInfoModal(t('{ticker} — thesis check', { ticker }), `
        <div style="display:inline-block; font-size:0.75rem; font-weight:800; letter-spacing:1px; color:${st.color}; border:1px solid ${st.color}; padding:3px 10px;">${st.label}</div>
        <p style="font-size:0.8rem; color:#e0e0e0; line-height:1.55; margin:12px 0 0;">${esc(r.summary)}</p>
        ${list('SUPPORTS IT', r.supporting, '#4caf50')}
        ${list('AGAINST IT', r.against, '#f44336')}
        ${list('KEEP AN EYE ON', r.watch, '#ffb900')}
        <div style="margin-top:14px; padding:8px 10px; background:#151515; border-left:2px solid #444; font-size:0.68rem; color:#999; line-height:1.5;">
            <span style="color:#666;">Your thesis:</span> ${esc(r.thesis)}</div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:14px;">
            <span style="font-size:0.6rem; color:#555;">${esc(r.model || '')} · ${r.created_at ? esc(fmtDateTime(r.created_at)) : ''} · ${t('AI opinion, not advice')}</span>
            <button class="pf-edit" onclick="showThesis(${esc(JSON.stringify(ticker))}, true)">CHECK AGAIN</button>
        </div>`);
}

// "You own ..." line in the stock sidebar.
function renderHoldingLine(data) {
    const el = document.getElementById('sbHolding');
    const h = data.holding;
    const price = data.financial_data?.metrics?.currentPrice;
    if (!el) return;
    if (!h) { el.style.display = 'none'; return; }
    const cur = h.currency || priceCurrency();
    const pl = price != null ? (price - h.avg_cost) * h.shares : null;
    const plPct = price != null && h.avg_cost > 0 ? (price / h.avg_cost - 1) * 100 : null;
    el.innerHTML = `<span style="color:#888;">You own</span> <b style="color:#e0e0e0;">${h.shares.toLocaleString(LOCALE, { maximumFractionDigits: 4 })}</b>
        <span style="color:#888;">@ ${fmtMoney(h.avg_cost, cur)}</span><br>
        <span style="color:${plColor(pl)}; font-family:monospace;">${fmtSigned(pl, v => fmtMoney(v, cur))} (${fmtPctSigned(plPct)})</span>`;
    el.style.display = 'block';
}

function initPortfolio() {
    // Same autocomplete as the main search; picking a result fills in the ticker.
    const input = document.getElementById('holdingTicker');
    initAutocomplete(input, document.getElementById('holdingDropdown'), input, input);
    document.getElementById('holdingModal').addEventListener('click', function (e) {
        if (e.target === this) closeHoldingModal();
    });
    ['holdingShares', 'holdingCost'].forEach(id =>
        document.getElementById(id).addEventListener('keydown', e => { if (e.key === 'Enter') saveHolding(); }));
    loadPortfolio();
}
