// Stock dashboard: sidebar, finance tab sections, metric cards, news tab, nav history.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// --- Metric Definitions (Fundamentals cards) ---
const fmtPct  = v => v != null ? (v * 100).toFixed(1) + '%' : 'N/A';
const fmtNum  = (d=2) => v => v?.toFixed(d) ?? 'N/A';
const METRIC_DESCRIPTIONS = {
    currentRatio:     { label: 'Current Ratio',      desc: 'Short-term assets vs liabilities. Above 1.0 means more assets than obligations.', format: fmtNum(2) },
    quickRatio:       { label: 'Quick Ratio',        desc: 'Current ratio excluding inventory — stricter liquidity test.', format: fmtNum(2) },
    profitMargins:    { label: 'Profit Margin',      desc: 'Net income as % of revenue. The higher, the more efficient the business.', format: fmtPct },
    operatingMargins: { label: 'Operating Margin',   desc: 'Profit after operating costs but before interest/taxes.', format: fmtPct },
    revenueGrowth:    { label: 'Revenue Growth',     desc: 'Year-over-year revenue change.', format: fmtPct },
    earningsGrowth:   { label: 'Earnings Growth',    desc: 'Year-over-year earnings change.', format: fmtPct },
    trailingEps:      { label: 'EPS (Trailing)',     desc: 'Earnings per share over the last 12 months.', format: v => fmtMoney(v, priceCurrency()) },
    forwardEps:       { label: 'EPS (Forward)',      desc: 'Analyst-estimated earnings per share for next 12 months.', format: v => fmtMoney(v, priceCurrency()) },
    debtToEquity:     { label: 'Debt / Equity',      desc: 'Total debt relative to shareholders equity. Lower = less leverage risk.', format: fmtNum(2) },
    freeCashflow:     { label: 'Free Cash Flow',     desc: 'Cash generated after capex. Positive = company funds itself without borrowing.', format: v => fmtBig(v, statementCurrency()) },
    dividendYield:    { label: 'Dividend Yield',     desc: 'Annual dividend as % of current price.',
                        format: v => v != null ? (v * 100).toFixed(2) + '%' : 'N/A' },  // backend sends a fraction
    beta:             { label: 'Beta',               desc: 'Volatility vs the market. < 1.0 = defensive, > 1.5 = highly volatile.', format: fmtNum(2) },
    marketCap:        { label: 'Market Cap',         desc: 'Total market value of all outstanding shares.', format: v => fmtBig(v, priceCurrency()) },
};

// Maps each metric key to a health tier: 'good' | 'ok' | 'bad' | 'neutral'
const METRIC_HEALTH = {
    currentRatio:     v => v >= 2 ? 'good' : v >= 1 ? 'ok' : 'bad',
    quickRatio:       v => v >= 1 ? 'good' : v >= 0.5 ? 'ok' : 'bad',
    profitMargins:    v => v >= 0.15 ? 'good' : v >= 0.05 ? 'ok' : v >= 0 ? 'neutral' : 'bad',
    operatingMargins: v => v >= 0.15 ? 'good' : v >= 0.05 ? 'ok' : v >= 0 ? 'neutral' : 'bad',
    revenueGrowth:    v => v >= 0.10 ? 'good' : v >= 0 ? 'ok' : 'bad',
    earningsGrowth:   v => v >= 0.15 ? 'good' : v >= 0 ? 'ok' : 'bad',
    trailingEps:      v => v > 0 ? 'good' : 'bad',
    forwardEps:       v => v > 0 ? 'good' : 'bad',
    debtToEquity:     v => v < 50 ? 'good' : v < 150 ? 'ok' : 'bad',
    freeCashflow:     v => v > 0 ? 'good' : 'bad',
    dividendYield:    () => 'neutral',
    beta:             v => v < 1 ? 'good' : v < 1.5 ? 'ok' : 'bad',
    marketCap:        () => 'neutral',
};
const HEALTH_COLOR = { good: '#4caf50', ok: '#ffc107', bad: '#f44336', neutral: '#a0a0a0' };

