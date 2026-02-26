/**
 * MetaScreener 2.0 — Evaluation Page
 */

let evalSessionId = null;
let charts = {};
let currentChart = 'roc';
let metricsData  = null;

/* ── Init ────────────────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', async () => {
    // Load existing screening sessions for dropdown
    try {
        const sessions = await apiGet('/screening/sessions');
        const sel = document.getElementById('session-select');
        sessions.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.session_id;
            opt.textContent = `${s.filename} (${s.total_records} records, ${s.session_id.slice(0,8)}…)`;
            sel.appendChild(opt);
        });
    } catch (_) { /* silent */ }
});

/* ── Label file upload ───────────────────────────────────── */
const labelZone = document.getElementById('label-zone');
const labelFile = document.getElementById('label-file');

labelZone.addEventListener('dragover',  e => { e.preventDefault(); labelZone.classList.add('drag-over'); });
labelZone.addEventListener('dragleave', ()  => labelZone.classList.remove('drag-over'));
labelZone.addEventListener('drop', e => {
    e.preventDefault();
    labelZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) { labelFile.files = e.dataTransfer.files; onLabelSelected(); }
});
labelFile.addEventListener('change', onLabelSelected);

async function onLabelSelected() {
    const f = labelFile.files[0];
    if (!f) return;
    const btn = document.getElementById('eval-btn');
    btnLoading(btn, 'Uploading…');
    try {
        const fd = new FormData();
        fd.append('file', f);
        const data = await apiUpload('/evaluation/upload-labels', fd);
        evalSessionId = data.session_id;
        document.getElementById('label-count').textContent    = data.gold_label_count ?? data.label_count ?? '?';
        document.getElementById('label-filename').textContent = f.name;
        document.getElementById('label-result').classList.remove('d-none');
        btn.disabled = false;
    } catch (e) {
        showAlert('Upload failed: ' + e.message);
    } finally {
        btnReset(btn);
    }
}

/* ── Run evaluation ──────────────────────────────────────── */
document.getElementById('eval-btn').addEventListener('click', async () => {
    if (!evalSessionId) { showAlert('Upload a label file first.', 'warning'); return; }
    const btn = document.getElementById('eval-btn');
    btnLoading(btn, 'Computing…');
    try {
        const screeningId = document.getElementById('session-select').value || undefined;
        const result = await apiPost('/evaluation/run/' + evalSessionId, {
            screening_session_id: screeningId || null,
            seed: 42,
        });
        metricsData = result;
        renderMetrics(result);
        renderCharts(result.charts);
        renderLancet(result.metrics);
        document.getElementById('metrics-section').style.display = '';
        window.scrollTo({ top: document.getElementById('metrics-section').offsetTop - 80, behavior: 'smooth' });
    } catch (e) {
        showAlert('Evaluation failed: ' + e.message);
    } finally {
        btnReset(btn);
    }
});

/* ── Metrics grid ────────────────────────────────────────── */
function renderMetrics(result) {
    const m = result.metrics;
    const fmt = v => v != null ? (v * 100).toFixed(1) + '%' : '—';
    const fmt2 = v => v != null ? Number(v).toFixed(3) : '—';
    const cards = [
        { label: 'Sensitivity',  value: fmt(m.sensitivity),  title: 'True positive rate (recall)' },
        { label: 'Specificity',  value: fmt(m.specificity),  title: 'True negative rate' },
        { label: 'F1 Score',     value: fmt(m.f1),           title: 'Harmonic mean of precision and recall' },
        { label: 'WSS@95',       value: fmt(m.wss_at_95),    title: 'Work saved over sampling at 95% recall' },
        { label: 'AUROC',        value: fmt2(m.auroc),       title: 'Area under the ROC curve' },
        { label: 'ECE',          value: fmt2(m.ece),         title: 'Expected calibration error (lower = better)' },
        { label: "Brier Score",  value: fmt2(m.brier),       title: 'Brier score (lower = better)' },
        { label: "Cohen's κ",    value: fmt2(m.kappa),       title: "Cohen's kappa inter-rater agreement" },
    ];
    document.getElementById('metrics-grid').innerHTML = cards.map(c => `
        <div class="col-6 col-sm-4 col-lg-3">
            <div class="metric-card" title="${escapeHtml(c.title)}">
                <div class="metric-value">${escapeHtml(c.value)}</div>
                <div class="metric-label">${escapeHtml(c.label)}</div>
            </div>
        </div>`).join('');
}

