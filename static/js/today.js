// "Your stocks" panel: upcoming earnings / ex-dividend dates, big moves, rating changes
// and insider buys for held + watched stocks (computed by /api/today).
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

const TODAY_KINDS = {
    big_move:    { icon: '⚡', color: '#ffb900', label: 'Move' },
    earnings:    { icon: '📅', color: '#5b9bd5', label: 'Earnings' },
    ex_dividend: { icon: '💵', color: '#4caf50', label: 'Dividend' },
    rating:      { icon: '★',  color: '#a78bfa', label: 'Analysts' },
    insider_buy: { icon: '◆',  color: '#00bfff', label: 'Insider' },
};

async function loadToday(manual = false) {
    const list = document.getElementById('todayList');
    if (manual) list.innerHTML = '<div style="font-size:0.68rem; color:#555;">Loading...</div>';
    try {
        renderToday(await api('/api/today'));
    } catch (e) {
        list.innerHTML = `<div style="font-size:0.68rem; color:#ff6b6b;">Couldn't load: ${esc(e.message)}</div>`;
    }
}

function renderToday(data) {
    const list = document.getElementById('todayList');
    if (!data.tracked) {
        list.innerHTML = '<div style="font-size:0.68rem; color:#555; line-height:1.6;">Add positions or ★ watchlist stocks to see their earnings dates, dividends and big moves here.</div>';
        return;
    }
    if (!data.events.length) {
        list.innerHTML = '<div style="font-size:0.68rem; color:#555; line-height:1.6;">Nothing notable for your stocks right now.</div>';
        return;
    }
    list.innerHTML = data.events.slice(0, 12).map(e => {
        const k = TODAY_KINDS[e.kind] || { icon: '•', color: '#888' };
        return `<div onclick="quickSearch(${esc(JSON.stringify(e.name))}, ${esc(JSON.stringify(e.ticker))})"
                     style="display:flex; gap:8px; padding:7px 4px; border-bottom:1px solid #2a2a2a; cursor:pointer;"
                     onmouseover="this.style.background='#1e1e1e'" onmouseout="this.style.background='transparent'">
            <span style="color:${k.color}; width:14px; flex-shrink:0; text-align:center;">${k.icon}</span>
            <div style="min-width:0;">
                <div style="font-size:0.68rem;"><b style="color:var(--accent); font-family:monospace;">${esc(e.ticker)}</b>
                    ${e.held ? '<span style="font-size:0.55rem; color:#888; border:1px solid #444; padding:0 3px; margin-left:3px;">OWNED</span>' : ''}</div>
                <div style="font-size:0.68rem; color:#ccc; line-height:1.4;">${esc(e.text)}</div>
            </div>
        </div>`;
    }).join('') + (data.events.length > 12 ? `<div style="font-size:0.6rem; color:#555; padding-top:6px;">+${data.events.length - 12} more</div>` : '');
}