// --- Finance Tab Rendering Helpers ---

function scoreColor(s) {
    return s >= 70 ? '#4caf50' : s >= 50 ? '#ffc107' : s >= 30 ? '#ff9800' : '#f44336';
}

function metricRow(label, value, note) {
    return `<div style="display:flex; justify-content:space-between; align-items:baseline; padding:5px 0; border-bottom:1px solid #222;">
        <span style="font-size:0.68rem; color:#a0a0a0;">${label}</span>
        <span style="font-size:0.78rem; font-weight:600; font-family:monospace; color:#e0e0e0;">${value ?? '—'}${note ? `<span style="font-size:0.6rem; color:#666; margin-left:5px;">${note}</span>` : ''}</span>
    </div>`;
}

function renderOpportunityScore(scores) {
    if (!scores?.opportunity) return;
    const opp = scores.opportunity;
    document.getElementById('opportunityBanner').style.display = 'block';
    document.getElementById('oppScoreNum').textContent   = opp.score;
    document.getElementById('oppScoreNum').style.color   = opp.color;
    document.getElementById('oppScoreLabel').textContent = opp.label;
    document.getElementById('oppScoreLabel').style.color = opp.color;
    const bar = document.getElementById('oppScoreBar');
    bar.style.width      = opp.score + '%';
    bar.style.background = opp.color;

    document.getElementById('subScoresGrid').innerHTML = (opp.components || []).map(c => `
        <div data-score-key="${esc(c.key)}" onclick="showScoreBreakdown('${esc(c.key)}', event)"
             style="text-align:center; padding:8px; background:#1e1e1e; border:1px solid #333; cursor:pointer; transition:border-color 0.15s;"
             onmouseover="this.style.borderColor='#555'" onmouseout="this.style.borderColor='#333'">
            <div style="font-size:1.1rem; font-weight:700; font-family:monospace; color:${scoreColor(c.score)};">${c.score}</div>
            <div style="font-size:0.58rem; color:#888; margin-top:3px; letter-spacing:0.5px;">${esc(c.label)}</div>
            <div style="font-size:0.55rem; color:#555; margin-top:1px;">${esc(c.weight)}</div>
            <div style="font-size:0.52rem; color:#444; margin-top:3px;">click for breakdown</div>
        </div>`).join('');
}

function renderValuationSection(metrics, vScore) {
    if (!metrics) return;
    const cur = metrics.currentPrice, h52 = metrics.fiftyTwoWeekHigh, l52 = metrics.fiftyTwoWeekLow;
    const pos = (cur && h52 && l52 && h52 > l52) ? ((cur - l52) / (h52 - l52) * 100).toFixed(1) : null;
    const upside = (metrics.targetMeanPrice && cur) ? (((metrics.targetMeanPrice - cur) / cur) * 100).toFixed(1) : null;

    let rangeBar = '';
    if (pos !== null) {
        rangeBar = `<div style="margin:10px 0 4px;">
            <div style="display:flex; justify-content:space-between; font-size:0.58rem; color:#666; margin-bottom:3px;">
                <span>52w Low ${fmtMoney(l52, priceCurrency())}</span><span>52w High ${fmtMoney(h52, priceCurrency())}</span>
            </div>
            <div style="height:4px; background:#333; border-radius:2px; position:relative;">
                <div style="position:absolute; top:-3px; width:10px; height:10px; border-radius:50%; background:var(--accent); left:calc(${pos}% - 5px);"></div>
            </div>
            <div style="font-size:0.6rem; color:#888; margin-top:6px;">${pos}% of 52-week range${vScore?.position_pct != null ? ' · ' + (pos < 30 ? 'near bottom ↓' : pos > 70 ? 'near peak ↑' : 'mid-range') : ''}</div>
        </div>`;
    }

    document.getElementById('valuationData').innerHTML =
        metricRow('Trailing P/E',  metrics.trailingPE?.toFixed(1))  +
        metricRow('Forward P/E',   metrics.forwardPE?.toFixed(1),   metrics.forwardPE < metrics.trailingPE ? 'earnings growing ↑' : '') +
        metricRow('PEG Ratio',     metrics.pegRatio?.toFixed(2),    metrics.pegRatio < 1 ? '< 1.0 = cheap for growth' : '') +
        metricRow('Price / Book',  metrics.priceToBook?.toFixed(2)) +
        metricRow('Price / Sales', metrics.priceToSalesTrailingTwelveMonths?.toFixed(2)) +
        metricRow('EV / EBITDA',   metrics.enterpriseToEbitda?.toFixed(1)) +
        rangeBar +
        (vScore ? `<div style="margin-top:10px; padding:8px; background:#1a1a1a; border:1px solid #333; text-align:center;">
            <div style="font-size:0.58rem; color:#888; margin-bottom:2px;">VALUATION SCORE</div>
            <div style="font-size:1.3rem; font-weight:700; font-family:monospace; color:${scoreColor(vScore.score)};">${vScore.score}/100</div>
        </div>` : '');
}

