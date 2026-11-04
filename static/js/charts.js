// Chart.js helpers. Colours come from a fixed palette; LLM-supplied colours are ignored.
// Plain script (not a module): all files share one global scope and load in the
// order listed in index.html. Top-level code may only call functions from earlier files.

// --- Terminal Chart Color Palette (strict, LLM colors are ignored) ---
const TERMINAL_COLORS = ['#0078D4', '#00CC6A', '#D13438', '#FFB900', '#8A2BE2', '#00BFFF', '#FF8C00'];

function getChartColors(labels) {
    return labels.map((label, i) => {
        const l = (label || '').toLowerCase();
        if (l.includes('debt') || l.includes('risk') || l.includes('loss') || l.includes('penalty')) return '#D13438';
        if (l.includes('profit') || l.includes('cash') || l.includes('safety') || l.includes('growth') || l.includes('revenue')) return '#00CC6A';
        return TERMINAL_COLORS[i % TERMINAL_COLORS.length];
    });
}

function createChart(canvasId, cfg) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    Chart.defaults.color = '#a0a0a0';
    Chart.defaults.borderColor = '#333333';
    const labels = cfg.labels || [];
    const colors = getChartColors(labels);
    return new Chart(ctx, {
        type: cfg.type || cfg.chart_type || 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: cfg.title || 'Metric',
                data: cfg.values || [],
                backgroundColor: colors.map(c => c + '66'),
                borderColor: colors,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: { display: true, text: cfg.title || '', color: '#e0e0e0', font: { size: 14, family: 'monospace' } },
                legend: { labels: { font: { family: 'monospace' } } }
            },
            scales: {
                x: { ticks: { font: { family: 'monospace' } } },
                y: { ticks: { font: { family: 'monospace' } } }
            }
        }
    });
}

function getExistingChartTitles() {
    const titles = [];
    document.querySelectorAll('canvas').forEach(c => {
        const chart = Chart.getChart(c);
        if (chart) {
            const t = chart.options?.plugins?.title?.text;
            if (t) titles.push(t);
        }
    });
    return titles;
}
