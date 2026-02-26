/**
 * MetaScreener 2.0 — Quality / Risk of Bias Assessment Page
 */

let robSessionId  = null;
let selectedTool  = null;
let robResults    = [];

/* ── Step 1: Tool selection ──────────────────────────────── */
function selectTool(tool) {
    selectedTool = tool;
    // Highlight selected card
    ['rob2', 'robins_i', 'quadas2'].forEach(t => {
        const card = document.getElementById('card-' + t);
        card.style.borderColor = t === tool ? '#2563EB' : 'transparent';
    });
    document.getElementById('radio-' + tool).checked = true;
    document.getElementById('tool-btn').disabled = false;
}

document.getElementById('tool-btn').addEventListener('click', () => {
    if (!selectedTool) { showAlert('Select a tool first.', 'warning'); return; }
    document.getElementById('rob-info').textContent =
        `Ready: tool = ${selectedTool.toUpperCase().replace('_', '-')}`;
    qSetStep(2);
});

/* ── Step 2: PDF upload ──────────────────────────────────── */
const robZone  = document.getElementById('rob-pdf-zone');
const robFiles = document.getElementById('rob-pdf-files');

robZone.addEventListener('dragover',  e => { e.preventDefault(); robZone.classList.add('drag-over'); });
robZone.addEventListener('dragleave', ()  => robZone.classList.remove('drag-over'));
robZone.addEventListener('drop', e => {
    e.preventDefault();
    robZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) { robFiles.files = e.dataTransfer.files; onRobPdfsSelected(); }
});
robFiles.addEventListener('change', onRobPdfsSelected);

function onRobPdfsSelected() {
    document.getElementById('rob-upload-btn').disabled = robFiles.files.length === 0;
}

document.getElementById('rob-upload-btn').addEventListener('click', async () => {
    if (!robFiles.files.length) { showAlert('Select PDF files first.', 'warning'); return; }
    const btn = document.getElementById('rob-upload-btn');
    btnLoading(btn, 'Uploading…');
    try {
        const fd = new FormData();
        [...robFiles.files].forEach(f => fd.append('files', f));
        const data = await apiUpload('/quality/upload-pdfs', fd);
        robSessionId = data.session_id;
        document.getElementById('rob-pdf-count').textContent = data.pdf_count;
        document.getElementById('rob-pdf-result').classList.remove('d-none');
        qSetStep(3);
    } catch (e) {
        showAlert('Upload failed: ' + e.message);
    } finally {
        btnReset(btn);
    }
});

/* ── Step 3: Run assessment ──────────────────────────────── */
document.getElementById('rob-run-btn').addEventListener('click', async () => {
    if (!robSessionId || !selectedTool) { showAlert('Complete steps 1 and 2 first.', 'warning'); return; }
    const btn = document.getElementById('rob-run-btn');
    btnLoading(btn, 'Assessing…');
    document.getElementById('rob-progress').classList.remove('d-none');
    try {
        await apiPost('/quality/run/' + robSessionId + '?tool=' + selectedTool);
        const data = await apiGet('/quality/results/' + robSessionId);
        robResults = data.results || [];
        renderRoBResults(robResults, data.tool || selectedTool);
        document.getElementById('rob-results').style.display = '';
    } catch (e) {
        showAlert('Assessment failed: ' + e.message);
    } finally {
        btnReset(btn);
        document.getElementById('rob-progress').classList.add('d-none');
    }
});

