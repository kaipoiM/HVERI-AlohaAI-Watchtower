/**
 * AlohaAI Emergency Watchtower — Admin App
 * Connects to FastAPI backend via SSE for report generation.
 * Polls /api/submissions for citizen report moderation.
 */

// ── DOM References ─────────────────────────────────────────────────────────
const generateBtn     = document.getElementById('generate-btn');
const saveBtn         = document.getElementById('save-btn');
const clearBtn        = document.getElementById('clear-btn');
const statusValue     = document.getElementById('status-value');
const statusDot       = document.getElementById('status-dot');
const pendingCount    = document.getElementById('pending-count');
const totalCount      = document.getElementById('total-count');
const lastReportTime  = document.getElementById('last-report-time');
const elapsedPill     = document.getElementById('elapsed-pill');
const elapsedTime     = document.getElementById('elapsed-time');
const logContent      = document.getElementById('log-content');
const logPulse        = document.getElementById('log-pulse');
const reportContent   = document.getElementById('report-content');
const reportTs        = document.getElementById('report-timestamp');
const pendingBadge    = document.getElementById('pending-badge');
const submissionsList = document.getElementById('submissions-list');
const filterDistrict  = document.getElementById('filter-district');
const filterSeverity  = document.getElementById('filter-severity');
const refreshBtn      = document.getElementById('refresh-btn');
const modalOverlay    = document.getElementById('modal-overlay');
const modalHeader     = document.getElementById('modal-header');
const modalTitle      = document.getElementById('modal-title');
const modalBody       = document.getElementById('modal-body');
const modalClose      = document.getElementById('modal-close');

// ── Theme Toggle ───────────────────────────────────────────────────────────
const themeToggleBtn = document.getElementById('theme-toggle');

function applyTheme(theme) {
    if (theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        themeToggleBtn.textContent = '☀️ Light Mode';
        themeToggleBtn.title = 'Switch to light mode';
    } else {
        document.documentElement.removeAttribute('data-theme');
        themeToggleBtn.textContent = '🌙 Dark Mode';
        themeToggleBtn.title = 'Switch to dark mode';
    }
    localStorage.setItem('theme', theme);
}

const savedTheme = localStorage.getItem('theme');
const systemDark  = window.matchMedia('(prefers-color-scheme: dark)').matches;
applyTheme(savedTheme || (systemDark ? 'dark' : 'light'));
themeToggleBtn.addEventListener('click', () => {
    applyTheme(document.documentElement.hasAttribute('data-theme') ? 'light' : 'dark');
});

// ── Clock ──────────────────────────────────────────────────────────────────
function updateClock() {
    const hst = new Date(new Date().toLocaleString('en-US', { timeZone: 'Pacific/Honolulu' }));
    const pad = n => String(n).padStart(2, '0');
    document.getElementById('live-clock').textContent =
        `${pad(hst.getHours())}:${pad(hst.getMinutes())}:${pad(hst.getSeconds())} HST`;
}
setInterval(updateClock, 1000);
updateClock();

// ── Tab Switching ──────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        if (btn.dataset.tab === 'submissions') loadSubmissions();
    });
});

// ── State ──────────────────────────────────────────────────────────────────
let currentReport  = null;
let sseController  = null;
let startTime      = null;
let elapsedTimer   = null;
let allSubmissions = [];   // full cache for client-side filtering

// ── Helpers ────────────────────────────────────────────────────────────────
function ts() {
    return new Date().toLocaleTimeString('en-US', { hour12: false });
}

