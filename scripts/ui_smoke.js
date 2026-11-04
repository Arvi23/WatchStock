// End-to-end UI smoke test against scripts/fake_server.py (port 8001).
//
//   uv run python scripts/fake_server.py &      # fake Yahoo + LLM, throwaway DB
//   npm ci && node scripts/ui_smoke.js          # OUT=/some/dir to also save screenshots
//
// Exits non-zero if any check fails or the page throws. All app assets are local, so
// only external extras (TradingView, logos, favicons) are blocked.
const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8001';
const OUT = process.env.OUT;
const failures = [];
const check = (name, ok, detail = '') => { if (!ok) failures.push(`${name}${detail ? ': ' + detail : ''}`); };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => {
    const t = m.text();
    if (m.type() === 'error' && !/ERR_FAILED|status of 502|Too Many Requests/.test(t)) errors.push(t);
  });
  await page.route('**/*', r => (r.request().url().startsWith(BASE) ? r.continue() : r.abort()));
  const shot = async name => OUT && page.screenshot({ path: `${OUT}/${name}.png` });
  const text = sel => page.evaluate(s => document.querySelector(s)?.innerText ?? null, sel);

  // Home
  await page.goto(BASE + '/');
  await page.waitForTimeout(1200);
  check('indices render', /S&P 500/.test(await text('#indicesBar')));
  // Explicitly load the face (browsers fetch fonts lazily) and confirm it came from /static/vendor.
  check('Inter font loaded', await page.evaluate(async () => (await document.fonts.load('600 12px Inter')).length > 0));
  check('tailwind css applied', await page.evaluate(() => getComputedStyle(document.querySelector('#initialView')).position === 'absolute'));
  await shot('home');

  // Portfolio: empty state, add (decimal comma), bad ticker, charts, flags
  check('portfolio empty state', /No positions yet/.test(await text('#portfolioTable')));
  const addPosition = async (ticker, shares, cost) => {
    await page.click('#btnAddHolding');
    await page.fill('#holdingTicker', ticker);
    await page.fill('#holdingShares', shares);
    await page.fill('#holdingCost', cost);
    await page.click('#btnSaveHolding');
    await page.waitForTimeout(1200);
  };
  await addPosition('MSFT', '10', '300,50');
  await addPosition('AAPL', '5', '150');
  await addPosition('NVDA', '20', '50');
  await addPosition('TLV.RO', '100', '20');
  const pfTable = await text('#portfolioTable');
  check('portfolio rows', /MSFT/.test(pfTable) && /AAPL/.test(pfTable) && /TLV\.RO/.test(pfTable), pfTable);
  check('decimal comma cost', /\$300\.50/.test(pfTable), pfTable);
  check('RON position priced in RON', /RON\s?100\.00/.test(pfTable), pfTable);
  check('USD summary value', /\$3,500\.00/.test(await text('#portfolioSummary')), await text('#portfolioSummary'));
  check('allocation charts shown', await page.evaluate(() => getComputedStyle(document.getElementById('portfolioCharts')).display === 'grid'));
  check('concentration flag', /NVDA is 57% of your USD holdings/.test(await text('#portfolioFlags')), await text('#portfolioFlags'));
  await page.click('#btnAddHolding');
  await page.fill('#holdingTicker', 'FAIL');
  await page.fill('#holdingShares', '1');
  await page.fill('#holdingCost', '1');
  await page.click('#btnSaveHolding');
  await page.waitForTimeout(1000);
  check('bad ticker error in modal', /429/.test(await text('#holdingError')));
  await page.evaluate(() => closeHoldingModal());
  await shot('portfolio');
  // edit prefills, two-click remove
  await page.evaluate(() => openHoldingModal('AAPL'));
  check('edit prefills', (await page.inputValue('#holdingShares')) === '5');
  await page.click('#btnDeleteHolding');
  check('remove needs confirmation', /CLICK AGAIN/.test(await text('#btnDeleteHolding')));
  await page.click('#btnDeleteHolding');
  await page.waitForTimeout(1000);
  check('position removed', !/AAPL/.test(await text('#portfolioTable')));

  // Today panel: events for held/watched stocks
  await page.waitForTimeout(800);
  const todayText = await text('#todayList');
  check('today: big move first', /NVDA[\s\S]*Down 6\.5% today/.test(todayText), todayText);
  check('today: earnings', /Earnings in 3 days/.test(todayText), todayText);
  check('today: ex-dividend', /Ex-dividend in 5 days/.test(todayText), todayText);
  check('today: rating', /Example Securities upgraded Hold → Buy/.test(todayText), todayText);
  check('today: insider buy', /Insider buy: Jane Doe \(\$1\.2M\)/.test(todayText), todayText);

  // Thesis check: needs a note first
  check('thesis needs a note', /ADD WHY/.test(await text('#portfolioTable')));
  await page.evaluate(() => openHoldingModal('MSFT'));
  await page.fill('#holdingNotes', 'Cloud growth and a strong balance sheet.');
  await page.click('#btnSaveHolding');
  await page.waitForTimeout(1200);
  await page.click('#portfolioTable button:has-text("CHECK")');
  await page.waitForTimeout(1500);
  const thesis = await text('#scoreModalBody');
  check('thesis result', /INTACT/.test(thesis) && /cloud growth is still visible/.test(thesis) && /Your thesis: Cloud growth/.test(thesis), thesis);
  await shot('thesis');
  await page.evaluate(() => closeScoreModal());
  await page.waitForTimeout(500);
  check('thesis badge in table', /INTACT/.test(await text('#portfolioTable')));

  // Open a stock: report renders, sanitised
  await page.evaluate(() => quickSearch('Microsoft Corporation', 'MSFT'));
  await page.waitForTimeout(2500);
  check('ticker shown', (await text('#sbTicker')) === 'MSFT');
  check('price in USD', /^\$414\.00$/.test(await text('#sbPrice')), await text('#sbPrice'));
  check('market cap compact', /^\$3\.08T$/.test(await text('#sbMarketCap')), await text('#sbMarketCap'));
  check('as-of label', /data /.test(await text('#asOfLabel')));
  check('you-own line', /You own 10/.test(await text('#sbHolding')), await text('#sbHolding'));
  const deepDive = await page.evaluate(() => document.getElementById('financialDeepDiveContent').innerHTML);
  check('markdown link rendered', /<a href="https:\/\/example.com" target="_blank"/.test(deepDive), deepDive.slice(0, 200));
  check('LLM HTML sanitised', !/onerror|<script|<img/i.test(deepDive) && !(await page.evaluate(() => window.__xss)), deepDive);
  check('since-last-report hidden on first report', await page.evaluate(() => document.getElementById('changesSection').classList.contains('hidden')));
  await shot('dashboard_ai');

  // Finance tab: breakdown popover, safety modal, dividend
  await page.click('.tab-btn[data-target="tab-finance"]');
  await page.click('[data-score-key="quality"]');
  check('quality breakdown', /Net margin 36\.0%/.test(await text('#popoverContent')), await text('#popoverContent'));
  await shot('popover');
  await page.evaluate(() => { hideScoreBreakdown(); showScoreExplanation('long_term'); });
  check('safety modal', /Debt\/Equity 0\.30x/.test(await text('#scoreModalBody')));
  await page.evaluate(() => closeScoreModal());
  const dividend = await page.evaluate(() => [...document.querySelectorAll('#metricCards > div')].map(d => d.innerText).find(t => /dividend/i.test(t)) || '');
  check('dividend yield as percent', /0\.88%/.test(dividend), dividend);
  const fcf = await page.evaluate(() => [...document.querySelectorAll('#metricCards > div')].map(d => d.innerText).find(t => /free cash/i.test(t)) || '');
  check('FCF in statement currency', /\$70B/.test(fcf), fcf);

  // Watchlist + refresh
  await page.click('#btnWatchlist');
  await page.waitForTimeout(500);
  check('watchlist add', /MSFT/.test(await text('#watchlistPanel')));
  await page.click('#btnForceUpdate');
  await page.waitForTimeout(1500);
  check('refresh keeps stock', (await text('#sbTicker')) === 'MSFT');

  // Non-USD stock: currencies and TradingView symbol
  await page.evaluate(() => quickSearch('Banca Transilvania', 'TLV.RO'));
  await page.waitForTimeout(2000);
  check('RON price', /RON/.test(await text('#sbPrice')), await text('#sbPrice'));
  check('tradingview symbol', await page.evaluate(() => currentRawData.tradingview_symbol === 'BVB:TLV'));
  await page.evaluate(() => quickSearch('Taiwan Semiconductor', 'TSM'));
  await page.waitForTimeout(2000);
  const tsmFcf = await page.evaluate(() => [...document.querySelectorAll('#metricCards > div')].map(d => d.innerText).find(t => /free cash/i.test(t)) || '');
  check('TSM FCF in TWD', /NT\$|TWD/.test(tsmFcf), tsmFcf);

  // Second report shows "since the last report"
  await page.evaluate(() => quickSearch('Microsoft Corporation', 'MSFT'));
  await page.waitForTimeout(1500);
  await page.evaluate(() => requestAnalysis());
  await page.waitForTimeout(2000);
  check('since-last-report shown', await page.evaluate(() => !document.getElementById('changesSection').classList.contains('hidden')));

  // Chat
  await page.fill('#oldChatInput', 'Is it cheap?');
  await page.press('#oldChatInput', 'Enter');
  await page.waitForTimeout(1500);
  check('chat reply', /Fake chat answer/.test(await text('#chatHistory')));
  await shot('chat');

  // No API key: no auto report, hint instead
  await page.evaluate(async () => { await api('/api/settings', { method: 'PUT', body: { llm_api_key: '' } }); await refreshLlmStatus(); });
  await page.evaluate(() => quickSearch('Apple', 'AAPL'));
  await page.waitForTimeout(1500);
  check('no-key hint', /AI analysis is off/.test(await text('#aiSummary')), await text('#aiSummary'));

  // Upstream failure: toast, previous stock stays
  await page.evaluate(() => quickSearch('Fail Corp', 'FAIL'));
  await page.waitForTimeout(1500);
  check('failure toast', /429/.test(await text('#toastMsg')));
  check('previous stock kept', (await text('#sbTicker')) === 'AAPL');

  // Settings modal
  await page.evaluate(() => openSettings());
  await page.waitForTimeout(300);
  await shot('settings');

  await browser.close();
  for (const e of errors) failures.push('page error: ' + e);
  if (failures.length) {
    console.error('UI smoke FAILED:\n  - ' + failures.join('\n  - '));
    process.exit(1);
  }
  console.log('UI smoke passed');
})().catch(e => { console.error(e); process.exit(1); });
