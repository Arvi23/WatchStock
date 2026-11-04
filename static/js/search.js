// Layout, autocomplete, search flow (executeSearch/loadStock), refresh, search overlay.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// --- 1. VIEWS & LAYOUT CONTROL ---

function toggleSidebar() {
    const isCollapsed = sidebar.style.marginLeft === '-260px';
    if (isCollapsed) {
        sidebar.style.marginLeft = '0px';
        sidebarIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>';
    } else {
        sidebar.style.marginLeft = '-260px';
        sidebarIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>';
    }
}

// Tabs logic
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        // Remove active from all
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        // Add active to current
        btn.classList.add('active');
        document.getElementById(btn.getAttribute('data-target')).classList.add('active');
    });
});

// --- 2. AUTOCOMPLETE ---

// --- Reusable Autocomplete ---
function initAutocomplete(inputEl, dropdownEl, companyTarget, tickerTarget) {
    let timer;
    inputEl.addEventListener('input', function() {
        const query = this.value.trim();
        if (query.length < 3) {
            dropdownEl.style.display = 'none';
            clearTimeout(timer);
            return;
        }
        clearTimeout(timer);
        timer = setTimeout(async () => {
            try {
                const data = await api(`/api/search?q=${encodeURIComponent(query)}`);

                if (data.length === 0) {
                    dropdownEl.innerHTML = '<div class="p-4 text-sm text-center" style="color: var(--text-muted)">No results found.</div>';
                } else {
                    dropdownEl.innerHTML = '';
                    data.forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'dropdown-item flex justify-between items-center';
                        div.innerHTML = `
                            <span class="font-medium truncate max-w-[70%]">${item.name}</span>
                            <span class="text-xs font-bold" style="color: var(--accent)">${item.ticker}</span>
                        `;
                        div.addEventListener('click', () => {
                            companyTarget.value = item.name;
                            tickerTarget.value = item.ticker;
                            dropdownEl.style.display = 'none';
                        });
                        dropdownEl.appendChild(div);
                    });
                }
                dropdownEl.style.display = 'block';
            } catch (error) {
                console.error(error);
            }
        }, 150);
    });
}

// Attach autocomplete to BOTH inputs
initAutocomplete(companyInput, dropdown, companyInput, tickerInput);

const overlayDropdown = document.getElementById('overlayDropdown');
const overlayCompanyInputEl = document.getElementById('overlayCompanyInput');
const overlayTickerInputEl = document.getElementById('overlayTickerInput');
initAutocomplete(overlayCompanyInputEl, overlayDropdown, overlayCompanyInputEl, overlayTickerInputEl);

document.addEventListener('click', e => {
    if (!companyInput.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.style.display = 'none';
    }
    if (overlayDropdown && !overlayCompanyInputEl.contains(e.target) && !overlayDropdown.contains(e.target)) {
        overlayDropdown.style.display = 'none';
    }
});

// --- 3. MAIN SEARCH TRIGGER ---

// Core search function — callable from initial search, overlay, and chat actions
async function executeSearch(company, ticker) {
    if (!company && !ticker) return;

    // Show dashboard if not already visible
    const isInitial = !initialView.classList.contains('hidden');
    if (isInitial) {
        initialView.classList.add('opacity-0');
        await new Promise(r => setTimeout(r, 500));
        initialView.classList.add('hidden');
        dashboardView.classList.remove('hidden');
        void dashboardView.offsetWidth;
        dashboardView.classList.remove('opacity-0');
    }

    loadingOverlay.classList.remove('hidden');
    try {
        if (!ticker) {
            const matches = await api(`/api/search?q=${encodeURIComponent(company)}`);
            if (!matches.length) throw new Error(`No stock found for "${company}".`);
            ticker = matches[0].ticker;
            company = matches[0].name;
        }
        await loadStock(ticker, company, false);
    } catch (err) {
        console.error(err);
        showToast(err.message, 6000);
        if (!currentRawData) {   // first search failed: go back to the home screen
            dashboardView.classList.add('hidden', 'opacity-0');
            initialView.classList.remove('hidden', 'opacity-0');
        }
    } finally {
        loadingOverlay.classList.add('hidden');
    }
}