/* ── Render traffic-light table ──────────────────────────── */
function renderRoBResults(results, tool) {
    if (!results.length) {
        document.getElementById('rob-result-title').textContent = 'No results';
        return;
    }

    // Collect all domain names
    const allDomains = [];
    results.forEach(r => {
        if (r.domains) {
            Object.keys(r.domains).forEach(d => {
                if (!allDomains.includes(d)) allDomains.push(d);
            });
        }
    });

    const fmtDomain = d => d.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

    // Header
    document.getElementById('rob-thead').innerHTML = `<tr>
        <th>#</th>
        <th>Paper</th>
        <th>Overall</th>
        ${allDomains.map(d => `<th title="${fmtDomain(d)}">${fmtDomain(d).slice(0,18)}${fmtDomain(d).length > 18 ? '…' : ''}</th>`).join('')}
    </tr>`;

    // Rows
    let html = '';
    results.forEach((r, i) => {
        const rowId = 'rob-detail-' + i;
        html += `<tr style="cursor:pointer;" onclick="toggleDetail(${i})">
            <td class="text-muted">${i + 1}</td>
            <td>${escapeHtml(r.record_id || '—')}</td>
            <td class="${robClass(r.overall)}">${fmtJudgement(r.overall)}</td>
            ${allDomains.map(d => {
                const dom = r.domains?.[d];
                return dom
                    ? `<td class="${robClass(dom.judgement)}" title="${escapeHtml(dom.rationale || '')}">${fmtJudgement(dom.judgement)}</td>`
                    : '<td class="text-muted text-center">—</td>';
            }).join('')}
        </tr>
        <tr id="${rowId}" class="rob-detail" style="display:none;">
            <td colspan="${allDomains.length + 3}">
                ${renderDomainDetail(r, allDomains)}
            </td>
        </tr>`;
    });
    document.getElementById('rob-tbody').innerHTML = html;

    document.getElementById('rob-result-title').textContent =
        `Risk of Bias Results — ${tool.toUpperCase().replace('_', '-')} (${results.length} papers)`;
}

function robClass(judgement) {
    if (!judgement) return '';
    const j = judgement.toLowerCase();
    if (j === 'low')                                   return 'rob-low';
    if (['some_concerns', 'moderate'].includes(j))    return 'rob-concerns';
    if (['high', 'serious', 'critical'].includes(j))  return 'rob-high';
    return 'rob-unclear';
}

function fmtJudgement(j) {
    if (!j) return '—';
    return j.replace(/_/g, ' ').toUpperCase();
}

function renderDomainDetail(r, domains) {
    if (!r.domains) return '<p class="p-2 text-muted small">No domain details.</p>';
    return `<div class="p-2">` +
        domains.filter(d => r.domains[d]).map(d => {
            const dom = r.domains[d];
            const fmtD = d.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            return `<div class="mb-2">
                <strong class="${robClass(dom.judgement)} px-2 py-1 rounded">${fmtD}:</strong>
                <span class="ms-1 small">${fmtJudgement(dom.judgement)}</span>
                ${dom.rationale ? `<p class="small text-muted mt-1 mb-0">${escapeHtml(dom.rationale)}</p>` : ''}
                ${dom.model_judgements ? `<p class="small text-muted mb-0">
                    Models: ${Object.entries(dom.model_judgements).map(([m, v]) =>
                        `<span class="badge bg-light text-dark border me-1">${escapeHtml(m)}: ${fmtJudgement(v)}</span>`
                    ).join('')}
                </p>` : ''}
            </div>`;
        }).join('') +
    `</div>`;
}

function toggleDetail(i) {
    const row = document.getElementById('rob-detail-' + i);
    row.style.display = row.style.display === 'none' ? '' : 'none';
}

/* ── Export ──────────────────────────────────────────────── */
function exportRoB(fmt) {
    if (!robResults.length) { showAlert('No results to export.', 'warning'); return; }
    if (fmt === 'json') {
        downloadBlob(JSON.stringify(robResults, null, 2), 'rob_results.json', 'application/json');
    } else {
        const table = document.getElementById('rob-table');
        downloadBlob(tableToCSV(table), 'rob_results.csv', 'text/csv');
    }
}

/* ── Step navigation ─────────────────────────────────────── */
function qSetStep(n) {
    [1, 2, 3].forEach(i => {
        const card   = document.getElementById('qstep' + i);
        const circle = document.getElementById('q' + i + '-circle');
        const label  = document.getElementById('q' + i + '-label');
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
        if (i < 3) {
            const line = document.getElementById('qline-' + i + (i + 1));
            if (line) line.className = 'step-line' + (i < n ? ' done' : '');
        }
    });
}
