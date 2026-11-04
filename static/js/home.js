// Home screen: indices, market news, movers, watchlist, search history.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// ---- Market Indices ----
async function loadIndices() {
    try {
        const data = await api('/api/market/indices');
        if (!data.length) return;
        document.getElementById('indicesBar').innerHTML = data.map(idx => {
            const pos   = idx.change_pct >= 0;
            const color = pos ? '#4caf50' : '#f44336';
            const arrow = pos ? '▲ ' : '▼ ';
            const val   = fmtN(idx.value, 2);
            return `<div style="display:flex; align-items:center; gap:7px; padding:4px 10px; background:#252526; border:1px solid #333; white-space:nowrap;">
                <span style="font-size:0.62rem; color:#a0a0a0; letter-spacing:1px;">${idx.name}</span>
                <span style="font-size:0.72rem; font-weight:600; color:#e0e0e0; font-family:monospace;">${val}</span>
                <span style="font-size:0.65rem; font-weight:700; color:${color}; font-family:monospace;">${arrow}${idx.change_pct >= 0 ? '+' : ''}${fmtN(idx.change_pct, 2)}%</span>
            </div>`;
        }).join('');
    } catch(e) {
        document.getElementById('indicesBar').innerHTML = '';
    }
}

// ---- Market News ----
async function loadMarketNews() {
    try {
        const data = await api('/api/market/news');
        if (!data.length) { document.getElementById('newsList').innerHTML = '<div style="font-size:0.7rem;color:#444;">No news available.</div>'; return; }
        document.getElementById('newsList').innerHTML = data.map(n => `
            <a href="${n.url}" target="_blank" rel="noopener noreferrer"
               style="display:block; margin-bottom:14px; text-decoration:none; padding-bottom:14px; border-bottom:1px solid #333;"
               onmouseover="this.style.opacity='0.75'" onmouseout="this.style.opacity='1'">
                <div style="font-size:0.72rem; color:#ccc; line-height:1.45; margin-bottom:4px;">${n.title}</div>
                <div style="font-size:0.6rem; color:#555;">${n.publisher} &middot; ${timeAgo(n.published_at)}</div>
            </a>`).join('');
    } catch(e) {}
}

// ---- Market Movers ----
let _moversData = null;
let _moversTab  = 'large'; // default to large cap
const LARGE_CAP_THRESHOLD = 10_000_000_000; // >= $10B — large cap
// small cap = anything below large cap (no lower bound)

async function loadMarketMovers() {
    try {
        _moversData = await api('/api/market/movers');
        if (!_moversData.gainers?.length && !_moversData.losers?.length) return;
        if ([0, 6].includes(new Date().getDay())) document.getElementById('marketStatusBadge').style.display = 'inline';
        renderMovers();
        document.getElementById('marketMovers').style.display = 'block';
    } catch(e) {}
}

function setMoversTab(tab) {
    _moversTab = tab;
    document.getElementById('moversTabLarge').style.background = tab === 'large' ? 'var(--accent)' : 'transparent';
    document.getElementById('moversTabLarge').style.color      = tab === 'large' ? '#fff' : '#666';
    document.getElementById('moversTabSmall').style.background = tab === 'small' ? 'var(--accent)' : 'transparent';
    document.getElementById('moversTabSmall').style.color      = tab === 'small' ? '#fff' : '#666';
    renderMovers();
}

function renderMovers() {
    if (!_moversData) return;
    let gainers = _moversData.gainers || [];
    let losers  = _moversData.losers  || [];
    if (_moversTab === 'large') {
        gainers = gainers.filter(x => x.market_cap && x.market_cap >= LARGE_CAP_THRESHOLD);
        losers  = losers.filter(x  => x.market_cap && x.market_cap >= LARGE_CAP_THRESHOLD);
    } else {
        gainers = gainers.filter(x => !x.market_cap || x.market_cap < LARGE_CAP_THRESHOLD);
        losers  = losers.filter(x  => !x.market_cap || x.market_cap < LARGE_CAP_THRESHOLD);
    }
    renderMoversList(gainers.slice(0,5), 'gainersList', true);
    renderMoversList(losers.slice(0,5),  'losersList',  false);
}