function renderAnalystSection(analystData, aScore, upgrades) {
    if (!analystData) return;
    const rec = analystData.recommendationKey || '';
    const recLabels = { strongbuy: 'Strong Buy', buy: 'Buy', hold: 'Hold', underperform: 'Underperform', sell: 'Sell' };
    const recColors = { strongbuy: '#4caf50', buy: '#8bc34a', hold: '#ffc107', underperform: '#ff9800', sell: '#f44336' };
    const recKey    = rec.replace('_','').toLowerCase();
    const recLabel  = recLabels[recKey] || rec;
    const recColor  = recColors[recKey] || '#888';
    const mean      = analystData.recommendationMean;
    const tgt       = analystData.targetMeanPrice;
    const tgtLow    = analystData.targetLowPrice;
    const tgtHigh   = analystData.targetHighPrice;
    const n         = analystData.numberOfAnalystOpinions;

    // Bull/bear bar (1=all buy, 5=all sell)
    const bullPct = mean ? Math.round((5 - mean) / 4 * 100) : 50;
    const upside  = aScore?.upside_pct;

    let tgtRange = '';
    if (tgtLow && tgtHigh && tgt) {
        const span = tgtHigh - tgtLow;
        const meanPct = span > 0 ? ((tgt - tgtLow) / span * 100).toFixed(0) : 50;
        tgtRange = `<div style="margin:10px 0;">
            <div style="display:flex; justify-content:space-between; font-size:0.58rem; color:#666; margin-bottom:3px;">
                <span>Low ${fmtMoney(tgtLow, priceCurrency(), 0)}</span><span style="color:#a0a0a0;">Mean ${fmtMoney(tgt, priceCurrency(), 0)}</span><span>High ${fmtMoney(tgtHigh, priceCurrency(), 0)}</span>
            </div>
            <div style="height:4px; background:#333; border-radius:2px; position:relative;">
                <div style="position:absolute; top:-3px; width:10px; height:10px; border-radius:50%; background:var(--accent); left:calc(${meanPct}% - 5px);"></div>
            </div>
        </div>`;
    }

    const ticker = currentRawData?.ticker || '';
    const _ratingRow = u => {
        const isUp   = (u.action||'').toLowerCase() === 'upgrade' || ['buy','strong buy','outperform','overweight','positive'].includes((u.to_grade||'').toLowerCase());
        const isDown = (u.action||'').toLowerCase() === 'downgrade' || ['sell','underperform','underweight','negative'].includes((u.to_grade||'').toLowerCase());
        const arrow  = isUp ? '<span style="color:#4caf50;">▲</span>' : isDown ? '<span style="color:#f44336;">▼</span>' : '<span style="color:#888;">·</span>';
        const gradeColor = isUp ? '#4caf50' : isDown ? '#f44336' : '#888';
        const searchUrl = `https://www.google.com/search?q=${encodeURIComponent((u.firm||'') + ' ' + ticker + ' ' + (u.to_grade||'') + ' analyst rating')}`;
        return `<div style="font-size:0.63rem; padding:4px 0; border-bottom:1px solid #1e1e1e; display:flex; gap:6px; align-items:center;">
            ${arrow}
            <span style="color:#666; flex-shrink:0;">${u.date?.slice(0,10) || ''}</span>
            <a href="${searchUrl}" target="_blank" rel="noopener" style="color:#a0a0a0; font-weight:600; text-decoration:none; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" onmouseover="this.style.color='var(--accent)'" onmouseout="this.style.color='#a0a0a0'">${u.firm || ''}</a>
            <span style="color:${gradeColor}; white-space:nowrap; flex-shrink:0;">${u.to_grade || ''}</span>
        </div>`;
    };
    const allUpgrades  = (upgrades || []);
    const upgradeList  = allUpgrades.slice(0, 5).map(_ratingRow).join('');
    const upgradeExtra = allUpgrades.slice(5).map(_ratingRow).join('');

    document.getElementById('analystData').innerHTML =
        `<div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
            <span style="font-size:1.1rem; font-weight:800; color:${recColor}; letter-spacing:1px;">${recLabel || '—'}</span>
            <span style="font-size:0.65rem; color:#666;">${n ? n + ' analysts' : ''}</span>
        </div>` +
        (mean ? `<div style="margin-bottom:10px;">
            <div style="height:4px; background:#333; border-radius:2px; overflow:hidden;">
                <div style="height:100%; width:${bullPct}%; background:linear-gradient(to right,#4caf50,#ffc107);"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.55rem; color:#555; margin-top:2px;"><span>Sell</span><span>Buy</span></div>
        </div>` : '') +
        metricRow('Mean Target', tgt ? fmtMoney(tgt, priceCurrency()) : '—', upside != null ? `${upside > 0 ? '+' : ''}${upside}% upside` : '') +
        tgtRange +
        (upgradeList ? `<div style="margin-top:10px;">
            <div style="font-size:0.55rem; letter-spacing:1.5px; color:#555; margin-bottom:6px;">RECENT RATINGS</div>
            ${upgradeList}
            ${upgradeExtra ? `<div id="ratingsExtra" style="display:none;">${upgradeExtra}</div>
            <button onclick="toggleExtra('ratingsExtra',this)" style="width:100%; margin-top:6px; padding:4px; background:transparent; border:1px solid #333; color:#666; font-size:0.62rem; cursor:pointer; letter-spacing:1px;">SHOW ${allUpgrades.length - 5} MORE</button>` : ''}
        </div>` : '') +
        (aScore ? `<div style="margin-top:10px; padding:8px; background:#1a1a1a; border:1px solid #333; text-align:center;">
            <div style="font-size:0.58rem; color:#888; margin-bottom:2px;">ANALYST SCORE</div>
            <div style="font-size:1.3rem; font-weight:700; font-family:monospace; color:${scoreColor(aScore.score)};">${aScore.score}/100</div>
        </div>` : '');
}