// Fetch one stock snapshot and render it. Throws on failure.
async function loadStock(ticker, company, refresh) {
    const params = new URLSearchParams({ name: company || '' });
    if (refresh) params.set('refresh', 'true');
    const data = await api(`/api/stocks/${encodeURIComponent(ticker)}?${params}`);
    currentRawData = data;
    populateDashboard(data);
    updateAsOf(data);

    let avgScore = null;
    if (data.safety) {
        const st = data.safety.short_term?.score || 0;
        const lt = data.safety.long_term?.score || 0;
        avgScore = Math.round((st + lt) / 2);
    }
    addToNavHistory(data.company_name, data.ticker, avgScore);
    if (data.warnings?.length) showToast(data.warnings.join(' '), 6000);

    // Show the stored report if there is one; otherwise generate one in the background.
    if (data.ai_analysis) renderAiAnalysis(data.ai_analysis);
    else if (llmConfigured) requestAnalysis();
    else showNoKeyHint();
}

// Whether an OpenRouter key is saved. Without one we don't auto-request reports.
let llmConfigured = true;
async function refreshLlmStatus() {
    try { llmConfigured = (await api('/api/settings')).llm_api_key_set; } catch (e) {}
}

function showNoKeyHint() {
    document.getElementById('aiLoading').classList.add('hidden');
    aiSummary.innerText = 'AI analysis is off. Add an OpenRouter API key in Settings (gear icon), then press "New AI report".';
    aiAction.innerText = '';
    aiAnalysisResult.classList.remove('hidden');
}

function updateAsOf(data) {
    const el = document.getElementById('asOfLabel');
    if (!el) return;
    el.textContent = data.as_of ? `data ${timeAgo(data.as_of)}${data.stale ? ' · offline' : ''}` : '';
    el.style.color = data.stale ? '#ff9800' : '#666';
    el.title = data.as_of ? 'Fetched ' + new Date(data.as_of).toLocaleString() : '';
}

searchBtn.addEventListener('click', () => {
    const company = companyInput.value.trim();
    const ticker = tickerInput.value.trim();
    if (!company) {
        alert("Please enter a company name.");
        companyInput.focus();
        return;
    }
    executeSearch(company, ticker);
});


async function forceUpdateSupplier() {
    if (!currentRawData) return;
    const btn = document.getElementById('btnForceUpdate');
    btn.innerText = 'REFRESHING...';
    btn.style.opacity = '0.5';
    btn.disabled = true;
    try {
        await loadStock(currentRawData.ticker, currentRawData.company_name, true);
    } catch (err) {
        showToast(err.message, 6000);
    } finally {
        btn.innerText = 'REFRESH';
        btn.style.opacity = '1';
        btn.disabled = false;
    }
}

// --- 7. TOPBAR SEARCH OVERLAY ---
const searchOverlay = document.getElementById('searchOverlay');
const overlayCompanyInput = document.getElementById('overlayCompanyInput');
const overlayTickerInput = document.getElementById('overlayTickerInput');
const overlaySearchBtn = document.getElementById('overlaySearchBtn');
const topbarSearchBtn = document.getElementById('topbarSearchBtn');

function openSearchOverlay() {
    searchOverlay.classList.add('visible');
    setTimeout(() => overlayCompanyInput.focus(), 50);
}

function closeSearchOverlay(e) {
    // Close only if clicking backdrop (not inner box)
    if (e && e.target !== searchOverlay) return;
    searchOverlay.classList.remove('visible');
}

function triggerOverlaySearch() {
    const company = overlayCompanyInput.value.trim();
    const ticker = overlayTickerInput.value.trim();
    if (!company) { overlayCompanyInput.focus(); return; }
    searchOverlay.classList.remove('visible');
    companyInput.value = company;
    tickerInput.value = ticker;
    executeSearch(company, ticker);
}

topbarSearchBtn.addEventListener('click', openSearchOverlay);
overlaySearchBtn.addEventListener('click', triggerOverlaySearch);

overlayCompanyInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') triggerOverlaySearch();
    if (e.key === 'Escape') searchOverlay.classList.remove('visible');
});
overlayTickerInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') triggerOverlaySearch();
    if (e.key === 'Escape') searchOverlay.classList.remove('visible');
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') searchOverlay.classList.remove('visible');
});
