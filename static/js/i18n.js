// Language: English (default) or Romanian. Loaded first.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.
//
// How it works (gettext style): the English text IS the key.
//  - Static text in index.html and any text the scripts insert later is translated
//    automatically when it exactly matches a key in RO (a MutationObserver watches the page).
//  - Text with variables goes through t('Saved {ticker}.', { ticker }) explicitly.
//  - A missing translation simply shows the English text.
// The choice lives in the `ws_lang` cookie so it's known instantly on page load and the
// backend can localise its own text (score breakdowns, panel events, AI language).

const LANG = (document.cookie.match(/(?:^|;\s*)ws_lang=(en|ro)/) || [])[1] || 'en';
const LOCALE = LANG === 'ro' ? 'ro-RO' : 'en-US';
document.documentElement.lang = LANG;

const RO = {
    // ---- header / home
    'Loading indices...': 'Se încarcă indicii...',
    'Settings': 'Setări',
    'WATCHLIST': 'LISTĂ DE URMĂRIRE',
    'Refresh prices': 'Actualizează prețurile',
    'Refresh': 'Actualizează',
    'No stocks yet.': 'Nicio acțiune încă.',
    'Click ★ on any stock': 'Apasă ★ pe orice acțiune',
    'to add it here.': 'ca să apară aici.',
    'Company name (e.g. Microsoft)...': 'Numele companiei (ex. Microsoft)...',
    'Ticker, optional (e.g. MSFT)': 'Simbol, opțional (ex. MSFT)',
    'Analyze': 'Analizează',
    'RECENT COMPANIES': 'COMPANII RECENTE',
    'MY PORTFOLIO': 'PORTOFOLIUL MEU',
    '+ ADD POSITION': '+ ADAUGĂ POZIȚIE',
    'IMPORT': 'IMPORT',
    'Loading portfolio...': 'Se încarcă portofoliul...',
    'BY POSITION': 'PE POZIȚII',
    'BY SECTOR': 'PE SECTOARE',
    'MARKET MOVERS': 'CELE MAI MARI MIȘCĂRI',
    'LAST SESSION': 'ULTIMA ȘEDINȚĂ',
    'LARGE CAP': 'CAPITALIZARE MARE',
    'SMALL CAP': 'CAPITALIZARE MICĂ',
    '▲ TOP GAINERS': '▲ CELE MAI MARI CREȘTERI',
    '▼ TOP LOSERS': '▼ CELE MAI MARI SCĂDERI',
    'YOUR STOCKS · NEXT 2 WEEKS': 'ACȚIUNILE TALE · URMĂTOARELE 2 SĂPTĂMÂNI',
    'Loading...': 'Se încarcă...',
    'MARKET NEWS': 'ȘTIRI DE PIAȚĂ',
    'No news available.': 'Nu sunt știri disponibile.',
    'No gainers match this filter.': 'Nicio creștere pentru acest filtru.',
    'No losers match this filter.': 'Nicio scădere pentru acest filtru.',
    'New Search': 'Căutare nouă',
    'Company name (e.g. Apple, NVIDIA)...': 'Numele companiei (ex. Apple, NVIDIA)...',
    'Ticker (Optional, e.g. AAPL)...': 'Simbol (opțional, ex. AAPL)...',
    'Press': 'Apasă',
    'to search  ·': 'pentru căutare  ·',
    'to search  ·': 'pentru căutare  ·',  // &nbsp; in the overlay hint
    'to search ·': 'pentru căutare ·',
    'to close': 'pentru închidere',
    'SEARCH': 'CAUTĂ',
    'No results found.': 'Niciun rezultat.',
    'Please enter a company name.': 'Introdu numele unei companii.',

    // ---- sidebar
    'Open on Yahoo Finance': 'Deschide pe Yahoo Finance',
    'Add to watchlist': 'Adaugă în lista de urmărire',
    'Remove from watchlist': 'Scoate din lista de urmărire',
    'Fetch fresh data from Yahoo Finance': 'Ia date noi de la Yahoo Finance',
    'REFRESH': 'ACTUALIZEAZĂ',
    'REFRESHING...': 'SE ACTUALIZEAZĂ...',
    'Financial Overview': 'Privire de ansamblu',
    'Market Cap': 'Capitalizare',
    'Stock Price': 'Preț acțiune',
    'CEO': 'Director general',
    'Safety Assessment': 'Analiza siguranței',
    'Liquidity': 'Lichiditate',
    'Short-term safety': 'Siguranță pe termen scurt',
    'Stability': 'Stabilitate',
    'Debt & volatility': 'Datorii și volatilitate',
    'Search History': 'Istoric căutări',
    'No searches yet.': 'Nicio căutare încă.',
    'You own': 'Deții',

    // ---- tabs / dashboard
    'FINANCE': 'FINANCIAR',
    'AI ANALYSIS': 'ANALIZĂ AI',
    'NEWS': 'ȘTIRI',
    'Home': 'Acasă',
    'Search': 'Caută',
    'Export JSON': 'Exportă JSON',
    'ANALYSIS IN PROGRESS...': 'ANALIZĂ ÎN CURS...',
    'Structuring real-time market data & parsing NLP signals': 'Se pregătesc datele de piață',
    'OPPORTUNITY SCORE': 'SCOR DE OPORTUNITATE',
    'VALUATION': 'EVALUARE',
    'ANALYST CONSENSUS': 'CONSENSUL ANALIȘTILOR',
    'SMART MONEY': 'INSIDERI ȘI INSTITUȚII',
    'INDUSTRY PEERS': 'COMPANII COMPARABILE',
    'Largest US companies in the same industry · median excludes this stock': 'Cele mai mari companii americane din aceeași industrie · mediana nu include această acțiune',
    'FUNDAMENTALS': 'INDICATORI FUNDAMENTALI',
    'click for breakdown': 'apasă pentru detalii',
    'VALUATION SCORE': 'SCOR EVALUARE',
    'ANALYST SCORE': 'SCOR ANALIȘTI',
    'SMART MONEY SCORE': 'SCOR INSIDERI ȘI INSTITUȚII',
    'RECENT RATINGS': 'RECOMANDĂRI RECENTE',
    'RECENT INSIDER TRANSACTIONS': 'TRANZACȚII RECENTE ALE INSIDERILOR',
    'SHOW LESS': 'ARATĂ MAI PUȚIN',
    'Click to read description': 'Apasă pentru descriere',
    'No description in data — try UPDATE DATA to refresh.': 'Fără descriere în date: încearcă ACTUALIZEAZĂ.',
    'No recent news found for this stock.': 'Nu am găsit știri recente pentru această acțiune.',
    'Sell': 'Vânzare',
    'Buy': 'Cumpărare',
    'Strong Buy': 'Cumpărare puternică',
    'Hold': 'Păstrare',
    'Underperform': 'Sub piață',
    'Mean Target': 'Țintă medie',
    'Trailing P/E': 'P/E (ultimele 12 luni)',
    'Forward P/E': 'P/E estimat',
    'PEG Ratio': 'Raport PEG',
    'Price / Book': 'Preț / Valoare contabilă',
    'Price / Sales': 'Preț / Vânzări',
    'EV / EBITDA': 'EV / EBITDA',
    'earnings growing ↑': 'profit în creștere ↑',
    '< 1.0 = cheap for growth': '< 1,0 = ieftin raportat la creștere',
    'Insider Ownership': 'Deținuți de insideri',
    'Institutional Ownership': 'Deținuți de instituții',
    'Short % of Float': 'Vânzări în lipsă (% din flotant)',
    'Short Ratio (days)': 'Raport short (zile)',
    'elevated': 'ridicat',
    '⚠ high': '⚠ mare',
    'near bottom ↓': 'aproape de minim ↓',
    'near peak ↑': 'aproape de maxim ↑',
    'mid-range': 'la mijloc',
    'Company': 'Companie',
    'Peer median': 'Mediana comparabilelor',
    'P/E': 'P/E',
    'Fwd P/E': 'P/E estimat',
    'PEG': 'PEG',
    'Net margin': 'Marjă netă',
    'Rev growth': 'Creștere venituri',
    'Mkt cap': 'Capitalizare',

    // ---- fundamentals cards
    'Current Ratio': 'Lichiditate curentă',
    'Short-term assets vs liabilities. Above 1.0 means more assets than obligations.': 'Active pe termen scurt față de datorii pe termen scurt. Peste 1,0 înseamnă mai multe active decât obligații.',
    'Quick Ratio': 'Lichiditate imediată',
    'Current ratio excluding inventory — stricter liquidity test.': 'Lichiditatea curentă fără stocuri: un test mai strict.',
    'Profit Margin': 'Marjă de profit',
    'Net income as % of revenue. The higher, the more efficient the business.': 'Profitul net ca % din venituri. Cu cât e mai mare, cu atât afacerea e mai eficientă.',
    'Operating Margin': 'Marjă operațională',
    'Profit after operating costs but before interest/taxes.': 'Profitul după costurile operaționale, înainte de dobânzi și taxe.',
    'Revenue Growth': 'Creșterea veniturilor',
    'Year-over-year revenue change.': 'Schimbarea veniturilor față de anul trecut.',
    'Earnings Growth': 'Creșterea profitului',
    'Year-over-year earnings change.': 'Schimbarea profitului față de anul trecut.',
    'EPS (Trailing)': 'Profit pe acțiune (12 luni)',
    'Earnings per share over the last 12 months.': 'Profitul pe acțiune din ultimele 12 luni.',
    'EPS (Forward)': 'Profit pe acțiune (estimat)',
    'Analyst-estimated earnings per share for next 12 months.': 'Profitul pe acțiune estimat de analiști pentru următoarele 12 luni.',
    'Debt / Equity': 'Datorii / Capital propriu',
    'Total debt relative to shareholders equity. Lower = less leverage risk.': 'Datoriile totale față de capitalul propriu. Mai mic = risc de îndatorare mai mic.',
    'Free Cash Flow': 'Flux de numerar liber',
    'Cash generated after capex. Positive = company funds itself without borrowing.': 'Numerarul generat după investiții. Pozitiv = compania se finanțează fără împrumuturi.',
    'Dividend Yield': 'Randament dividend',
    'Annual dividend as % of current price.': 'Dividendul anual ca % din prețul curent.',
    'Beta': 'Beta',
    'Volatility vs the market. < 1.0 = defensive, > 1.5 = highly volatile.': 'Volatilitatea față de piață. < 1,0 = defensivă, > 1,5 = foarte volatilă.',
    'Total market value of all outstanding shares.': 'Valoarea de piață a tuturor acțiunilor.',

    // ---- AI tab
    'AI Analysis': 'Analiză AI',
    'AI-written from the data on this page. It can be wrong; not financial advice.': 'Scrisă de AI pe baza datelor de pe pagină. Poate greși; nu este o recomandare de investiții.',
    'New AI report': 'Raport AI nou',
    'Interrogating LLM Pipeline...': 'AI-ul analizează...',
    'Executive Summary': 'Rezumat',
    'Recommendation': 'Recomandare',
    'CONVICTION': 'ÎNCREDERE',
    'Since the Last Report': 'De la raportul anterior',
    'Financial Deep Dive': 'Analiză financiară',
    'News Impact Analysis': 'Impactul știrilor',
    'Risk Scenarios': 'Scenarii',
    'Chart Analysis': 'Grafice',
    'No summary provided.': 'Fără rezumat.',
    'STRONG BUY': 'CUMPĂRĂ PUTERNIC',
    'BUY': 'CUMPĂRĂ',
    'HOLD': 'PĂSTREAZĂ',
    'REDUCE': 'REDU',
    'SELL': 'VINDE',
    'STRONG SELL': 'VINDE PUTERNIC',
    'AI analysis is off. Add an OpenRouter API key in Settings (gear icon), then press "New AI report".': 'Analiza AI e oprită. Adaugă o cheie OpenRouter în Setări (rotița), apoi apasă „Raport AI nou”.',

    // ---- chat
    'Ask about this stock (e.g. Is it expensive compared to its growth?)': 'Întreabă despre această acțiune (ex. E scumpă raportat la creștere?)',
    'AI TERMINAL CHAT': 'CHAT CU AI',
    'Initialize query sequence...': 'Pune o întrebare...',
    'Ask a follow-up question...': 'Pune o întrebare suplimentară...',
    'Processing query...': 'Se procesează...',
    'No response.': 'Niciun răspuns.',
    'USER': 'TU',
    'SYSTEM': 'SISTEM',

    // ---- settings
    'API Keys': 'Chei API',
    'Language': 'Limbă',
    'OpenRouter API Key': 'Cheie API OpenRouter',
    'SHOW': 'ARATĂ',
    'HIDE': 'ASCUNDE',
    'Get one at openrouter.ai. Needed only for AI analysis and chat.': 'Se obține de pe openrouter.ai. E necesară doar pentru analiza AI și chat.',
    'Model': 'Model',
    'Any model id from openrouter.ai/models. Ids ending in': 'Orice model de pe openrouter.ai/models. Cele care se termină în',
    'cost nothing but are rate-limited.': 'sunt gratuite, dar limitate.',
    'CANCEL': 'ANULEAZĂ',
    'SAVE': 'SALVEAZĂ',
    'Saved. Leave blank to keep it': 'Salvată. Lasă gol ca să o păstrezi',
    'Settings saved.': 'Setările au fost salvate.',

    // ---- portfolio
    'Add position': 'Adaugă poziție',
    'Stock (company name or ticker)': 'Acțiune (nume sau simbol)',
    'e.g. Apple or AAPL': 'ex. Apple sau AAPL',
    'Shares': 'Acțiuni',
    'Average cost per share': 'Cost mediu pe acțiune',
    "In the stock's own currency (USD for US stocks). If you bought several times, use the average price you paid.": 'În moneda acțiunii (USD pentru acțiunile americane). Dacă ai cumpărat de mai multe ori, folosește prețul mediu plătit.',
    'Why I own it': 'De ce o dețin',
    '(optional)': '(opțional)',
    'e.g. Cloud growth, strong balance sheet, pays a growing dividend.': 'ex. Creștere în cloud, bilanț solid, dividend în creștere.',
    'REMOVE': 'ȘTERGE',
    'CLICK AGAIN TO REMOVE': 'APASĂ DIN NOU PENTRU ȘTERGERE',
    'CHECKING...': 'SE VERIFICĂ...',
    'Profit / loss': 'Profit / pierdere',
    'Today': 'Azi',
    'Dividends / year': 'Dividende / an',
    'expected, at current rates': 'estimat, la valorile actuale',
    'Stock': 'Acțiune',
    'Avg cost': 'Cost mediu',
    'Price': 'Preț',
    'Value': 'Valoare',
    'P/L': 'Profit',
    'Weight': 'Pondere',
    'Thesis': 'Teză',
    'Does your reason for owning it still hold?': 'Mai e valabil motivul pentru care o deții?',
    'EDIT': 'EDITEAZĂ',
    'Edit or remove': 'Editează sau șterge',
    'ADD WHY': 'ADAUGĂ MOTIV',
    "Add a 'why I own it' note to enable thesis checks": 'Adaugă motivul pentru care o deții ca să poți verifica teza',
    'CHECK': 'VERIFICĂ',
    'Ask the AI whether your reason still holds': 'Întreabă AI-ul dacă motivul tău mai e valabil',
    'CHECK AGAIN': 'VERIFICĂ DIN NOU',
    'Asking the AI whether your reason still holds...': 'AI-ul verifică dacă motivul tău mai e valabil...',
    'SUPPORTS IT': 'ÎN FAVOARE',
    'AGAINST IT': 'ÎMPOTRIVĂ',
    'KEEP AN EYE ON': 'DE URMĂRIT',
    'Your thesis:': 'Teza ta:',
    'AI opinion, not advice': 'opinia AI, nu o recomandare',
    'INTACT': 'VALABILĂ',
    'WEAKENING': 'SLĂBEȘTE',
    'BROKEN': 'INVALIDATĂ',
    'UNCLEAR': 'NECLAR',
    'Pick a stock first.': 'Alege mai întâi o acțiune.',
    'Shares must be a number above 0.': 'Numărul de acțiuni trebuie să fie mai mare decât 0.',
    'Average cost must be a number (0 or more).': 'Costul mediu trebuie să fie un număr (0 sau mai mare).',
    'No positions yet. Add the stocks you own to see their value, profit/loss,': 'Nicio poziție încă. Adaugă acțiunile pe care le deții ca să vezi valoarea, profitul,',
    'allocation and expected dividends in one place.': 'alocarea și dividendele estimate într-un singur loc.',

    // ---- today panel
    'OWNED': 'DEȚINUTĂ',
    'Add positions or ★ watchlist stocks to see their earnings dates, dividends and big moves here.': 'Adaugă poziții sau acțiuni ★ în lista de urmărire ca să vezi aici rezultatele financiare, dividendele și mișcările mari.',
    'Nothing notable for your stocks right now.': 'Nimic important pentru acțiunile tale acum.',

    // ---- score modal
    'Score Breakdown': 'Detalii scor',
    'No breakdown available.': 'Fără detalii.',
    'Liquidity (short term)': 'Lichiditate (termen scurt)',
    'Stability: debt & volatility (long term)': 'Stabilitate: datorii și volatilitate (termen lung)',
    'The score is the weighted average of the items with a bar. Lines without a bar explain what was skipped or flagged.': 'Scorul e media ponderată a elementelor cu bară. Rândurile fără bară explică ce a fost omis sau semnalat.',
    'Quality': 'Calitate',
    'Valuation': 'Evaluare',
    'Analyst': 'Analiști',
    'Smart Money': 'Insideri și instituții',

    // ---- parameterised (used via t(text, params))
    'just now': 'acum',
    '{n}m ago': 'acum {n} min',
    '{n}h ago': 'acum {n} h',
    '{n}d ago': 'acum {n} zile',
    '1 day ago': 'acum o zi',
    'data {age}': 'date {age}',
    'offline': 'offline',
    'Fetched {when}': 'Preluate {when}',
    '{n} analysts': '{n} analiști',
    'SHOW {n} MORE': 'ARATĂ ÎNCĂ {n}',
    '{n} position': '{n} poziție',
    '{n} positions': '{n} poziții',
    '{label} — BREAKDOWN': '{label} — DETALII',
    '{pct} upside': '{pct} potențial',
    '{pct} of 52-week range': '{pct} din intervalul pe 52 de săptămâni',
    'Analysed by {model}': 'Analizat de {model}',
    'Analysis failed: {msg}': 'Analiza a eșuat: {msg}',
    'Error: {msg}': 'Eroare: {msg}',
    'Could not save settings: {msg}': 'Setările nu au putut fi salvate: {msg}',
    'Saved {ticker} ({name}).': 'Am salvat {ticker} ({name}).',
    'Removed {ticker} from the portfolio.': 'Am scos {ticker} din portofoliu.',
    "Couldn't load the portfolio: {msg}": 'Portofoliul nu a putut fi încărcat: {msg}',
    "Couldn't load: {msg}": 'Nu s-a putut încărca: {msg}',
    'No stock found for "{q}".': 'Nu am găsit nicio acțiune pentru „{q}”.',
    'Switching to {name} ({ticker})...': 'Trec la {name} ({ticker})...',
    'Edit {ticker}': 'Editează {ticker}',
    'Open {name}': 'Deschide {name}',
    '{ticker} — thesis check': '{ticker} — verificarea tezei',
    'Checked {when}': 'Verificat {when}',
    '+{n} more': 'încă {n}',
    'Value · {cur}': 'Valoare · {cur}',
    'BY POSITION ({cur})': 'PE POZIȚII ({cur})',
    // ---- import
    'Import positions': 'Importă poziții',
    'Load positions from a Tradeville export or a CSV file': 'Încarcă pozițiile dintr-un export Tradeville sau dintr-un fișier CSV',
    'In Tradeville, open your portfolio and export it to a file.': 'În Tradeville, deschide portofoliul și exportă-l într-un fișier.',
    'Pick that file below. You will see a preview first; nothing is saved until you confirm.': 'Alege fișierul mai jos. Vei vedea întâi o previzualizare; nimic nu se salvează până nu confirmi.',
    'CHOOSE FILE': 'ALEGE FIȘIERUL',
    'Any CSV with ticker, shares and avg_cost columns works too.': 'Merge și orice CSV cu coloanele ticker, shares și avg_cost.',
    'That file is too big for a portfolio export.': 'Fișierul e prea mare pentru un export de portofoliu.',
    'Reading the file and checking each stock...': 'Citesc fișierul și verific fiecare acțiune...',
    'Matched by ISIN (file: {ticker})': 'Găsită după ISIN (în fișier: {ticker})',
    'Not found': 'Negăsită',
    'already in portfolio': 'deja în portofoliu',
    '{cur} cash ({amount}) is not imported.': 'Numerarul în {cur} ({amount}) nu se importă.',
    '{symbol}: no shares or cost, skipped.': '{symbol}: fără acțiuni sau cost, omisă.',
    '{symbol}: skipped ({reason}).': '{symbol}: omisă ({reason}).',
    '{n} stock was not found on Yahoo Finance.': '{n} acțiune nu a fost găsită pe Yahoo Finance.',
    '{n} stocks were not found on Yahoo Finance.': '{n} acțiuni nu au fost găsite pe Yahoo Finance.',
    'Type the Yahoo ticker in the red rows (e.g. BRK-B, TLV.RO), then check again. Rows that stay red are left out.': 'Scrie simbolul Yahoo pe rândurile roșii (de ex. BRK-B, TLV.RO), apoi verifică din nou. Rândurile care rămân roșii nu se importă.',
    'CHECK AGAIN': 'VERIFICĂ DIN NOU',
    'Replace my portfolio with this file': 'Înlocuiește portofoliul cu acest fișier',
    'Best for a full Tradeville export. Your "why I own it" notes are kept for stocks that stay.': 'Potrivit pentru un export Tradeville complet. Notițele „de ce o dețin” se păstrează pentru acțiunile care rămân.',
    'Add and update only': 'Doar adaugă și actualizează',
    'Positions that are not in the file stay as they are.': 'Pozițiile care nu sunt în fișier rămân neschimbate.',
    'Tradeville export: {n} positions found.': 'Export Tradeville: {n} poziții găsite.',
    'CSV file: {n} positions found.': 'Fișier CSV: {n} poziții găsite.',
    'PICK ANOTHER FILE': 'ALT FIȘIER',
    'In the file': 'În fișier',
    'Ticker': 'Simbol',
    'Name': 'Nume',
    'Status': 'Stare',
    'IMPORT {n} POSITION': 'IMPORTĂ {n} POZIȚIE',
    'IMPORT {n} POSITIONS': 'IMPORTĂ {n} POZIȚII',
    '1 position you hold now is not selected and will be removed.': 'O poziție pe care o deții acum nu e selectată și va fi ștearsă.',
    '{n} positions you hold now are not selected and will be removed.': '{n} poziții pe care le deții acum nu sunt selectate și vor fi șterse.',
    'SAVING...': 'SE SALVEAZĂ...',
    'Imported {n} position.': 'Am importat {n} poziție.',
    'Imported {n} positions.': 'Am importat {n} poziții.',
    'Using Tradeville? Click IMPORT and pick your portfolio export.': 'Folosești Tradeville? Apasă IMPORT și alege exportul portofoliului.',
    'Loading sector and dividend info for {n} stock...': 'Se încarcă sectorul și dividendele pentru {n} acțiune...',
    'Loading sector and dividend info for {n} stocks...': 'Se încarcă sectorul și dividendele pentru {n} acțiuni...',
};