function addLog(message, level = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry log-${level}`;
    entry.dataset.ts = `[${ts()}]`;
    entry.textContent = message;
    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;
}

function clearLog() { logContent.innerHTML = ''; }

function setStatus(text, state) {
    statusValue.textContent = text;
    statusValue.className   = `status-value status-${state}`;
    statusDot.className     = `status-dot dot-${state}`;
    logPulse.classList.toggle('active', state === 'processing');
}

function startElapsed() {
    startTime = Date.now();
    elapsedPill.style.display = '';
    elapsedTimer = setInterval(() => {
        elapsedTime.textContent = Math.floor((Date.now() - startTime) / 1000) + 's';
    }, 1000);
}

function stopElapsed() {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
}

// ── Markdown renderer ──────────────────────────────────────────────────────
function markdownToHtml(md) {
    let html = md
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm,  '<h2>$1</h2>')
        .replace(/^# (.+)$/gm,   '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g,    '<em>$1</em>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/^• (.+)$/gm, '<li>$1</li>')
        .replace(/^---+$/gm, '<hr>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/(<li>.*<\/li>)\n*/gs, '<ul>$1</ul>');
    html = `<p>${html}</p>`;
    html = html.replace(
        /\b(URGENT|MANDATORY EVACUATION|EVACUATE|EVACUATIONS|COMPLETELY CLOSED|CLOSED|FATALITIES?|CRITICAL|EMERGENCY|IMMEDIATE)\b/gi,
        '<span class="urgent-kw">$1</span>'
    );
    return html;
}

function renderReport(markdown) {
    const body = document.createElement('div');
    body.className = 'report-body';
    body.innerHTML = markdownToHtml(markdown);
    reportContent.innerHTML = '';
    reportContent.appendChild(body);
    const now = new Date().toLocaleString('en-US', {
        timeZone: 'Pacific/Honolulu', dateStyle: 'medium', timeStyle: 'short'
    });
    reportTs.textContent = now + ' HST';
    lastReportTime.textContent = now;
}

// ── Modal ──────────────────────────────────────────────────────────────────
function showModal(title, message, type = 'info') {
    modalTitle.textContent = title;
    modalBody.textContent  = message;
    modalHeader.className  = `modal-header ${type}`;
    modalOverlay.classList.add('active');
}

function hideModal() { modalOverlay.classList.remove('active'); }

modalClose.addEventListener('click', hideModal);
modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) hideModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideModal(); });

// ── Fetch Submission Count (for status bar + badge) ────────────────────────
async function refreshCounts() {
    try {
        const res  = await fetch('/api/submissions/counts');
        if (!res.ok) return;
        const data = await res.json();

        const pending = data.pending ?? 0;
        const total   = data.total   ?? 0;

        pendingCount.textContent = pending.toLocaleString();
        totalCount.textContent   = total.toLocaleString();

        // Badge on the submissions tab
        if (pending > 0) {
            pendingBadge.textContent = pending > 99 ? '99+' : pending;
            pendingBadge.classList.remove('hidden');
        } else {
            pendingBadge.classList.add('hidden');
        }
    } catch {
        // Endpoint not wired yet — silently ignore
    }
}

// Poll counts every 30 seconds
refreshCounts();
setInterval(refreshCounts, 30000);

// ── Load Submissions ───────────────────────────────────────────────────────
async function loadSubmissions() {
    submissionsList.innerHTML = '<div class="submission-empty"><div class="submission-empty-icon">⏳</div><div>Loading…</div></div>';

    try {
        const res = await fetch('/api/submissions');
        if (!res.ok) throw new Error(`Server error ${res.status}`);
        const data = await res.json();
        allSubmissions = data.submissions ?? [];
    } catch (err) {
        allSubmissions = [];
        addLog('Could not load submissions — backend not yet connected.', 'info');
    }

    renderSubmissions();
    refreshCounts();
}

function renderSubmissions() {
    const district = filterDistrict.value;
    const severity = filterSeverity.value;

    const filtered = allSubmissions.filter(s => {
        if (district && s.district !== district) return false;
        if (severity && s.severity !== severity) return false;
        return true;
    });

    if (filtered.length === 0) {
        submissionsList.innerHTML = `
            <div class="submission-empty">
                <div class="submission-empty-icon">📋</div>
                <div>${allSubmissions.length === 0 ? 'No submissions yet' : 'No results match the current filters'}</div>
            </div>`;
        return;
    }

    submissionsList.innerHTML = '';
    filtered.forEach(sub => submissionsList.appendChild(buildSubCard(sub)));
}

function buildSubCard(sub) {
    const card = document.createElement('div');
    card.className = 'sub-card' + (sub.mod_status !== 'pending' ? ` ${sub.mod_status}` : '');
    card.dataset.id = sub.id;

    const typeLabels = {
        fire: '🔥 Fire/Smoke', flooding: '💧 Flooding', road: '🚧 Road Closure',
        power: '⚡ Power Outage', lava: '🌋 Lava', tsunami: '🌊 Tsunami',
        accident: '🚨 Accident', other: '📋 Other'
    };

    const evacLabels = {
        voluntary: 'Voluntary evac underway', mandatory: 'Mandatory evac in effect',
        sheltering: 'Sheltering in place', road_blocked: 'Evac routes blocked'
    };

    const timeAgo = formatTimeAgo(sub.timestamp);

    card.innerHTML = `
        <div class="sub-top">
            <span class="sub-type-badge">${typeLabels[sub.incident_type] || sub.incident_type}</span>
            <span class="sub-district">${sub.district}</span>
            ${sub.location ? `<span class="sub-location">— ${sub.location}</span>` : ''}
            <span class="sub-spacer"></span>
            <span class="sub-sev ${sub.severity}">${sub.severity}</span>
            <span class="sub-time">${timeAgo}</span>
        </div>
        <div class="sub-desc">${escHtml(sub.description)}</div>
        <div class="sub-meta">
            ${sub.evacuation ? `<span class="sub-evac">⚠ ${evacLabels[sub.evacuation] || sub.evacuation}</span>` : ''}
            ${sub.reporter_name ? `<span class="sub-reporter">👤 ${escHtml(sub.reporter_name)}</span>` : ''}
            <span class="sub-ref">${sub.ref_code}</span>
        </div>
        <div class="sub-actions">
            <button class="mod-btn" onclick="removeSubmission(${sub.id}, this)">✕ Remove</button>
        </div>`;

    return card;
}

// ── Remove Submission ──────────────────────────────────────────────────────
async function removeSubmission(id, btn) {
    btn.disabled = true;
    const card = document.querySelector(`.sub-card[data-id="${id}"]`);
    if (card) card.classList.add('deleted');

    try {
        await fetch(`/api/submissions/${id}`, { method: 'DELETE' });
    } catch {
        // Not yet wired — update local state only
    }

    setTimeout(() => {
        allSubmissions = allSubmissions.filter(s => s.id !== id);
        renderSubmissions();
        refreshCounts();
    }, 350);
}

// ── Filters ────────────────────────────────────────────────────────────────
filterDistrict.addEventListener('change', renderSubmissions);
filterSeverity.addEventListener('change', renderSubmissions);
refreshBtn.addEventListener('click', loadSubmissions);

// ── Generate Report ────────────────────────────────────────────────────────
generateBtn.addEventListener('click', async () => {
    clearLog();
    currentReport = null;
    saveBtn.disabled = true;
    generateBtn.disabled = true;
    reportContent.innerHTML = '<div class="placeholder-text"><div class="placeholder-icon">⏳</div><div>Generating report…</div></div>';
    reportTs.textContent = '';

    setStatus('Connecting…', 'processing');
    startElapsed();

    if (sseController) sseController.abort();
    sseController = new AbortController();

    // Switch to report tab
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelector('[data-tab="report"]').classList.add('active');
    document.getElementById('tab-report').classList.add('active');

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
            signal: sseController.signal,
        });

        if (!response.ok) throw new Error(`Server error: ${response.status} ${response.statusText}`);

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let   buffer  = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop();

            for (const part of parts) {
                const line = part.trim();
                if (!line.startsWith('data:')) continue;
                try {
                    handleEvent(JSON.parse(line.slice(5).trim()));
                } catch { /* ignore malformed */ }
            }
        }

    } catch (err) {
        if (err.name === 'AbortError') return;
        addLog(`Connection error: ${err.message}`, 'error');
        setStatus('Error', 'error');
        showModal('Connection Error', err.message, 'error');
    } finally {
        stopElapsed();
        generateBtn.disabled = false;
    }
});

// ── SSE Event Handler ──────────────────────────────────────────────────────
function handleEvent(event) {
    switch (event.type) {
        case 'log':
            addLog(event.message, event.level || 'info');
            setStatus(event.message.replace(/…$/, ''), 'processing');
            break;

        case 'status':
            setStatus(event.status, event.status === 'Complete' ? 'complete' : 'processing');
            if (event.pending != null) pendingCount.textContent = event.pending.toLocaleString();
            if (event.total   != null) totalCount.textContent   = event.total.toLocaleString();
            break;

        case 'report':
            currentReport = event.content;
            renderReport(currentReport);
            saveBtn.disabled = false;
            addLog('Report generated successfully', 'success');
            setStatus('Complete', 'complete');
            refreshCounts();
            break;

        case 'error':
            addLog(event.message, 'error');
            setStatus('Error', 'error');
            showModal('Error', event.message, 'error');
            generateBtn.disabled = false;
            stopElapsed();
            break;

        case 'done':
            generateBtn.disabled = false;
            stopElapsed();
            break;
    }
}

// ── Save Report ────────────────────────────────────────────────────────────
saveBtn.addEventListener('click', async () => {
    if (!currentReport) return;
    try {
        const res  = await fetch('/api/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: currentReport }),
        });
        if (!res.ok) throw new Error(`Save failed: ${res.status}`);
        const data = await res.json();
        addLog(`Report saved: ${data.filename}`, 'success');
        showModal('Report Saved', `Saved to server:\n${data.path}`, 'success');
    } catch (err) {
        showModal('Save Error', err.message, 'error');
    }
});

// ── Clear ──────────────────────────────────────────────────────────────────
clearBtn.addEventListener('click', () => {
    if (sseController) { sseController.abort(); sseController = null; }
    stopElapsed();

    currentReport = null;
    saveBtn.disabled = true;
    elapsedTime.textContent   = '0s';
    elapsedPill.style.display = 'none';

    setStatus('Ready', 'ready');
    clearLog();
    addLog('Interface cleared — ready for new analysis.', 'info');

    reportContent.innerHTML = `
        <div class="placeholder-text">
            <div class="placeholder-icon">🏝</div>
            <div>Awaiting analysis</div>
            <div class="placeholder-sub">Click Generate Report to process pending submissions</div>
        </div>`;
    reportTs.textContent = '';
});

// ── Utility Helpers ────────────────────────────────────────────────────────
function escHtml(str) {
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatTimeAgo(isoString) {
    if (!isoString) return '—';
    const diff = Math.floor((Date.now() - new Date(isoString)) / 1000);
    if (diff < 60)   return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400)return `${Math.floor(diff/3600)}h ago`;
    return new Date(isoString).toLocaleDateString('en-US', { month:'short', day:'numeric' });
}