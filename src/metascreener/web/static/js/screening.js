/**
 * MetaScreener 2.0 — Screening Page
 */

let sessionId      = null;
let criteriaMode   = 'topic';
let pollTimer      = null;
let rawResults     = [];

/* ── Drag-and-drop ───────────────────────────────────────── */
const zone    = document.getElementById('upload-zone');
const fileInp = document.getElementById('file-input');

zone.addEventListener('dragover',  e => { e.preventDefault(); zone.classList.add('drag-over'); });
zone.addEventListener('dragleave', ()  => zone.classList.remove('drag-over'));
zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
        fileInp.files = e.dataTransfer.files;
        onFileSelected();
    }
});

fileInp.addEventListener('change', onFileSelected);

function onFileSelected() {
    const f = fileInp.files[0];
    if (!f) return;
    document.getElementById('filename-display').textContent = f.name;
    document.getElementById('upload-btn').disabled = false;
}

/* ── Step 1: Upload ──────────────────────────────────────── */
document.getElementById('upload-btn').addEventListener('click', async () => {
    const f = fileInp.files[0];
    if (!f) { showAlert('Please select a file first.', 'warning'); return; }
    const btn = document.getElementById('upload-btn');
    btnLoading(btn, 'Uploading…');
    try {
        const fd = new FormData();
        fd.append('file', f);
        const data = await apiUpload('/screening/upload', fd);
        sessionId = data.session_id;
        document.getElementById('record-count').textContent = data.record_count;
        document.getElementById('upload-result').classList.remove('d-none');
        setStep(2);
    } catch (e) {
        showAlert('Upload failed: ' + e.message);
    } finally {
        btnReset(btn);
    }
});

/* ── Step 2: Criteria ────────────────────────────────────── */
function switchCriteriaTab(tab, btn) {
    criteriaMode = tab;
    // Reset all pills
    document.querySelectorAll('#criteria-tabs .nav-link').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Show/hide panels
    ['topic', 'upload', 'manual'].forEach(t => {
        document.getElementById('tab-' + t).style.display = t === tab ? '' : 'none';
    });
}

// YAML file → textarea
document.getElementById('yaml-file').addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    document.getElementById('yaml-text').value = await f.text();
});

document.getElementById('criteria-btn').addEventListener('click', async () => {
    if (!sessionId) { showAlert('Upload a file first.', 'warning'); return; }
    const btn = document.getElementById('criteria-btn');
    btnLoading(btn, 'Applying…');
    try {
        let payload;
        if (criteriaMode === 'topic') {
            const text = document.getElementById('topic-text').value.trim();
            if (!text) { showAlert('Please enter a topic.', 'warning'); btnReset(btn); return; }
            payload = { mode: 'topic', text };
        } else if (criteriaMode === 'upload') {
            const yaml_text = document.getElementById('yaml-text').value.trim();
            if (!yaml_text) { showAlert('Please enter or upload YAML criteria.', 'warning'); btnReset(btn); return; }
            payload = { mode: 'upload', yaml_text };
        } else {
            const json_text = document.getElementById('manual-json').value.trim();
            if (!json_text) { showAlert('Please enter JSON criteria.', 'warning'); btnReset(btn); return; }
            payload = { mode: 'manual', json_text };
        }
        await apiPost('/screening/criteria/' + sessionId, payload);
        document.getElementById('run-record-count').textContent =
            document.getElementById('record-count').textContent;
        setStep(3);
    } catch (e) {
        showAlert('Could not set criteria: ' + e.message);
    } finally {
        btnReset(btn);
    }
});

/* ── Step 3: Run ─────────────────────────────────────────── */
document.getElementById('run-btn').addEventListener('click', async () => {
    if (!sessionId) return;
    const btn = document.getElementById('run-btn');
    btnLoading(btn, 'Screening…');
    document.getElementById('run-progress').classList.remove('d-none');
    updateStatus('Sending request…', 5);
    try {
        await apiPost('/screening/run/' + sessionId, { session_id: sessionId, seed: 42 });
        updateStatus('Processing with HCN…', 20);
        startPolling();
    } catch (e) {
        showAlert('Screening failed: ' + e.message);
        btnReset(btn);
        document.getElementById('run-progress').classList.add('d-none');
    }
});