function t(text, params) {
    let s = (LANG === 'ro' && RO[text]) || text;
    if (params) s = s.replace(/\{(\w+)\}/g, (_, k) => (params[k] ?? ''));
    return s;
}

// Locale-aware number: fmtN(1234.5, 1) -> "1,234.5" (en) / "1.234,5" (ro).
// Returns undefined for null/NaN so callers can keep their `?? '—'` fallbacks.
function fmtN(value, digits = 2) {
    if (value == null || isNaN(value)) return undefined;
    return Number(value).toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtDateTime(iso) {
    return iso ? new Date(iso).toLocaleString(LOCALE) : '';
}

// Highlight the active language in the EN/RO switches.
document.querySelectorAll('[data-lang]').forEach(b => {
    const on = b.dataset.lang === LANG;
    b.style.color = on ? '#fff' : '#666';
    b.style.background = on ? 'var(--accent)' : 'transparent';
});

function setLanguage(lang) {
    document.cookie = `ws_lang=${lang}; path=/; max-age=315360000; SameSite=Lax`;
    location.reload();
}

// ---- automatic translation of page text ----

const _I18N_ATTRS = ['placeholder', 'title'];

function _skip(el) {
    return !!el?.closest?.('.no-i18n');  // news, AI text, chat: never "translate" content
}

function _translateText(node) {
    const raw = node.nodeValue;
    const key = raw.trim();
    if (!key || !RO[key] || RO[key] === key || _skip(node.parentElement)) return;
    // Only write when something changes: writing triggers the MutationObserver again,
    // and an identical write (e.g. 'P/E' -> 'P/E') would loop forever.
    node.nodeValue = raw.replace(key, RO[key]);
}

function _translateAttrs(el) {
    for (const attr of _I18N_ATTRS) {
        const v = el.getAttribute(attr);
        const tr = v && RO[v.trim()];
        if (tr && tr !== v) el.setAttribute(attr, tr);
    }
}

function translateTree(root) {
    if (LANG === 'en' || !root) return;
    if (root.nodeType === Node.TEXT_NODE) return _translateText(root);
    if (root.nodeType !== Node.ELEMENT_NODE || _skip(root)) return;
    _translateAttrs(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
        acceptNode: n => (n.nodeType === Node.ELEMENT_NODE && n.classList.contains('no-i18n'))
            ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    let node;
    while ((node = walker.nextNode())) {
        if (node.nodeType === Node.ELEMENT_NODE) _translateAttrs(node);
        else _translateText(node);
    }
}

if (LANG !== 'en') {
    translateTree(document.body);
    new MutationObserver(mutations => {
        for (const m of mutations) {
            if (m.type === 'characterData') _translateText(m.target);
            else if (m.type === 'attributes') translateTree(m.target);
            else m.addedNodes.forEach(translateTree);
        }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: _I18N_ATTRS });
}
