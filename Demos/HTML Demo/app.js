/**
 * AlohaAI Emergency Watchtower - Interactive Demo
 * JavaScript for button clicks, popups, and state transitions
 */

// DOM Elements
const generateBtn = document.getElementById('generate-btn');
const saveBtn = document.getElementById('save-btn');
const clearBtn = document.getElementById('clear-btn');
const statusValue = document.getElementById('status-value');
const commentCount = document.getElementById('comment-count');
const logContent = document.getElementById('log-content');
const reportText = document.getElementById('report-text');
const modalOverlay = document.getElementById('modal-overlay');
const modal = document.getElementById('modal');
const modalHeader = document.getElementById('modal-header');
const modalTitle = document.getElementById('modal-title');
const modalBody = document.getElementById('modal-body');
const modalClose = document.getElementById('modal-close');

// Sample report content
const sampleReportHTML = `
    <p class="report-title"><strong>HAWAII COUNTY CIVIL DEFENSE - EMERGENCY UPDATE</strong></p>
    <p class="report-date"><em>December 17, 2025 - 11:30 PM HST</em></p>

    <p>We are currently responding to three active emergency situations across Hawaii Island affecting thousands of residents.</p>

    <p class="section-header"><strong>ACTIVE INCIDENTS:</strong></p>

    <div class="incident">
        <p class="incident-title">🔥 <strong>SOUTH KOHALA - Waikoloa Fire</strong></p>
        <ul>
            <li>Large brush fire (~400 acres) spreading rapidly due to high winds</li>
            <li><span class="urgent">MANDATORY EVACUATIONS</span> in progress for Waikoloa Village</li>
            <li>Fire threatening multiple residential areas and spreading toward Puako</li>
            <li>Red Cross shelter open for evacuees</li>
            <li>Air quality advisory in effect - avoid outdoor activities</li>
        </ul>
    </div>

    <div class="incident">
        <p class="incident-title">🚨 <strong>SOUTH HILO - Highway 19 Fatal Accident</strong></p>
        <ul>
            <li>Highway 19 <span class="urgent">COMPLETELY CLOSED</span> between Honomu and Laupahoehoe</li>
            <li>Two fatalities confirmed, multiple injuries</li>
            <li>Multi-vehicle collision involving tour bus</li>
            <li>Road closure indefinite - use Highway 130 or Waimea detour</li>
        </ul>
    </div>

    <div class="incident">
        <p class="incident-title">⚡ <strong>PUNA DISTRICT - Widespread Power Outage</strong></p>
        <ul>
            <li>Over 2,000 homes without power since 2:00 PM</li>
            <li>All traffic lights out - exercise extreme caution</li>
            <li>HELCO crews working on equipment failure repairs</li>
            <li>Estimated restoration: several more hours</li>
        </ul>
    </div>

    <p class="safety-reminder"><strong>IMMEDIATE SAFETY REMINDER:</strong> If you're in an evacuation zone, leave NOW. Do not delay for belongings.</p>

    <p>Monitor our page and local media for updates. Report emergencies to 911 immediately.</p>

    <p class="sign-off"><em>Stay safe, Hawaii Island.</em></p>
`;

// Utility: Get current timestamp
function getTimestamp() {
    const now = new Date();
    return now.toLocaleTimeString('en-US', { hour12: false });
}

// Utility: Add log entry
function addLogEntry(message, type = '') {
    const entry = document.createElement('div');
    entry.className = 'log-entry' + (type ? ' ' + type : '');
    entry.textContent = `[${getTimestamp()}] ${message}`;
    logContent.appendChild(entry);
    logContent.scrollTop = logContent.scrollHeight;
}

// Utility: Clear log
function clearLog() {
    logContent.innerHTML = '';
}

// Utility: Update status
function updateStatus(text, className) {
    statusValue.textContent = text;
    statusValue.className = 'status-value ' + className;
}

// Modal functions
function showModal(title, message, type = 'info') {
    modalTitle.textContent = title;
    modalBody.textContent = message;
    modalHeader.className = 'modal-header ' + type;
    modalOverlay.classList.add('active');
}

function hideModal() {
    modalOverlay.classList.remove('active');
}

// Close modal on X button click
modalClose.addEventListener('click', hideModal);

// Close modal on overlay click (outside modal)
modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) {
        hideModal();
    }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalOverlay.classList.contains('active')) {
        hideModal();
    }
});

// Generate Report button
generateBtn.addEventListener('click', async () => {
    // Disable button during processing
    generateBtn.disabled = true;
    saveBtn.disabled = true;

    // Clear previous log entries for this run
    clearLog();

    // Processing sequence
    const steps = [
        { message: 'Extracting post ID...', delay: 800 },
        { message: 'Connecting to Facebook API...', delay: 1000 },
        { message: 'Scraping comments (247 found)...', delay: 1500 },
        { message: 'Processing comment data...', delay: 800 },
        { message: 'Analyzing with AI...', delay: 2000 },
        { message: 'Generating emergency report...', delay: 1000 }
    ];

    addLogEntry('Report generation started');
    updateStatus('Processing...', 'status-processing');

    // Execute steps sequentially
    for (const step of steps) {
        await new Promise(resolve => setTimeout(resolve, step.delay));
        addLogEntry(step.message, 'processing');
        updateStatus(step.message.replace('...', ''), 'status-processing');
    }

    // Complete
    await new Promise(resolve => setTimeout(resolve, 500));
    addLogEntry('Report generated successfully', 'success');
    updateStatus('Complete', 'status-complete');
    commentCount.textContent = '247';

    // Display the report
    reportText.innerHTML = sampleReportHTML;

    // Re-enable buttons
    generateBtn.disabled = false;
    saveBtn.disabled = false;
});

// Save Report button
saveBtn.addEventListener('click', () => {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15);
    const filename = `emergency_report_${timestamp}.txt`;
    showModal('Report Saved', `Report saved to:\nwatchtower_reports/${filename}`, 'success');
    addLogEntry(`Report saved: ${filename}`, 'success');
});

// Clear button
clearBtn.addEventListener('click', () => {
    // Reset report area
    reportText.innerHTML = '<p class="placeholder-text">Click "Generate Report" to analyze Facebook comments and generate an emergency report.</p>';

    // Reset status
    updateStatus('Ready', 'status-ready');
    commentCount.textContent = '0';

    // Clear log
    clearLog();
    addLogEntry('Interface cleared - ready for new analysis');

    // Disable save button
    saveBtn.disabled = true;
});

// Initialize: Ensure save button is enabled if report is pre-loaded
document.addEventListener('DOMContentLoaded', () => {
    // Check if there's report content (not placeholder)
    if (reportText.querySelector('.report-title')) {
        saveBtn.disabled = false;
    }
});
