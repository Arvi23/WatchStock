// AI report: rendering, requesting a new one, JSON export.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

const VERDICT_COLORS = {
    'STRONG BUY':  { border: '#52b788', color: '#52b788', bg: 'rgba(82,183,136,0.12)' },
    'BUY':         { border: '#69db7c', color: '#69db7c', bg: 'rgba(105,219,124,0.12)' },
    'HOLD':        { border: '#ffd43b', color: '#ffd43b', bg: 'rgba(255,212,59,0.12)'  },
    'REDUCE':      { border: '#ff8c42', color: '#ff8c42', bg: 'rgba(255,140,66,0.12)'  },
    'STRONG SELL': { border: '#ff4444', color: '#ff4444', bg: 'rgba(255,68,68,0.12)'   },
    'SELL':        { border: '#ff6b6b', color: '#ff6b6b', bg: 'rgba(255,107,107,0.12)' },
};

// --- Render AI Analysis (from cache or API) ---
function renderAiAnalysis(aiData) {
    if (!aiData) return;

    aiSummary.innerText = aiData.executive_summary || "No summary provided.";
    const modelLabel = document.getElementById('aiModelLabel');
    if (modelLabel && aiData.model) {
        modelLabel.textContent = `Analysed by ${aiData.model}` + (aiData.created_at ? ` · ${new Date(aiData.created_at).toLocaleString()}` : '');
    }

    // Verdict badge
    const verdict = aiData.verdict || {};
    const rawAction = (verdict.action || aiData.recommended_action || '').toUpperCase();
    let colors = { border: '#444', color: '#666', bg: 'transparent' };
    let badgeText = rawAction || '—';
    for (const [key, val] of Object.entries(VERDICT_COLORS)) {
        if (rawAction.includes(key)) { colors = val; badgeText = key; break; }
    }
    const verdictBadge = document.getElementById('verdictBadge');
    verdictBadge.textContent = badgeText;
    verdictBadge.style.borderColor = colors.border;
    verdictBadge.style.color = colors.color;
    verdictBadge.style.background = colors.bg;

    const confRow = document.getElementById('verdictConfidenceRow');
    if (verdict.confidence != null) {
        document.getElementById('verdictConfidenceBar').style.background = colors.border;
        document.getElementById('verdictConfidenceBar').style.width = verdict.confidence + '%';
        document.getElementById('verdictConfidenceVal').textContent = verdict.confidence + '/100';
        confRow.classList.remove('hidden');
    } else {
        confRow.classList.add('hidden');
    }

    const horizonRow = document.getElementById('verdictHorizonRow');
    if (verdict.horizon) {
        document.getElementById('verdictHorizon').textContent = verdict.horizon;
        horizonRow.classList.remove('hidden');
    } else {
        horizonRow.classList.add('hidden');
    }

    aiAction.innerText = aiData.recommended_action || '';

    // What changed since the previous report (only when there was one)
    const changesSection = document.getElementById('changesSection');
    if (aiData.changes_since_last) {
        document.getElementById('changesContent').innerHTML = renderMarkdown(aiData.changes_since_last);
        changesSection.classList.remove('hidden');
    } else {
        changesSection.classList.add('hidden');
    }

    // Financial Deep Dive
    const deepDiveSection = document.getElementById('financialDeepDiveSection');
    const deepDiveContent = document.getElementById('financialDeepDiveContent');
    if (aiData.financial_deep_dive) {
        deepDiveContent.innerHTML = renderMarkdown(aiData.financial_deep_dive);
        deepDiveSection.classList.remove('hidden');
    } else {
        deepDiveSection.classList.add('hidden');
    }

    // News Impact Analysis
    const newsImpactSection = document.getElementById('newsImpactSection');
    const newsImpactContent = document.getElementById('newsImpactContent');
    if (aiData.news_impact_analysis) {
        newsImpactContent.innerHTML = renderMarkdown(aiData.news_impact_analysis);
        newsImpactSection.classList.remove('hidden');
    } else {
        newsImpactSection.classList.add('hidden');
    }

    // Risk Scenarios
    const riskSection = document.getElementById('riskScenariosSection');
    const riskContent = document.getElementById('riskScenariosContent');
    if (aiData.risk_scenarios) {
        riskContent.innerHTML = renderMarkdown(aiData.risk_scenarios);
        riskSection.classList.remove('hidden');
    } else {
        riskSection.classList.add('hidden');
    }

    // Charts — support new `charts` array OR legacy `dynamic_ui_config`
    const chartsSection = document.getElementById('chartsSection');
    const chartsGrid = document.getElementById('chartsGrid');
    const chartConfigs = aiData.charts || (aiData.dynamic_ui_config ? [aiData.dynamic_ui_config] : []);

    chartsGrid.querySelectorAll('canvas').forEach(c => { const ch = Chart.getChart(c); if (ch) ch.destroy(); });
    chartsGrid.innerHTML = '';
    dynamicChartInstance = null;

    if (chartConfigs.length > 0) {
        chartConfigs.forEach((cfg, i) => {
            const uid = 'aiChart_' + i;
            const wrapper = document.createElement('div');
            wrapper.className = 'bg-[#1a1a1a] border border-[#333] p-4';
            const canvas = document.createElement('canvas');
            canvas.id = uid;
            canvas.style.maxHeight = '240px';
            wrapper.appendChild(canvas);
            chartsGrid.appendChild(wrapper);
        });
        chartConfigs.forEach((cfg, i) => {
            const instance = createChart('aiChart_' + i, cfg);
            if (i === 0) dynamicChartInstance = instance;
        });
        chartsSection.classList.remove('hidden');
    } else {
        chartsSection.classList.add('hidden');
    }

    // Show the result panel, hide loading
    const aiLoading = document.getElementById('aiLoading');
    aiLoading.classList.add('hidden');
    aiLoading.classList.add('opacity-0');
    aiAnalysisResult.classList.remove('hidden');
    
    // Store on raw data for chat context
    if (currentRawData) currentRawData.ai_analysis = aiData;
}