function renderSmartMoneySection(metrics, sScore, insiderTxns) {
    if (!metrics) return;
    const ins   = metrics.heldPercentInsiders;
    const inst  = metrics.heldPercentInstitutions;
    const short = metrics.shortPercentOfFloat;
    const shortR = metrics.shortRatio;

    const flags = sScore?.flags || [];

    const _isBuy  = tx => /purchase|bought|acqui|open market p|\bp\b/i.test(tx);
    const _isSell = tx => /sale|sold|dispos|\bs\b/i.test(tx);
    const _txnColor = t => {
        const tx = t.transaction || '';
        return _isBuy(tx) ? '#4caf50' : _isSell(tx) ? '#f44336' : '#888';
    };
    const _txnLabel = t => {
        const tx = t.transaction || '';
        return _isBuy(tx) ? 'BUY' : _isSell(tx) ? 'SELL' : (tx || '?');
    };
    const _txnRow = t => {
        const color = _txnColor(t);
        const label = _txnLabel(t);
        const val   = t.value ? fmtBig(Math.abs(t.value), 'USD') : '';  // SEC filings are in USD
        const isUnknown = label === '?' || label === '';
        const safeText  = (t.text || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
        const revealText = safeText || '<span style="color:#555;font-style:italic;">No description in data — try UPDATE DATA to refresh.</span>';
        const pillStyle = `font-size:0.6rem; font-weight:700; padding:1px 6px; flex-shrink:0; margin-top:1px; cursor:pointer; letter-spacing:0.5px;`;
        const pillColor = isUnknown ? '#f5c518' : color;
        const pillHtml  = `<span onclick="var d=this.parentNode.querySelector('.txn-raw');d.style.display=d.style.display==='none'?'block':'none';"
                   style="${pillStyle} color:${pillColor}; background:${pillColor}15; border:1px solid ${pillColor}40;"
                   title="Click to read description">${isUnknown ? '?' : label}</span>`;
        return `<div style="font-size:0.63rem; padding:5px 0; border-bottom:1px solid #1e1e1e; display:flex; gap:8px; align-items:flex-start;">
            ${pillHtml}
            <div style="flex:1; min-width:0;">
                <div style="display:flex; justify-content:space-between; align-items:baseline; gap:4px;">
                    <span style="color:#ccc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${t.insider || ''}</span>
                    <span style="color:${color}; white-space:nowrap; flex-shrink:0; font-family:monospace; font-weight:600;">${val}</span>
                </div>
                <div style="display:flex; justify-content:space-between; margin-top:2px;">
                    ${t.title ? `<span style="font-size:0.58rem; color:#666; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${t.title}</span>` : '<span></span>'}
                    <span style="font-size:0.58rem; color:#555; flex-shrink:0;">${t.date?.slice(0,10) || ''}</span>
                </div>
                <div class="txn-raw" style="display:none; font-size:0.62rem; color:#999; background:#161616; border:1px solid #2a2a2a; padding:5px 7px; margin-top:4px; line-height:1.5;">${revealText}</div>
            </div>
        </div>`;
    };
    const allTxns = (insiderTxns || []);
    const txnList = allTxns.slice(0, 5).map(_txnRow).join('');
    const txnExtra = allTxns.slice(5).map(_txnRow).join('');

    document.getElementById('smartMoneyData').innerHTML =
        metricRow('Insider Ownership',       ins  != null ? (ins  * 100).toFixed(1) + '%' : '—') +
        metricRow('Institutional Ownership', inst != null ? (inst * 100).toFixed(1) + '%' : '—') +
        metricRow('Short % of Float',        short != null ? (short * 100).toFixed(1) + '%' : '—',
            short > 0.15 ? '⚠ high' : short > 0.10 ? 'elevated' : '') +
        metricRow('Short Ratio (days)',      shortR?.toFixed(1)) +
        (flags.length ? flags.map(f => `<div style="font-size:0.63rem; color:#ff9800; background:#1a1a1a; border:1px solid #333; padding:6px 8px; margin-top:6px; line-height:1.4;">⚠ ${f}</div>`).join('') : '') +
        (txnList ? `<div style="margin-top:10px;">
            <div style="font-size:0.55rem; letter-spacing:1.5px; color:#555; margin-bottom:6px;">RECENT INSIDER TRANSACTIONS</div>
            ${txnList}
            ${txnExtra ? `<div id="txnExtra" style="display:none;">${txnExtra}</div>
            <button onclick="toggleExtra('txnExtra',this)" style="width:100%; margin-top:6px; padding:4px; background:transparent; border:1px solid #333; color:#666; font-size:0.62rem; cursor:pointer; letter-spacing:1px;">SHOW ${allTxns.length - 5} MORE</button>` : ''}
        </div>` : '') +
        (sScore ? `<div style="margin-top:10px; padding:8px; background:#1a1a1a; border:1px solid #333; text-align:center;">
            <div style="font-size:0.58rem; color:#888; margin-bottom:2px;">SMART MONEY SCORE</div>
            <div style="font-size:1.3rem; font-weight:700; font-family:monospace; color:${scoreColor(sScore.score)};">${sScore.score}/100</div>
        </div>` : '');
}

// --- Navigation History ---
function addToNavHistory(company, ticker, safetyScore) {
    // Add to front of array, dedupe
    searchHistory = searchHistory.filter(h => h.ticker !== ticker);
    searchHistory.unshift({ company, ticker, time: new Date(), score: safetyScore || null });
    if (searchHistory.length > 10) searchHistory.pop();
    saveUserHistory();
    renderNavHistory();
}

function getScoreDotColor(score) {
    if (score === null || score === undefined) return '#555';
    if (score >= 65) return '#22c55e';  // green
    if (score >= 40) return '#f59e0b';  // amber
    return '#ef4444';                    // red
}

function renderNavHistory() {
    const navHistory = document.getElementById('navHistory');
    navHistory.innerHTML = '';
    if (searchHistory.length === 0) {
        navHistory.innerHTML = '<div class="text-xs" style="color: var(--text-muted)">No searches yet.</div>';
        return;
    }
    searchHistory.forEach(h => {
        const item = document.createElement('div');
        item.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:6px 8px; cursor:pointer; border-bottom:1px solid #2a2a2a; transition: background 0.15s;';
        item.onmouseenter = () => item.style.background = '#252526';
        item.onmouseleave = () => item.style.background = 'transparent';

        const timeStr = new Date(h.time).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
        const dotColor = getScoreDotColor(h.score);
        item.innerHTML = `
            <div style="display:flex; align-items:center; gap:6px;">
                <span style="width:6px; height:6px; border-radius:50%; background:${dotColor}; flex-shrink:0;"></span>
                <span style="color:var(--accent); font-weight:700; font-size:0.7rem; font-family:monospace;">${h.ticker}</span>
                <span style="color:var(--text-muted); font-size:0.65rem; max-width:90px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${h.company}</span>
            </div>
            <span style="color:#555; font-size:0.6rem; font-family:monospace;">${timeStr}</span>
        `;
        item.addEventListener('click', () => {
            companyInput.value = h.company;
            tickerInput.value = h.ticker;
            executeSearch(h.company, h.ticker);
        });
        navHistory.appendChild(item);
    });
}


// --- 4. POPULATE DASHBOARD ---

function populateDashboard(data) {
    // Destroy all existing Chart.js instances and remove appended chart wrappers
    document.querySelectorAll('canvas').forEach(c => {
        const chart = Chart.getChart(c);
        if (chart) chart.destroy();
    });
    dynamicChartInstance = null;

    // Reset logo glow
    document.getElementById('companyLogoBox').style.boxShadow = 'none';

    // Reset AI Analysis tab to its original structure (remove appended Agent Insight / chart divs)
    const aiResult = document.getElementById('aiAnalysisResult');
    aiResult.querySelectorAll('.mt-8').forEach(el => el.remove());
    aiResult.classList.add('hidden');

    // Reset verdict badge to placeholder state
    const verdictBadge = document.getElementById('verdictBadge');
    if (verdictBadge) { verdictBadge.textContent = '—'; verdictBadge.style.borderColor = '#444'; verdictBadge.style.color = '#666'; verdictBadge.style.background = 'transparent'; }
    document.getElementById('verdictConfidenceRow')?.classList.add('hidden');
    document.getElementById('verdictHorizonRow')?.classList.add('hidden');

    // Clear charts grid
    const chartsGrid = document.getElementById('chartsGrid');
    if (chartsGrid) { chartsGrid.querySelectorAll('canvas').forEach(c => { const ch = Chart.getChart(c); if (ch) ch.destroy(); }); chartsGrid.innerHTML = ''; }
    document.getElementById('chartsSection')?.classList.add('hidden');

    // Reset text sections
    document.getElementById('newsImpactSection')?.classList.add('hidden');
    document.getElementById('financialDeepDiveSection')?.classList.add('hidden');
    document.getElementById('changesSection')?.classList.add('hidden');
    document.getElementById('riskScenariosSection')?.classList.add('hidden');

    // Build Sidebar
    sbTicker.innerText = data.ticker || 'N/A';
    updateWatchlistStar(data.ticker);
    sbLogoInitials.innerText = (data.ticker || data.company_name.substring(0,2)).substring(0,2).toUpperCase();
    
    const sbLogoImg = document.getElementById('sbLogoImg');
    sbLogoImg.classList.add('hidden');
    sbLogoInitials.style.display = 'block';
    
    if (data.company_domain) {
        // Try multiple logo sources with fallback chain
        const domain = data.company_domain;
        const logoSources = [
            `https://img.logo.dev/${domain}?token=pk_anonymous&size=128`,
            `https://www.google.com/s2/favicons?domain=${domain}&sz=128`,
            `https://logo.clearbit.com/${domain}`
        ];
        
        let sourceIdx = 0;
        function tryNextLogo() {
            if (sourceIdx >= logoSources.length) {
                sbLogoImg.classList.add('hidden');
                sbLogoInitials.style.display = 'block';
                return;
            }
            sbLogoImg.src = logoSources[sourceIdx];
            sourceIdx++;
        }
        
        sbLogoImg.onload = () => { 
            sbLogoImg.classList.remove('hidden'); 
            sbLogoInitials.style.display = 'none';
        };
        sbLogoImg.onerror = () => tryNextLogo();
        tryNextLogo();
    }

    const metrics = data.financial_data?.metrics || {};
    const cap = fmtBig(metrics.marketCap, metrics.currency || 'USD');
    sbMarketCap.innerText = cap;
    const price = metrics.currentPrice;
    sbPrice.innerText = fmtMoney(price, metrics.currency || 'USD');

    // --- TradingView Widget ---
    const tvContainer = document.getElementById('tradingViewContainer');
    tvContainer.innerHTML = '';
    if (data.ticker) {
        tvContainer.style.display = 'block';
        const tvScript = document.createElement('script');
        tvScript.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
        tvScript.type = 'text/javascript';
        tvScript.async = true;
        tvScript.innerHTML = JSON.stringify({
            "autosize": true, "symbol": data.tradingview_symbol || data.ticker, "interval": "D",
            "timezone": "Etc/UTC", "theme": "dark", "style": "1",
            "locale": "en", "allow_symbol_change": false,
            "backgroundColor": "rgba(19, 23, 34, 1)",
            "gridColor": "rgba(51, 51, 51, 0.3)",
            "hide_top_toolbar": false, "hide_legend": true,
            "save_image": false, "height": "100%", "width": "100%"
        });
        tvContainer.appendChild(tvScript);
    } else {
        tvContainer.style.display = 'none';
    }

    // ---- Opportunity Score banner ----
    renderOpportunityScore(data.scores);

    // ---- Three-column deep dive ----
    renderValuationSection(metrics, data.scores?.valuation);
    renderAnalystSection(data.financial_data?.analyst_data, data.scores?.analyst, data.financial_data?.upgrades_downgrades);
    renderSmartMoneySection(metrics, data.scores?.smart_money, data.financial_data?.insider_transactions);

    // ---- Fundamentals metric cards ----
    const metricCards = document.getElementById('metricCards');
    metricCards.innerHTML = '';
    const cardKeys = [
        'currentRatio','quickRatio','profitMargins','operatingMargins',
        'revenueGrowth','earningsGrowth','trailingEps','forwardEps',
        'debtToEquity','freeCashflow','dividendYield','beta','marketCap'
    ];
    cardKeys.forEach(key => {
        const def = METRIC_DESCRIPTIONS[key];
        if (!def) return;
        const val = metrics[key];
        if (val == null) return;
        const card = document.createElement('div');
        card.style.cssText = 'background:#1a1a1a; border:1px solid #333; padding:14px 16px; transition:border-color 0.2s; cursor:default;';
        card.onmouseenter = () => card.style.borderColor = '#555';
        card.onmouseleave = () => card.style.borderColor = '#333';
        const tier  = METRIC_HEALTH[key]?.(val) ?? 'neutral';
        const vColor = HEALTH_COLOR[tier];
        card.innerHTML = `
            <div style="font-size:0.6rem; color:#888; text-transform:uppercase; letter-spacing:1px; margin-bottom:5px;">${def.label}</div>
            <div style="font-size:1.25rem; font-weight:700; font-family:monospace; color:${vColor}; margin-bottom:7px;">${def.format(val)}</div>
            <div style="font-size:0.68rem; color:var(--text-muted); line-height:1.4;">${def.desc}</div>
        `;
        metricCards.appendChild(card);
    });
    
    // Officers string (Only CEO)
    sbCEOList.innerHTML = '';
    if (data.financial_data?.key_officers) {
        data.financial_data.key_officers.slice(0, 1).forEach(o => {
            let wpLink = `https://en.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(o.name)}`;
            sbCEOList.innerHTML += `<a href="${wpLink}" target="_blank" class="hover:underline text-[0.95rem]" style="color: var(--accent)">${o.name}</a><span class="text-xs text-gray-500">${o.title}</span>`;
        });
    }

    // Sidebar Risk Badges
    if (data.safety) {
        sidebarRiskScores.classList.remove('hidden');
        const st = data.safety.short_term.score;
        const lt = data.safety.long_term.score;
        sbStCircle.innerText = st;
        sbStCircle.style.color = `hsl(${st * 1.2}, 100%, 50%)`;
        sbStCircle.style.borderColor = `hsl(${st * 1.2}, 100%, 40%)`;
        
        sbLtCircle.innerText = lt;
        sbLtCircle.style.color = `hsl(${lt * 1.2}, 100%, 50%)`;
        sbLtCircle.style.borderColor = `hsl(${lt * 1.2}, 100%, 40%)`;

        // Logo glow based on average safety
        const avg = (st + lt) / 2;
        const glowHue = avg * 1.2; // 0=red, 60=yellow, 120=green
        document.getElementById('companyLogoBox').style.boxShadow = `0 0 12px hsla(${glowHue}, 100%, 45%, 0.4)`;
    }


    // News — headlines from Yahoo Finance for this ticker
    newsContent.innerHTML = '';
    const news = data.news || [];
    if (news.length === 0) {
        newsContent.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:40px;">No recent news found for this stock.</p>';
    }
    news.forEach(item => {
        let domain = '';
        try { domain = new URL(item.url).hostname; } catch (e) {}
        const card = document.createElement('div');
        card.style.cssText = 'border:1px solid #333; padding:16px; margin-bottom:12px; background:#1a1a1a; transition: border-color 0.2s;';
        card.onmouseenter = () => card.style.borderColor = '#555';
        card.onmouseleave = () => card.style.borderColor = '#333';
        card.innerHTML = `
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                ${domain ? `<img src="https://www.google.com/s2/favicons?domain=${esc(domain)}&sz=32" alt="" style="width:16px;height:16px;flex-shrink:0;border-radius:2px;">` : ''}
                <a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer" style="color:var(--text-main); font-weight:600; font-size:0.9rem; text-decoration:none; line-height:1.3;" onmouseover="this.style.color='var(--accent)'" onmouseout="this.style.color='var(--text-main)'">${esc(item.title)}</a>
            </div>
            ${item.summary ? `<p style="color:var(--text-muted); font-size:0.8rem; line-height:1.5; margin:0;">${esc(item.summary)}</p>` : ''}
            <div style="margin-top:8px; font-size:0.65rem; color:#666; text-transform:uppercase; letter-spacing:1px;">${esc(item.publisher)}${item.published_at ? ' · ' + timeAgo(item.published_at) : ''}</div>
        `;
        newsContent.appendChild(card);
    });
}