/* ── Charts ──────────────────────────────────────────────── */
function renderCharts(chartData) {
    if (!chartData) return;

    // Destroy old charts
    Object.values(charts).forEach(c => c.destroy());
    charts = {};

    // ROC curve
    if (chartData.roc?.length) {
        charts.roc = new Chart(document.getElementById('chart-roc'), {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'ROC',
                        data: chartData.roc.map(p => ({ x: p.fpr, y: p.tpr })),
                        borderColor: '#2563EB',
                        backgroundColor: 'rgba(37,99,235,0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 2,
                    },
                    {
                        label: 'Random',
                        data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
                        borderColor: '#9CA3AF',
                        borderDash: [6, 4],
                        pointRadius: 0,
                        fill: false,
                    }
                ]
            },
            options: rocOptions('False Positive Rate', 'True Positive Rate'),
        });
    }

    // Calibration
    if (chartData.calibration?.length) {
        charts.cal = new Chart(document.getElementById('chart-cal'), {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Model',
                        data: chartData.calibration.map(p => ({ x: p.predicted, y: p.actual })),
                        borderColor: '#2563EB',
                        backgroundColor: 'rgba(37,99,235,0.1)',
                        fill: false,
                        tension: 0.3,
                        pointRadius: 4,
                    },
                    {
                        label: 'Perfect',
                        data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
                        borderColor: '#9CA3AF',
                        borderDash: [6, 4],
                        pointRadius: 0,
                        fill: false,
                    }
                ]
            },
            options: rocOptions('Predicted Probability', 'Actual Probability'),
        });
    }

    // Score distribution
    if (chartData.distribution?.length) {
        charts.dist = new Chart(document.getElementById('chart-dist'), {
            type: 'bar',
            data: {
                labels: chartData.distribution.map(d => d.bin),
                datasets: [
                    {
                        label: 'Include',
                        data: chartData.distribution.map(d => d.include),
                        backgroundColor: 'rgba(40,167,69,0.7)',
                    },
                    {
                        label: 'Exclude',
                        data: chartData.distribution.map(d => d.exclude),
                        backgroundColor: 'rgba(220,53,69,0.7)',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top' } },
                scales: {
                    x: { stacked: true, title: { display: true, text: 'Score Bin' } },
                    y: { stacked: true, title: { display: true, text: 'Count' } },
                }
            },
        });
    }
}

function rocOptions(xLabel, yLabel) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        parsing: { xAxisKey: 'x', yAxisKey: 'y' },
        plugins: { legend: { position: 'top' } },
        scales: {
            x: { type: 'linear', min: 0, max: 1, title: { display: true, text: xLabel } },
            y: { type: 'linear', min: 0, max: 1, title: { display: true, text: yLabel } },
        },
    };
}

function switchChart(id, btn) {
    currentChart = id;
    document.querySelectorAll('#chart-tabs .nav-link').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    ['roc', 'cal', 'dist'].forEach(c => {
        document.getElementById('chart-' + c).style.display = c === id ? 'block' : 'none';
    });
}

function exportChart() {
    const canvas = document.getElementById('chart-' + currentChart);
    const link = document.createElement('a');
    link.download = `metascreener_${currentChart}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
}

/* ── Lancet format ───────────────────────────────────────── */
function renderLancet(m) {
    const dot = v => v != null ? (v * 100).toFixed(1).replace('.', '·') : '—';
    const dot3 = v => v != null ? Number(v).toFixed(3).replace('.', '·') : '—';
    document.getElementById('lancet-output').value =
        `Sensitivity ${dot(m.sensitivity)}%\n` +
        `Specificity ${dot(m.specificity)}%\n` +
        `F1 score ${dot(m.f1)}%\n` +
        `WSS@95 ${dot(m.wss_at_95)}%\n` +
        `AUROC ${dot3(m.auroc)}\n` +
        `ECE ${dot3(m.ece)}\n` +
        `Brier score ${dot3(m.brier)}\n` +
        `Cohen's κ ${dot3(m.kappa)}`;
}

function copyLancet() {
    const ta = document.getElementById('lancet-output');
    ta.select();
    navigator.clipboard.writeText(ta.value).then(() => {
        showAlert('Copied to clipboard.', 'success');
    });
}