// --- 5. AI GENERATION LOGIC ---

async function requestAnalysis() {
    if (!currentRawData || btnAiAnalyze.disabled) return;
    const ticker = currentRawData.ticker;

    btnAiAnalyze.disabled = true;
    const orgHtml = btnAiAnalyze.innerHTML;
    btnAiAnalyze.innerHTML = '<div class="spinner w-4 h-4 border-2 mr-2"></div> Standby...';

    aiAnalysisResult.classList.add('hidden');
    const aiLoading = document.getElementById('aiLoading');
    const aiProgressBar = document.getElementById('aiProgressBar');
    aiLoading.classList.remove('hidden');
    void aiLoading.offsetWidth;  // trigger reflow
    aiLoading.classList.remove('opacity-0');

    let width = 0;
    const progressInterval = setInterval(() => {
        width += (100 - width) * 0.15;
        aiProgressBar.style.width = width + '%';
    }, 300);

    try {
        const data = await api(`/api/stocks/${encodeURIComponent(ticker)}/analysis`, { method: 'POST' });
        if (currentRawData?.ticker === ticker) renderAiAnalysis(data);
    } catch (err) {
        if (currentRawData?.ticker === ticker) {
            aiLoading.classList.add('hidden');
            aiSummary.innerText = 'Analysis failed: ' + err.message;
            aiAction.innerText = '';
            aiAnalysisResult.classList.remove('hidden');
        }
    } finally {
        clearInterval(progressInterval);
        aiProgressBar.style.width = '100%';
        setTimeout(() => {
            aiLoading.classList.add('hidden');
            aiLoading.classList.add('opacity-0');
            btnAiAnalyze.disabled = false;
            btnAiAnalyze.innerHTML = orgHtml;
        }, 400);
    }
}

btnAiAnalyze.addEventListener('click', requestAnalysis);

// Downloads
function downloadJSON() {
    if (!currentRawData) return;
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentRawData, null, 2));
    const anchor = document.createElement('a');
    anchor.href = dataStr;
    anchor.download = `Terminal_${currentRawData.ticker || 'Export'}.json`;
    anchor.click();
}