function renderMoversList(items, containerId, positive) {
    const color = positive ? '#4caf50' : '#f44336';
    document.getElementById(containerId).innerHTML = items.length
        ? items.map(item => `
            <div onclick="quickSearch('${item.name.replace(/'/g,"\\'")}','${item.ticker}')"
                 style="cursor:pointer; padding:7px 10px; background:#1e1e1e; border:1px solid #333; margin-bottom:3px; display:flex; justify-content:space-between; align-items:center; transition:background 0.15s;"
                 onmouseover="this.style.background='#252526'" onmouseout="this.style.background='#1e1e1e'">
                <div style="min-width:0; overflow:hidden;">
                    <span style="font-size:0.72rem; font-weight:700; color:#e0e0e0; font-family:monospace;">${item.ticker}</span>
                    <span style="font-size:0.6rem; color:#999; margin-left:6px;">${item.name}</span>
                </div>
                <span style="font-size:0.75rem; font-weight:700; color:${color}; white-space:nowrap; margin-left:8px; font-family:monospace;">${item.change_pct >= 0 ? '+' : ''}${fmtN(item.change_pct, 2)}%</span>
            </div>`).join('')
        : `<div style="font-size:0.68rem; color:#444; padding:8px 4px;">No ${positive ? 'gainers' : 'losers'} match this filter.</div>`;
}

function quickSearch(company, ticker) {
    document.getElementById('companyInput').value = company;
    document.getElementById('tickerInput').value  = ticker;
    document.getElementById('searchBtn').click();
}


// ---- Watchlist ----
let _watchlistData = [];
const wlCacheKey = () => 'wl_local';

async function loadWatchlist() {
    // Render cached data instantly (synchronous localStorage read)
    try {
        const raw = localStorage.getItem(wlCacheKey());
        if (raw) { _watchlistData = JSON.parse(raw); renderWatchlist(); }
    } catch(e) {}
    // Then silently fetch fresh prices in background
    _refreshWatchlistPrices();
}

async function _refreshWatchlistPrices() {
    try {
        const fresh = await api('/api/watchlist');
        _watchlistData = fresh;
        localStorage.setItem(wlCacheKey(), JSON.stringify(fresh));
        renderWatchlist();
    } catch(e) {}
}

function renderWatchlist() {
    const panel = document.getElementById('watchlistPanel');
    if (!panel) return;
    if (!_watchlistData.length) {
        panel.innerHTML = '<div style="font-size:0.63rem; color:#555; text-align:center; margin-top:24px; padding:0 8px; line-height:1.7;">No stocks yet.<br>Click ★ on any stock<br>to add it here.</div>';
        return;
    }
    panel.innerHTML = _watchlistData.map(item => {
        const pos   = (item.change_pct ?? 0) >= 0;
        const color = pos ? '#4caf50' : '#f44336';
        const chg   = item.change_pct != null ? `${pos ? '+' : ''}${fmtN(item.change_pct, 2)}%` : '--';
        const price = item.price != null ? fmtMoney(item.price, item.currency || 'USD') : '--';
        const name  = (item.company_name || '').replace(/'/g, "\\'");
        return `<div onclick="quickSearch('${name}','${item.ticker}')"
                     style="cursor:pointer; padding:8px; margin-bottom:3px; background:#1e1e1e; border:1px solid #333; transition:background 0.15s;"
                     onmouseover="this.style.background='#252526'" onmouseout="this.style.background='#1e1e1e'">
            <div style="display:flex; justify-content:space-between; align-items:center; gap:4px;">
                <span style="font-size:0.72rem; font-weight:700; color:#e0e0e0; font-family:monospace;">${item.ticker}</span>
                <span style="font-size:0.65rem; font-weight:700; color:${color}; font-family:monospace; white-space:nowrap;">${chg}</span>
            </div>
            <div style="font-size:0.58rem; color:#888; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${item.company_name || ''}</div>
            <div style="font-size:0.65rem; color:#ccc; font-family:monospace; margin-top:2px;">${price}</div>
        </div>`;
    }).join('');
}

async function toggleWatchlist() {
    if (!currentRawData) return;
    const ticker      = (currentRawData.ticker || '').toUpperCase();
    const companyName = currentRawData.company_name || '';
    if (!ticker) return;
    const inList = _watchlistData.some(x => x.ticker === ticker);
    if (inList) {
        _watchlistData = _watchlistData.filter(x => x.ticker !== ticker);
    } else {
        // Seed with cached price if we already have it from a previous analysis load
        const cachedPrice = currentRawData?.financial_data?.metrics?.currentPrice ?? null;
        _watchlistData.push({ ticker, company_name: companyName, price: cachedPrice, change_pct: null });
    }
    // Write to localStorage immediately so the next load is instant
    localStorage.setItem(wlCacheKey(), JSON.stringify(_watchlistData));
    updateWatchlistStar(ticker);
    renderWatchlist();
    // Fire-and-forget: persist to DB and silently refresh price
    if (inList) {
        api(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: 'DELETE' }).catch(e => showToast(e.message));
    } else {
        api('/api/watchlist', { method: 'POST', body: { ticker, company_name: companyName } })
            .then(() => _refreshWatchlistPrices())
            .catch(e => showToast(e.message));
    }
}

