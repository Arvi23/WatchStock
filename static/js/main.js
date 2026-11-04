// Startup. Runs last, after every other script has defined its functions.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

loadUserHistory();
loadWatchlist();
refreshLlmStatus();
loadIndices();
loadMarketMovers();
loadMarketNews();
initPortfolio();
initImport();
loadToday();
