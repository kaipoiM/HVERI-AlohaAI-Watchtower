/**
 * AlohaAI Emergency Watchtower — Frontend App
 * Connects to FastAPI backend via SSE for real-time streaming.
 */

// ── DOM References ─────────────────────────────────────────────────────────
const generateBtn   = document.getElementById('generate-btn');
const saveBtn       = document.getElementById('save-btn');
const clearBtn      = document.getElementById('clear-btn');
const fbUrlInput    = document.getElementById('fb-url');
const statusValue   = document.getElementById('status-value');
const statusDot     = document.getElementById('status-dot');
const commentCount  = document.getElementById('comment-count');
const elapsedPill   = document.getElementById('elapsed-pill');
const elapsedTime   = document.getElementById('elapsed-time');
const logContent    = document.getElementById('log-content');
const logPulse      = document.getElementById('log-pulse');
const reportContent = document.getElementById('report-content');
const reportTs      = document.getElementById('report-timestamp');
const modalOverlay  = document.getElementById('modal-overlay');
const modalHeader   = document.getElementById('modal-header');
const modalTitle    = document.getElementById('modal-title');
const modalBody     = document.getElementById('modal-body');
const modalClose    = document.getElementById('modal-close');

// ── State ──────────────────────────────────────────────────────────────────
let currentReport = null;
let sseController  = null; // AbortController for the fetch stream
let startTime      = null;
let elapsedTimer   = null;

// ── Clock ──────────────────────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    const hst = new Date(now.toLocaleString('en-US', { timeZone: 'Pacific/Honolulu' }));
    const h   = String(hst.getHours()).padStart(2, '0');
    const m   = String(hst.getMinutes()).padStart(2, '0');
    const s   = String(hst.getSeconds()).padStart(2, '0');
    document.getElementById('live-clock').textContent = `${h}:${m}:${s} HST`;
}
setInterval(updateClock, 1000);
updateClock();

// ── Timestamp Helper ───────────────────────────────────────────────────────
function ts() {
    const now = new Date();
    return now.toLocaleTimeString('en-US', { hour12: false });
}

