// Shared helpers and state: API calls, escaping, formatting, DOM handles, toast.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// Configure marked: all links open in new tab so they never navigate away from the SPA.
// marked >= 13 passes a single token object to renderers (the old (href, title, text)
// signature rendered every link as "undefined").
marked.use({
    renderer: {
        link({ href, title, tokens }) {
            const text = this.parser.parseInline(tokens);
            return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer"${title ? ` title="${esc(title)}"` : ''}>${text}</a>`;
        }
    }
});

// Constants & State
const companyInput = document.getElementById('companyInput');
const tickerInput = document.getElementById('tickerInput');
const dropdown = document.getElementById('dropdown');
const searchBtn = document.getElementById('searchBtn');

// View containers
const initialView = document.getElementById('initialView');
const dashboardView = document.getElementById('dashboardView');
const loadingOverlay = document.getElementById('loadingOverlay');

// Sidebar
const sidebar = document.getElementById('sidebar');
const sidebarIcon = document.getElementById('sidebarIcon');
const sbLogoInitials = document.getElementById('sbLogoInitials');
const sbTicker = document.getElementById('sbTicker');
const sbCompanyName = document.getElementById('sbCompanyName');
const sbMarketCap = document.getElementById('sbMarketCap');
const sbPrice = document.getElementById('sbPrice');
const sbCEOList = document.getElementById('sbCEOList');
const sidebarRiskScores = document.getElementById('sidebarRiskScores');
const sbStCircle = document.getElementById('sbStCircle');
const sbLtCircle = document.getElementById('sbLtCircle');

// Main Content
const newsContent = document.getElementById('newsContent');

// AI
const btnAiAnalyze = document.getElementById('btnAiAnalyze');
const aiAnalysisResult = document.getElementById('aiAnalysisResult');
const aiSummary = document.getElementById('aiSummary');
const aiAction = document.getElementById('aiAction');

let currentRawData = null;
let dynamicChartInstance = null;

// ---- API helper ----
// All backend calls go through here: JSON in/out, throws Error(detail) on non-2xx.
async function api(path, options = {}) {
    const opts = { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } };
    if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) {
        const detail = data?.detail;
        throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`);
    }
    return data;
}

function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// Markdown from the LLM -> sanitised HTML. Model output is untrusted (it reads news
// articles), so it never reaches innerHTML without DOMPurify.
function renderMarkdown(text) {
    return DOMPurify.sanitize(marked.parse(String(text ?? '')), {
        ADD_ATTR: ['target'],
        FORBID_TAGS: ['img', 'style', 'form', 'input', 'iframe'],  // no remote images/tracking pixels
    });
}

// ---- Money ----
// Prices are in `metrics.currency`; statement values (FCF, revenue) in
// `metrics.financialCurrency` (different for e.g. foreign companies listed in the US).
// Yahoo uses minor units for a few markets: GBp = pence, ZAc = cents, ILA = agorot.
const MINOR_UNITS = { GBp: ['GBP', 'p'], GBX: ['GBP', 'p'], ZAc: ['ZAR', 'c'], ILA: ['ILS', 'ag'] };

function priceCurrency() {
    return currentRawData?.financial_data?.metrics?.currency || 'USD';
}

function statementCurrency() {
    const m = currentRawData?.financial_data?.metrics || {};
    return m.financialCurrency || m.currency || 'USD';
}

function fmtMoney(value, currency = 'USD', digits = 2) {
    if (value == null || isNaN(value)) return 'N/A';
    const minor = MINOR_UNITS[currency];
    if (minor) {
        return Number(value).toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits }) + ' ' + minor[1];
    }
    try {
        return new Intl.NumberFormat(LOCALE, {
            style: 'currency', currency, minimumFractionDigits: digits, maximumFractionDigits: digits,
        }).format(value);
    } catch (e) {
        return `${Number(value).toFixed(digits)} ${currency}`;
    }
}

// Large amounts in compact form: $3.08T, €70.1B, -$512M.
// Assumes Yahoo reports aggregates (market cap, cash flow) in major units even for GBp quotes.
function fmtBig(value, currency = 'USD') {
    if (value == null || isNaN(value)) return 'N/A';
    const major = MINOR_UNITS[currency]?.[0] || currency;
    try {
        return new Intl.NumberFormat(LOCALE, {
            style: 'currency', currency: major, notation: 'compact', maximumFractionDigits: 2,
        }).format(value);
    } catch (e) {
        return `${(value / 1e9).toFixed(2)}B ${currency}`;
    }
}

function timeAgo(iso) {
    if (!iso) return '';
    const secs = (Date.now() - new Date(iso).getTime()) / 1000;
    if (isNaN(secs)) return '';
    if (secs < 60) return t('just now');
    if (secs < 3600) return t('{n}m ago', { n: Math.floor(secs / 60) });
    if (secs < 86400) return t('{n}h ago', { n: Math.floor(secs / 3600) });
    const days = Math.floor(secs / 86400);
    return days === 1 ? t('1 day ago') : t('{n}d ago', { n: days });
}


// ---- Toast ----
function showToast(msg, duration = 2500) {
    const el = document.getElementById('toastMsg');
    el.textContent = msg;
    el.style.display = 'block';
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.display = 'none'; }, duration);
}
