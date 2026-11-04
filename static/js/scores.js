// Score breakdown popover (opportunity pillars) and safety modal.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// ---- Score breakdowns ----
// Items with a score get a bar; items without one are explanations (skipped inputs, flags).
function renderBreakdownItems(items) {
    return (items || []).map(item => {
        if (item.score !== null && item.score !== undefined) {
            const c = scoreColor(item.score);
            return `<div style="margin-bottom:10px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
                    <span style="font-size:0.68rem; color:#a0a0a0; flex:1;">${esc(item.item)}</span>
                    <span style="font-size:0.7rem; font-weight:700; font-family:monospace; color:${c}; margin-left:8px;">${item.score}<span style="font-size:0.55rem; color:#555;">/100</span></span>
                    ${item.weight ? `<span style="font-size:0.55rem; color:#555; margin-left:6px;">${esc(item.weight)}</span>` : ''}
                </div>
                <div style="height:3px; background:#2a2a2a; border-radius:2px; overflow:hidden;">
                    <div style="height:100%; width:${item.score}%; background:${c};"></div>
                </div>
            </div>`;
        }
        return `<div style="font-size:0.63rem; color:#888; padding:4px 0; border-bottom:1px solid #222; line-height:1.4;">${esc(item.item)}${item.note ? `<span style="color:#555;"> · ${esc(item.note)}</span>` : ''}</div>`;
    }).join('');
}

// ---- Score Breakdown Popover ----
function showScoreBreakdown(key, event) {
    event.stopPropagation();
    if (!currentRawData?.scores) return;
    const data    = currentRawData.scores[key];
    if (!data) return;
    const comp = currentRawData.scores.opportunity?.components?.find(c => c.key === key);
    document.getElementById('popoverTitle').textContent = (comp?.label || key).toUpperCase() + ' — BREAKDOWN';

    let html = renderBreakdownItems(data.breakdown);

    if (key === 'smart_money' && data.flags?.length) {
        html += `<div style="margin-top:10px; padding-top:8px; border-top:1px solid #333;">`;
        data.flags.forEach(f => { html += `<div style="font-size:0.62rem; color:#ff9800; margin-bottom:4px; line-height:1.4;">⚠ ${f}</div>`; });
        html += `</div>`;
    }
    if (key === 'analyst' && data.upside_pct != null) {
        html += `<div style="margin-top:10px; padding:7px; background:#1a1a1a; border:1px solid #333; font-size:0.65rem; color:#a0a0a0;">
            Price-target upside: <span style="color:${data.upside_pct >= 0 ? '#4caf50' : '#f44336'}; font-weight:700; font-family:monospace;">${data.upside_pct > 0 ? '+' : ''}${data.upside_pct}%</span>
        </div>`;
    }

    document.getElementById('popoverContent').innerHTML = html || '<div style="color:#555; font-size:0.72rem;">No breakdown available.</div>';

    const popover = document.getElementById('scoreBreakdownPopover');
    popover.style.display = 'block';
    const rect     = event.currentTarget.getBoundingClientRect();
    const pw       = 290;
    let   left     = rect.left;
    let   top      = rect.bottom + 8;
    if (left + pw > window.innerWidth - 12) left = window.innerWidth - pw - 12;
    if (top + popover.offsetHeight > window.innerHeight - 12) top = rect.top - popover.offsetHeight - 8;
    popover.style.left = left + 'px';
    popover.style.top  = top  + 'px';
}

function hideScoreBreakdown() {
    document.getElementById('scoreBreakdownPopover').style.display = 'none';
}

function toggleExtra(id, btn) {
    const el = document.getElementById(id);
    if (!el) return;
    const showing = el.style.display !== 'none';
    el.style.display = showing ? 'none' : 'block';
    const n = el.querySelectorAll('[style*="border-bottom"]').length || '';
    btn.textContent = showing ? `SHOW ${n} MORE` : 'SHOW LESS';
}

document.addEventListener('click', e => {
    const p = document.getElementById('scoreBreakdownPopover');
    if (p && p.style.display !== 'none' && !p.contains(e.target) && !e.target.closest('[data-score-key]'))
        hideScoreBreakdown();
});

// ---- Yahoo Finance link ----
function openYahooFinance() {
    const ticker = currentRawData?.ticker;
    if (ticker) window.open(`https://finance.yahoo.com/quote/${ticker}`, '_blank', 'noopener');
}


// --- Score Explanation Modal ---
function showScoreExplanation(type) {
    const safety = currentRawData?.safety;
    if (!safety?.[type]) return;
    const data = safety[type];
    const label = type === 'short_term' ? 'Liquidity (short term)' : 'Solvency & Volatility (long term)';
    document.getElementById('scoreModalTitle').innerText = `${label} — ${data.score}/100`;
    document.getElementById('scoreModalBody').innerHTML = renderBreakdownItems(data.breakdown) +
        `<div style="margin-top:14px; font-size:0.65rem; color:#666; line-height:1.5;">The score is the weighted average of the items with a bar. Lines without a bar explain what was skipped or flagged.</div>`;
    document.getElementById('scoreModal').style.display = 'flex';
}

function closeScoreModal() {
    document.getElementById('scoreModal').style.display = 'none';
}

document.getElementById('scoreModal').addEventListener('click', function(e) {
    if (e.target === this) closeScoreModal();
});