// ── Log ────────────────────────────────────────────────────────────────────
function addLog(message, level = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry log-${level}`;
    entry.dataset.ts = `[${ts()}]`;
    entry.textContent = message;
    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;
}

function clearLog() {
    logContent.innerHTML = '';
}

// ── Status ─────────────────────────────────────────────────────────────────
function setStatus(text, state) {
    // state: 'ready' | 'processing' | 'complete' | 'error'
    statusValue.textContent = text;
    statusValue.className = `status-value status-${state}`;
    statusDot.className   = `status-dot dot-${state}`;
    logPulse.classList.toggle('active', state === 'processing');
}

// ── Elapsed Timer ──────────────────────────────────────────────────────────
function startElapsed() {
    startTime = Date.now();
    elapsedPill.style.display = '';
    elapsedTimer = setInterval(() => {
        const s = Math.floor((Date.now() - startTime) / 1000);
        elapsedTime.textContent = `${s}s`;
    }, 1000);
}

function stopElapsed() {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
}

// ── Markdown → HTML (basic) ───────────────────────────────────────────────
function markdownToHtml(md) {
    let html = md
        // Escape HTML entities first
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        // Headers
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm,  '<h2>$1</h2>')
        .replace(/^# (.+)$/gm,   '<h1>$1</h1>')
        // Bold
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // Italic
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        // Bullet lists
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/^• (.+)$/gm, '<li>$1</li>')
        // Horizontal rule
        .replace(/^---+$/gm, '<hr>')
        // Paragraphs: blank lines become <br> spacing
        .replace(/\n\n/g, '</p><p>')
        // Wrap dangling li elements in ul
        .replace(/(<li>.*<\/li>)\n*/gs, '<ul>$1</ul>');

    // Wrap in a <p> block
    html = `<p>${html}</p>`;

    // Highlight urgent keywords
    const urgentWords = /\b(URGENT|MANDATORY EVACUATION|EVACUATE|EVACUATIONS|COMPLETELY CLOSED|CLOSED|FATALITIES?|CRITICAL|EMERGENCY|IMMEDIATE)\b/gi;
    html = html.replace(urgentWords, '<span class="urgent-kw">$1</span>');

    return html;
}

// ── Render Report ──────────────────────────────────────────────────────────
function renderReport(markdown) {
    const body = document.createElement('div');
    body.className = 'report-body';
    body.innerHTML = markdownToHtml(markdown);
    reportContent.innerHTML = '';
    reportContent.appendChild(body);
    reportTs.textContent = new Date().toLocaleString('en-US', {
        timeZone: 'Pacific/Honolulu',
        dateStyle: 'medium',
        timeStyle: 'short',
    }) + ' HST';
}

// ── Modal ──────────────────────────────────────────────────────────────────
function showModal(title, message, type = 'info') {
    modalTitle.textContent = title;
    modalBody.textContent  = message;
    modalHeader.className  = `modal-header ${type}`;
    modalOverlay.classList.add('active');
}

function hideModal() {
    modalOverlay.classList.remove('active');
}

modalClose.addEventListener('click', hideModal);
modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) hideModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideModal(); });

// ── Generate Report ────────────────────────────────────────────────────────
generateBtn.addEventListener('click', async () => {
    const url = fbUrlInput.value.trim();
    if (!url) {
        showModal('Missing URL', 'Please enter a Facebook post URL.', 'error');
        return;
    }

    // Reset UI
    clearLog();
    currentReport = null;
    saveBtn.disabled = true;
    generateBtn.disabled = true;
    commentCount.textContent = '—';
    reportContent.innerHTML = '<div class="placeholder-text"><div class="placeholder-icon">⏳</div><div>Generating report…</div></div>';
    reportTs.textContent = '';

    setStatus('Connecting…', 'processing');
    startElapsed();

    // Abort any previous stream
    if (sseController) sseController.abort();
    sseController = new AbortController();

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
            signal: sseController.signal,
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status} ${response.statusText}`);
        }

        const reader   = response.body.getReader();
        const decoder  = new TextDecoder();
        let   buffer   = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Process complete SSE events (terminated by \n\n)
            const parts = buffer.split('\n\n');
            buffer = parts.pop(); // keep the incomplete tail

            for (const part of parts) {
                const line = part.trim();
                if (!line.startsWith('data:')) continue;

                let event;
                try {
                    event = JSON.parse(line.slice(5).trim());
                } catch {
                    continue;
                }

                handleEvent(event);
            }
        }

    } catch (err) {
        if (err.name === 'AbortError') return; // user cancelled
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
            if (event.count != null) commentCount.textContent = event.count.toLocaleString();
            break;

        case 'report':
            currentReport = event.content;
            if (event.count != null) commentCount.textContent = event.count.toLocaleString();
            renderReport(currentReport);
            saveBtn.disabled = false;
            addLog('Report generated successfully', 'success');
            setStatus('Complete', 'complete');
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
    // Abort any running stream
    if (sseController) {
        sseController.abort();
        sseController = null;
    }
    stopElapsed();

    fbUrlInput.value = '';
    currentReport    = null;
    saveBtn.disabled = true;
    commentCount.textContent = '—';
    elapsedTime.textContent  = '0s';
    elapsedPill.style.display = 'none';

    setStatus('Ready', 'ready');
    clearLog();
    addLog('Interface cleared — ready for new analysis.', 'info');

    reportContent.innerHTML = `
        <div class="placeholder-text">
            <div class="placeholder-icon">🏝</div>
            <div>Awaiting analysis</div>
            <div class="placeholder-sub">Enter a Facebook post URL above and click Generate Report</div>
        </div>`;
    reportTs.textContent = '';
});

// ── Key shortcut: Enter to generate ───────────────────────────────────────
fbUrlInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !generateBtn.disabled) generateBtn.click();
});
