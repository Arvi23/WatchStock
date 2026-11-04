// UI smoke test + screenshots against scripts/fake_server.py (port 8001).
//
// The sandbox can't reach CDNs, so CDN scripts are served from local npm copies:
//   mkdir /tmp/mk && cd /tmp/mk && npm i marked chart.js @tailwindcss/browser@4
//   NODE_PATH=$(npm root -g) NM=/tmp/mk/node_modules OUT=/tmp/shots node scripts/ui_smoke.js
// (@tailwindcss/browser v4 only approximates the v3 Play CDN the page uses.)
// Prints UI state + console errors as JSON; screenshots go to $OUT.
const { chromium } = require('playwright');
const fs = require('fs');
const NM = process.env.NM;
const local = {
  'cdn.tailwindcss.com': NM + '/@tailwindcss/browser/dist/index.global.js',
  'marked': NM + '/marked/lib/marked.umd.js',
  'chart.js': NM + '/chart.js/dist/chart.umd.min.js',
};
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await page.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('http://127.0.0.1')) return route.continue();
    for (const [k, f] of Object.entries(local)) if (url.includes(k)) return route.fulfill({ path: f, contentType: 'application/javascript' });
    return route.abort();
  });
  await page.goto('http://127.0.0.1:8001/');
  await page.waitForTimeout(1500);
  await page.screenshot({ path: process.env.OUT + '/home.png' });
  await page.evaluate(() => quickSearch('Microsoft Corporation', 'MSFT'));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: process.env.OUT + '/dash_ai.png' });
  await page.click('.tab-btn[data-target="tab-finance"]').catch(e => errors.push('no finance tab ' + e.message));
  await page.waitForTimeout(500);
  await page.screenshot({ path: process.env.OUT + '/dash_finance.png' });
  await page.click('.tab-btn[data-target="tab-news"]').catch(e => errors.push('no news tab'));
  await page.waitForTimeout(300);
  await page.screenshot({ path: process.env.OUT + '/dash_news.png' });
  // watchlist star + refresh + bad ticker
  await page.click('#btnWatchlist');
  await page.waitForTimeout(500);
  await page.click('#btnForceUpdate');
  await page.waitForTimeout(1500);
  const state = await page.evaluate(() => ({
    asOf: document.getElementById('asOfLabel').textContent,
    ticker: document.getElementById('sbTicker').textContent,
    wl: document.getElementById('watchlistPanel').innerText.slice(0, 60),
    model: document.getElementById('aiModelLabel').textContent,
    link: document.querySelector('#financialDeepDiveContent a')?.outerHTML,
  }));
  await page.evaluate(() => quickSearch('Fail Corp', 'FAIL'));
  await page.waitForTimeout(1500);
  state.toast = await page.evaluate(() => document.getElementById('toastMsg').textContent);
  state.tickerAfterFail = await page.evaluate(() => document.getElementById('sbTicker').textContent);
  await page.evaluate(() => openSettings());
  await page.waitForTimeout(500);
  await page.screenshot({ path: process.env.OUT + '/settings.png' });
  console.log(JSON.stringify({ state, errors }, null, 1));
  await browser.close();
})();
