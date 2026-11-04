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
  check('Inter font loaded', await page.evaluate(() => document.fonts.check('600 12px Inter')));
  check('tailwind css applied', await page.evaluate(() => getComputedStyle(document.querySelector('#initialView')).position === 'absolute'));
  await shot('home');

  // Open a stock: report renders, sanitised
  await page.evaluate(() => quickSearch('Microsoft Corporation', 'MSFT'));
  await page.waitForTimeout(2500);
  check('ticker shown', (await text('#sbTicker')) === 'MSFT');
  check('price in USD', /^\$414\.00$/.test(await text('#sbPrice')), await text('#sbPrice'));
  check('market cap compact', /^\$3\.08T$/.test(await text('#sbMarketCap')), await text('#sbMarketCap'));
  check('as-of label', /data /.test(await text('#asOfLabel')));
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