function startPolling() {
    pollTimer = setInterval(async () => {
        try {
            const data = await apiGet('/screening/results/' + sessionId);
            const total     = data.total     || 0;
            const completed = data.completed || 0;
            const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
            updateStatus(`Processed ${completed} / ${total} records`, pct);
            addLog(`${completed}/${total} records processed`);
            if (completed >= total && total > 0) {
                clearInterval(pollTimer);
                rawResults = data.results || [];
                renderResults(rawResults);
                setStep(4);
                document.getElementById('run-btn').disabled = false;
                document.getElementById('run-btn').innerHTML =
                    '<i class="bi bi-play-fill me-1"></i>Start Screening';
            }
        } catch (e) {
            // keep polling
        }
    }, 2000);
}

function updateStatus(msg, pct) {
    document.getElementById('run-status').textContent = msg;
    document.getElementById('run-progress-bar').style.width = pct + '%';
}

function addLog(msg) {
    const log = document.getElementById('progress-log');
    const div = document.createElement('div');
    div.textContent = new Date().toLocaleTimeString() + ' — ' + msg;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
}

/* ── Step 4: Results ─────────────────────────────────────── */
function renderResults(results) {
    const included = results.filter(r => r.decision === 'INCLUDE').length;
    const excluded = results.filter(r => r.decision === 'EXCLUDE').length;
    const review   = results.filter(r => r.decision === 'HUMAN_REVIEW').length;

    document.getElementById('results-summary').innerHTML = `
        <div class="col-3"><div class="metric-card">
            <div class="metric-value">${results.length}</div>
            <div class="metric-label">Total</div>
        </div></div>
        <div class="col-3"><div class="metric-card" style="border-color:#28a745;">
            <div class="metric-value text-success">${included}</div>
            <div class="metric-label">Include</div>
        </div></div>
        <div class="col-3"><div class="metric-card" style="border-color:#dc3545;">
            <div class="metric-value text-danger">${excluded}</div>
            <div class="metric-label">Exclude</div>
        </div></div>
        <div class="col-3"><div class="metric-card" style="border-color:#ffc107;">
            <div class="metric-value text-warning">${review}</div>
            <div class="metric-label">Review</div>
        </div></div>`;

    const tbody = document.getElementById('results-tbody');
    tbody.innerHTML = results.map((r, i) => `
        <tr>
            <td class="text-muted">${i + 1}</td>
            <td>${escapeHtml(r.title || '(no title)')}</td>
            <td>${decisionBadge(r.decision)}</td>
            <td><span class="badge bg-secondary">T${r.tier ?? '?'}</span></td>
            <td>${fmtScore(r.score)}</td>
            <td>${fmtScore(r.confidence)}</td>
        </tr>`).join('');
}

function exportResults(fmt) {
    if (!rawResults.length) { showAlert('No results to export.', 'warning'); return; }
    if (fmt === 'json') {
        downloadBlob(JSON.stringify(rawResults, null, 2), 'screening_results.json', 'application/json');
    } else {
        const table = document.getElementById('results-table');
        downloadBlob(tableToCSV(table), 'screening_results.csv', 'text/csv');
    }
}

function resetScreening() {
    sessionId = null;
    rawResults = [];
    clearInterval(pollTimer);
    // Reset form
    fileInp.value = '';
    document.getElementById('upload-result').classList.add('d-none');
    document.getElementById('upload-btn').disabled = true;
    document.getElementById('topic-text').value = '';
    document.getElementById('run-progress').classList.add('d-none');
    document.getElementById('progress-log').innerHTML = '';
    document.getElementById('results-tbody').innerHTML = '';
    setStep(1);
}

/* ── Step navigation ─────────────────────────────────────── */
function setStep(n) {
    [1, 2, 3, 4].forEach(i => {
        const card   = document.getElementById('step' + i);
        const circle = document.getElementById('s' + i + '-circle');
        const label  = document.getElementById('s' + i + '-label');
        if (i < n) {
            card.style.display = '';
            circle.className = 'step-circle done';
            circle.innerHTML = '<i class="bi bi-check"></i>';
            label.className  = 'step-label done';
        } else if (i === n) {
            card.style.display = '';
            circle.className = 'step-circle active';
            circle.textContent = i;
            label.className  = 'step-label active';
        } else {
            card.style.display = 'none';
            circle.className = 'step-circle';
            circle.textContent = i;
            label.className  = 'step-label';
        }
        if (i < 4) {
            const line = document.getElementById('line-' + i + (i + 1));
            if (line) line.className = 'step-line' + (i < n ? ' done' : '');
        }
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
