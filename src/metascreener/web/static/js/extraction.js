/**
 * MetaScreener 2.0 — Data Extraction Page
 */

let extSessionId = null;
let extResults   = [];
let formFields   = [];

/* ── PDF upload ──────────────────────────────────────────── */
const pdfZone  = document.getElementById('pdf-zone');
const pdfFiles = document.getElementById('pdf-files');

pdfZone.addEventListener('dragover',  e => { e.preventDefault(); pdfZone.classList.add('drag-over'); });
pdfZone.addEventListener('dragleave', ()  => pdfZone.classList.remove('drag-over'));
pdfZone.addEventListener('drop', e => {
    e.preventDefault();
    pdfZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) { pdfFiles.files = e.dataTransfer.files; onPdfsSelected(); }
});
pdfFiles.addEventListener('change', onPdfsSelected);

function onPdfsSelected() {
    document.getElementById('pdf-upload-btn').disabled = pdfFiles.files.length === 0;
}

document.getElementById('pdf-upload-btn').addEventListener('click', async () => {
    if (!pdfFiles.files.length) { showAlert('Select PDF files first.', 'warning'); return; }
    const btn = document.getElementById('pdf-upload-btn');
    btnLoading(btn, 'Uploading…');
    try {
        const fd = new FormData();
        [...pdfFiles.files].forEach(f => fd.append('files', f));
        const data = await apiUpload('/extraction/upload-pdfs', fd);
        extSessionId = data.session_id;
        document.getElementById('pdf-count').textContent = data.pdf_count;
        document.getElementById('pdf-result').classList.remove('d-none');
        eSetStep(2);
    } catch (e) {
        showAlert('PDF upload failed: ' + e.message);
    } finally {
        btnReset(btn);
    }
});

/* ── Form upload ─────────────────────────────────────────── */
const formZone = document.getElementById('form-zone');
const formFile = document.getElementById('form-file');

formZone.addEventListener('dragover',  e => { e.preventDefault(); formZone.classList.add('drag-over'); });
formZone.addEventListener('dragleave', ()  => formZone.classList.remove('drag-over'));
formZone.addEventListener('drop', e => {
    e.preventDefault();
    formZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) { formFile.files = e.dataTransfer.files; onFormFileSelected(); }
});
formFile.addEventListener('change', onFormFileSelected);

async function onFormFileSelected() {
    const f = formFile.files[0];
    if (!f) return;
    document.getElementById('form-yaml').value = await f.text();
}

document.getElementById('form-upload-btn').addEventListener('click', async () => {
    if (!extSessionId) { showAlert('Upload PDFs first.', 'warning'); return; }
    const yamlText = document.getElementById('form-yaml').value.trim();
    if (!yamlText) { showAlert('Provide a YAML extraction form.', 'warning'); return; }
    const btn = document.getElementById('form-upload-btn');
    btnLoading(btn, 'Uploading form…');
    try {
        const blob = new Blob([yamlText], { type: 'text/yaml' });
        const fd = new FormData();
        fd.append('file', blob, 'form.yaml');
        await apiUpload('/extraction/upload-form/' + extSessionId, fd);
        document.getElementById('ext-info').textContent =
            `Ready: ${document.getElementById('pdf-count').textContent} PDFs · YAML form loaded`;
        eSetStep(3);
    } catch (e) {
        showAlert('Form upload failed: ' + e.message);
    } finally {
        btnReset(btn);
    }
});

/* ── Run extraction ──────────────────────────────────────── */
document.getElementById('extract-btn').addEventListener('click', async () => {
    if (!extSessionId) { showAlert('Complete steps 1 and 2 first.', 'warning'); return; }
    const btn = document.getElementById('extract-btn');
    btnLoading(btn, 'Extracting…');
    document.getElementById('ext-progress').classList.remove('d-none');
    try {
        await apiPost('/extraction/run/' + extSessionId);
        const data = await apiGet('/extraction/results/' + extSessionId);
        extResults = data.results || [];
        renderExtResults(extResults);
        document.getElementById('ext-results').style.display = '';
    } catch (e) {
        showAlert('Extraction failed: ' + e.message);
    } finally {
        btnReset(btn);
        document.getElementById('ext-progress').classList.add('d-none');
    }
});

/* ── Render results table ────────────────────────────────── */
function renderExtResults(results) {
    if (!results.length) {
        document.getElementById('ext-result-title').textContent = 'No results';
        return;
    }

    // Determine columns (skip private _ fields except _paper, _needs_review)
    const sample = results[0];
    const dataKeys = Object.keys(sample).filter(k => !k.startsWith('_'));
    formFields = dataKeys;

    // Header
    document.getElementById('ext-thead').innerHTML = `<tr>
        <th>#</th>
        <th>Paper</th>
        ${dataKeys.map(k => `<th>${escapeHtml(k)}</th>`).join('')}
        <th title="Consensus across models">✓</th>
    </tr>`;

    // Rows
    document.getElementById('ext-tbody').innerHTML = results.map((r, i) => {
        const consensusOk = !(r._needs_review);
        return `<tr>
            <td class="text-muted">${i + 1}</td>
            <td>${escapeHtml(r._paper || r._record_id || '—')}</td>
            ${dataKeys.map(k => `<td class="editable-cell" contenteditable="true">
                ${escapeHtml(r[k] != null ? String(r[k]) : '')}
            </td>`).join('')}
            <td class="text-center">
                ${consensusOk
                    ? '<i class="bi bi-check-circle text-success" title="All models agreed"></i>'
                    : '<i class="bi bi-exclamation-triangle text-warning" title="Discrepancy — review required"></i>'}
            </td>
        </tr>`;
    }).join('');

    document.getElementById('ext-result-title').textContent =
        `Extracted Data (${results.length} papers, ${dataKeys.length} fields)`;
}

/* ── Export ──────────────────────────────────────────────── */
function exportExtraction(fmt) {
    if (!extResults.length) { showAlert('No results to export.', 'warning'); return; }
    if (fmt === 'json') {
        downloadBlob(JSON.stringify(extResults, null, 2), 'extraction_results.json', 'application/json');
    } else {
        const table = document.getElementById('ext-table');
        downloadBlob(tableToCSV(table), 'extraction_results.csv', 'text/csv');
    }
}

/* ── Step navigation ─────────────────────────────────────── */
function eSetStep(n) {
    [1, 2, 3].forEach(i => {
        const card   = document.getElementById('estep' + i);
        const circle = document.getElementById('e' + i + '-circle');
        const label  = document.getElementById('e' + i + '-label');
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
            const line = document.getElementById('eline-' + i + (i + 1));
            if (line) line.className = 'step-line' + (i < n ? ' done' : '');
        }
    });
}
