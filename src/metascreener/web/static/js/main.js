/**
 * MetaScreener 2.0 — Shared Utilities
 * Used across all pages via base.html
 */

const API = '/api';

/* ── HTTP helpers ─────────────────────────────────────────── */

async function apiGet(path) {
    const res = await fetch(API + path);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

async function apiPost(path, data = {}) {
    const res = await fetch(API + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

async function apiPut(path, data = {}) {
    const res = await fetch(API + path, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

async function apiUpload(path, formData) {
    const res = await fetch(API + path, { method: 'POST', body: formData });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

/* ── Alert messages ──────────────────────────────────────── */

function showAlert(msg, type = 'danger') {
    const container = document.getElementById('alert-container');
    if (!container) return;
    const div = document.createElement('div');
    div.className = `alert alert-${type} alert-dismissible fade show shadow-sm`;
    div.setAttribute('role', 'alert');
    div.innerHTML = `${escapeHtml(msg)}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
    container.appendChild(div);
    // Auto-dismiss after 6 s
    setTimeout(() => {
        div.classList.remove('show');
        setTimeout(() => div.remove(), 300);
    }, 6000);
}

/* ── Button spinner helpers ──────────────────────────────── */

function btnLoading(btn, loadingText) {
    btn._origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${escapeHtml(loadingText)}`;
}

function btnReset(btn) {
    btn.disabled = false;
    btn.innerHTML = btn._origText || btn.innerHTML;
}

/* ── Misc helpers ────────────────────────────────────────── */

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function decisionBadge(decision) {
    const map = {
        INCLUDE:      ['badge-include', 'INCLUDE'],
        EXCLUDE:      ['badge-exclude', 'EXCLUDE'],
        HUMAN_REVIEW: ['badge-review',  'REVIEW'],
    };
    const [cls, label] = map[decision] || ['badge-unclear', decision];
    return `<span class="${cls}">${label}</span>`;
}

function fmtScore(v) {
    return v != null ? Number(v).toFixed(3) : '—';
}

function downloadBlob(content, filename, mime = 'text/plain') {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

function tableToCSV(tableEl) {
    const rows = [...tableEl.querySelectorAll('tr')];
    return rows.map(row => {
        const cells = [...row.querySelectorAll('th,td')];
        return cells.map(c => `"${c.innerText.replace(/"/g, '""')}"`).join(',');
    }).join('\n');
}
