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
            `<div style="font-size:0.7rem; color:#ff6b6b; padding:12px 0;">Couldn't load the portfolio: ${esc(e.message)}</div>`;
    }
}

function plColor(v) {
    return v == null ? '#888' : v >= 0 ? '#4caf50' : '#f44336';
}

function fmtSigned(v, fmt) {
    return v == null ? '—' : (v > 0 ? '+' : '') + fmt(v);
}

function fmtPctSigned(v) {
    return fmtSigned(v, x => x.toFixed(2) + '%');
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
    summary.innerHTML = Object.entries(p.totals).map(([cur, t]) => `
        <div class="pf-cards">
            <div class="pf-card"><div class="k">Value${Object.keys(p.totals).length > 1 ? ' · ' + esc(cur) : ''}</div>
                <div class="v">${fmtMoney(t.value, cur)}</div>
                <div class="s" style="color:#666;">${t.positions} position${t.positions === 1 ? '' : 's'}</div></div>
            <div class="pf-card"><div class="k">Profit / loss</div>
                <div class="v" style="color:${plColor(t.pl)};">${fmtSigned(t.pl, v => fmtMoney(v, cur))}</div>
                <div class="s" style="color:${plColor(t.pl)};">${fmtPctSigned(t.pl_pct)}</div></div>
            <div class="pf-card"><div class="k">Today</div>
                <div class="v" style="color:${plColor(t.day_change)};">${fmtSigned(t.day_change, v => fmtMoney(v, cur))}</div>
                <div class="s" style="color:${plColor(t.day_change)};">${fmtPctSigned(t.day_change_pct)}</div></div>
            <div class="pf-card"><div class="k">Dividends / year</div>
                <div class="v">${fmtMoney(t.annual_dividends, cur)}</div>
                <div class="s" style="color:#666;">expected, at current rates</div></div>
        </div>`).join('');

    const rows = p.positions.map(pos => `
        <tr>
            <td class="pf-stock" onclick="quickSearch(${esc(JSON.stringify(pos.name))}, ${esc(JSON.stringify(pos.ticker))})" title="Open ${esc(pos.name)}">
                <b>${esc(pos.ticker)}</b><span>${esc(pos.name.slice(0, 24))}</span></td>
            <td>${pos.shares.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
            <td>${fmtMoney(pos.avg_cost, pos.currency)}</td>
            <td>${fmtMoney(pos.price, pos.currency)}</td>
            <td style="color:${plColor(pos.change_pct)};">${fmtPctSigned(pos.change_pct)}</td>
            <td>${fmtMoney(pos.value, pos.currency)}</td>
            <td style="color:${plColor(pos.pl)};">${fmtSigned(pos.pl, v => fmtMoney(v, pos.currency))}<br><span style="font-size:0.62rem;">${fmtPctSigned(pos.pl_pct)}</span></td>
            <td>${pos.weight != null ? pos.weight.toFixed(1) + '%' : '—'}</td>
            <td><button class="pf-edit" onclick="openHoldingModal(${esc(JSON.stringify(pos.ticker))})" title="Edit or remove">EDIT</button></td>
        </tr>`).join('');
    table.innerHTML = `<table class="pf-table">
        <thead><tr><th>Stock</th><th>Shares</th><th>Avg cost</th><th>Price</th><th>Today</th><th>Value</th><th>P/L</th><th>Weight</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table>`;

    // Allocation charts for the biggest currency group (by number of positions).
    const [mainCur] = Object.entries(p.totals).sort((a, b) => b[1].positions - a[1].positions)[0];
    const alloc = p.allocation[mainCur];
    if (alloc && alloc.positions.length >= 2) {
        charts.style.display = 'grid';
        document.getElementById('allocPositionsTitle').textContent =
            'BY POSITION' + (Object.keys(p.totals).length > 1 ? ` (${mainCur})` : '');
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
                tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed.toFixed(1)}%` } },
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
    document.getElementById('holdingModalTitle').textContent = existing ? `Edit ${existing.ticker}` : 'Add position';
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
        showToast(`Saved ${res.ticker} (${res.company_name}).`);
        await loadPortfolio();
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
        showToast(`Removed ${ticker} from the portfolio.`);
        await loadPortfolio();
    } catch (e) {
        holdingError(e.message);
    }
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
    el.innerHTML = `<span style="color:#888;">You own</span> <b style="color:#e0e0e0;">${h.shares.toLocaleString('en-US', { maximumFractionDigits: 4 })}</b>
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