function updateWatchlistStar(ticker) {
    const btn = document.getElementById('btnWatchlist');
    if (!btn) return;
    const inList = _watchlistData.some(x => x.ticker === (ticker || '').toUpperCase());
    btn.textContent = inList ? '★' : '☆';
    btn.style.color = inList ? '#f5c518' : '#666';
    btn.title       = inList ? 'Remove from watchlist' : 'Add to watchlist';
}


function getUserHistoryKey() {
    return 'history_local';
}

function loadUserHistory() {
    try {
        const saved = localStorage.getItem(getUserHistoryKey());
        if (saved) {
            searchHistory = JSON.parse(saved).map(h => ({ ...h, time: new Date(h.time) }));
            renderNavHistory();
            renderHomeHistory();
        }
    } catch(e) {}
}

function renderHomeHistory() {
    const container = document.getElementById('homeHistoryItems');
    const wrapper = document.getElementById('homeHistory');
    if (!container || !wrapper || searchHistory.length === 0) return;
    wrapper.style.display = '';
    container.innerHTML = '';
    searchHistory.slice(0, 6).forEach(h => {
        const dotColor = getScoreDotColor(h.score);
        const chip = document.createElement('button');
        chip.style.cssText = `display:flex; align-items:center; gap:8px; padding:10px 16px; background:#1e1e1e; border:1px solid #333; cursor:pointer; transition:all 0.15s; color:var(--text-main); font-family:'Inter',sans-serif; font-size:0.8rem;`;
        chip.onmouseenter = () => { chip.style.borderColor = 'var(--accent)'; chip.style.background = '#252526'; };
        chip.onmouseleave = () => { chip.style.borderColor = '#333'; chip.style.background = '#1e1e1e'; };
        chip.innerHTML = `
            <span style="width:7px; height:7px; border-radius:50%; background:${dotColor}; flex-shrink:0;"></span>
            <span style="font-weight:700; font-family:monospace; color:var(--accent); font-size:0.75rem;">${h.ticker}</span>
            <span style="color:var(--text-muted); font-size:0.7rem; max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${h.company}</span>
        `;
        chip.addEventListener('click', () => {
            companyInput.value = h.company;
            tickerInput.value = h.ticker;
            executeSearch(h.company, h.ticker);
        });
        container.appendChild(chip);
    });
}

function saveUserHistory() {
    try {
        localStorage.setItem(getUserHistoryKey(), JSON.stringify(searchHistory));
    } catch(e) {}
}

let debounceTimer;
let searchHistory = [];
