// KSP CRIME AI — COMMAND CENTER JAVASCRIPT
// Handles API calls to /api/investigate, Vis.js Graph, Chart.js Trends, and Courtroom Audit Trail

let networkInstance = null;
let trendsChartInstance = null;
let fullTrendsChartInstance = null;
let hotspotShareChartInstance = null;

// ==========================================================================
// PANEL DRAG-TO-RESIZE LOGIC
// Lets the user drag the handle between AI Investigator and Intel panels.
// ==========================================================================
(function initPanelResize() {
    document.addEventListener('DOMContentLoaded', () => {
        const workspace = document.getElementById('workspace');
        const handle = document.getElementById('panel-resize-handle');
        if (!workspace || !handle) return;

        // Restore saved width from previous session safely
        const savedWidth = localStorage.getItem('chatPanelWidth');
        if (savedWidth) {
            const parsed = parseInt(savedWidth, 10);
            const minW = 280;
            const maxW = Math.floor(window.innerWidth * 0.65);
            if (!isNaN(parsed) && parsed >= minW && parsed <= maxW) {
                workspace.style.setProperty('--chat-panel-width', parsed + 'px');
            } else {
                localStorage.removeItem('chatPanelWidth');
            }
        }

        let isDragging = false;
        let startX = 0;
        let startWidth = 0;

        handle.addEventListener('mousedown', (e) => {
            isDragging = true;
            startX = e.clientX;
            const chatPanel = document.getElementById('chat-panel');
            startWidth = chatPanel ? chatPanel.getBoundingClientRect().width : 420;

            handle.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const delta = e.clientX - startX;
            const minWidth = 280;
            const maxWidth = Math.floor(window.innerWidth * 0.65);
            const newWidth = Math.min(maxWidth, Math.max(minWidth, startWidth + delta));
            workspace.style.setProperty('--chat-panel-width', newWidth + 'px');
        });

        document.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            handle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            const w = workspace.style.getPropertyValue('--chat-panel-width');
            if (w) localStorage.setItem('chatPanelWidth', w);
            if (networkInstance) networkInstance.redraw();
            if (trendsChartInstance) trendsChartInstance.resize();
        });

        window.addEventListener('resize', () => {
            if (networkInstance) networkInstance.redraw();
            if (trendsChartInstance) trendsChartInstance.resize();
        });
    });
})();



// 3. Trends Page Loader (`trends.html`)
function loadTrendsPageData() {
    // Clear any permanent legacy items from previous browser sessions
    localStorage.removeItem('latestCrimeData');
    let data = null;
    const stored = sessionStorage.getItem('latestCrimeData');

    if (stored) {
        try {
            data = JSON.parse(stored);
        } catch (e) {
            console.error("Failed to parse stored crime data:", e);
        }
    }

    // If no stored data or empty findings, initialize with clean empty structure
    if (!data || !data.trend_findings) {
        data = {
            trend_findings: [],
            hotspots: [],
            demographic_findings: []
        };
    }

    window.currentTrendsData = data;
    const findings = data.trend_findings || [];
    const hotspots = data.hotspots || [];

    // 1. Populate Executive KPI Ribbon & Filter Bar dynamically from live findings
    const totalCases = findings.reduce((sum, f) => sum + (f.case_count || 0), 0);
    const uniqueLocations = Array.from(new Set(findings.map(f => f.location || 'District').filter(Boolean)));
    const spikes = findings.filter(f => f.is_spike || (f.pct_change && f.pct_change >= 25));
    const topMoList = findings.flatMap(f => f.mo_patterns || []).filter(Boolean);
    const topMo = topMoList.length > 0 ? topMoList[0] : (findings.length > 0 ? "Standard Pattern" : "No Active MO");
    const topSpike = spikes.sort((a, b) => (b.pct_change || 0) - (a.pct_change || 0))[0];

    if (document.getElementById('kpi-total-volume')) {
        document.getElementById('kpi-total-volume').innerHTML = `${totalCases} <small>cases</small>`;
    }
    if (document.getElementById('kpi-volume-subtext')) {
        document.getElementById('kpi-volume-subtext').innerHTML = `<span class="kpi-dot cyan"></span>Across ${uniqueLocations.length} monitored jurisdictions`;
    }
    if (document.getElementById('kpi-critical-spikes')) {
        document.getElementById('kpi-critical-spikes').innerHTML = `${spikes.length} <small>districts</small>`;
    }
    if (document.getElementById('kpi-spikes-subtext')) {
        const spikeNames = Array.from(new Set(spikes.map(s => s.location).filter(Boolean)));
        const spikeText = spikeNames.length > 0 ? `${spikeNames.slice(0, 3).join(', ')} (+25% threshold)` : 'No critical spikes active';
        document.getElementById('kpi-spikes-subtext').innerHTML = `<span class="kpi-dot red"></span>${spikeText}`;
    }
    if (document.getElementById('kpi-top-mo')) {
        document.getElementById('kpi-top-mo').innerHTML = `"${topMo}"`;
    }
    if (document.getElementById('kpi-mo-subtext')) {
        const moSub = findings.length > 0 ? `Linked across ${findings.length} categories` : `No patterns extracted yet`;
        document.getElementById('kpi-mo-subtext').innerHTML = `<span class="kpi-dot amber"></span>${moSub}`;
    }
    if (document.getElementById('kpi-forecast')) {
        const forecastEl = document.getElementById('kpi-forecast');
        if (spikes.length > 0) {
            forecastEl.innerHTML = `HIGH ALERT`;
            forecastEl.style.color = `#fbbf24`;
        } else {
            forecastEl.innerHTML = `NORMAL`;
            forecastEl.style.color = `#34d399`;
        }
    }
    if (document.getElementById('kpi-forecast-subtext')) {
        const forecastSub = topSpike && topSpike.pct_change
            ? `+${topSpike.pct_change}% projected surge in ${topSpike.crime_type || 'Crime'}`
            : `Stable baseline across jurisdictions`;
        document.getElementById('kpi-forecast-subtext').innerHTML = `<span class="kpi-dot ${spikes.length > 0 ? 'amber' : 'green'}"></span>${forecastSub}`;
    }

    // Dynamic Jurisdiction Filter Bar
    const filterPillsContainer = document.getElementById('trends-filter-pills');
    if (filterPillsContainer) {
        let pillsHTML = `<button class="pill active" onclick="filterTrendsByJurisdiction('all', this)">All Districts (${uniqueLocations.length})</button>`;
        uniqueLocations.forEach(loc => {
            const isLocSpike = spikes.some(s => (s.location || '').toLowerCase() === loc.toLowerCase());
            pillsHTML += `<button class="pill" onclick="filterTrendsByJurisdiction('${loc.replace(/'/g, "\\'")}', this)">${loc} ${isLocSpike ? '<span class="badge-mini red">Spike</span>' : ''}</button>`;
        });
        filterPillsContainer.innerHTML = pillsHTML;
    }

    // 2. Render Dossier Cards immediately
    renderTrendsDossiers(findings);

    // 3 & 4. Render Charts safely inside requestAnimationFrame once canvas dimensions are computed by browser
    requestAnimationFrame(() => {
        renderTrendsBarLineChart(findings);
        renderHotspotShareChart(hotspots);
    });
}

function renderTrendsDossiers(findings) {
    const alertsContainer = document.getElementById('full-trends-alerts');
    const countLabel = document.getElementById('dossier-count-label');
    if (countLabel) {
        countLabel.innerText = `Showing ${findings.length} monitored category dossiers`;
    }
    if (!alertsContainer) return;
    alertsContainer.innerHTML = '';

    if (findings.length === 0) {
        alertsContainer.innerHTML = `
            <div class="alert-card" style="background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.3);">
                <h4 style="color: var(--status-low); display: flex; align-items: center;"><span style="display:inline-block; width:8px; height:8px; background:#10b981; border-radius:50%; margin-right:8px;"></span>Normal Baseline Volume — No Spikes Flagged</h4>
                <p>All crime categories across monitored jurisdictions remain stable relative to 3-period rolling averages.</p>
            </div>
        `;
        return;
    }

    findings.forEach(f => {
        const isSpike = f.is_spike || (f.pct_change && f.pct_change >= 25);
        const cardClass = isSpike ? 'dossier-card spike-active' : 'dossier-card baseline-stable';
        const dotColor = isSpike ? '#f87171' : '#34d399';
        const statusText = isSpike ? `CRITICAL SURGE (+${f.pct_change ?? '25+'}% vs baseline)` : `STABLE BASELINE (${f.trend_direction || 'Stable'})`;
        const badgeStyle = isSpike ? 'background: rgba(248, 113, 113, 0.15); border: 1px solid #ef4444; color: #fca5a5;' : 'background: rgba(16, 185, 129, 0.15); border: 1px solid #059669; color: #34d399;';

        // Gauge bar percentage
        const caseCount = f.case_count ?? 0;
        const rollingAvg = f.rolling_avg ?? caseCount;
        const maxScale = Math.max(caseCount, rollingAvg, 1) * 1.3;
        const currentBarWidth = Math.min(Math.round((caseCount / maxScale) * 100), 100);
        const baselineBarWidth = Math.min(Math.round((rollingAvg / maxScale) * 100), 100);

        const moList = (f.mo_patterns || []).length > 0
            ? (f.mo_patterns || []).map(mo => `<span class="mo-pill">${mo}</span>`).join(' ')
            : '<span class="mo-pill">Standard Historical Pattern</span>';

        const tacticalRecommendation = isSpike
            ? `Immediate tactical alert: Deploy night patrol checkpoints around high-risk zones in ${f.location} and inspect linked repeat offenders.`
            : `Routine baseline monitoring: Continue periodic surveillance of ${f.crime_type} networks across ${f.location}.`;

        alertsContainer.innerHTML += `
            <div class="${cardClass}">
                <div class="dossier-header">
                    <div>
                        <h3 class="dossier-title">${f.crime_type || 'Crime'}</h3>
                        <div class="dossier-location">Jurisdiction: <strong>${f.location || 'District'}</strong> (${f.period || 'Current'})</div>
                    </div>
                    <span style="padding: 3px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; display: inline-flex; align-items: center; ${badgeStyle}">
                        <span style="display:inline-block; width:6px; height:6px; background:${dotColor}; border-radius:50%; margin-right:6px; vertical-align:middle;"></span>${statusText}
                    </span>
                </div>

                <div class="baseline-gauge">
                    <div class="gauge-labels">
                        <span style="color:#cbd5e1;">Current Frequency: <strong style="color:#f8fafc;">${caseCount} Cases</strong></span>
                        <span style="color:#a5b4fc;">AI Rolling Baseline: <strong>${rollingAvg} Cases</strong></span>
                    </div>
                    <div class="gauge-bar-bg" style="margin-bottom: 4px;">
                        <div class="gauge-bar-fill" style="width: ${currentBarWidth}%; background: ${isSpike ? '#f87171' : '#8b5cf6'};"></div>
                    </div>
                    <div class="gauge-bar-bg">
                        <div class="gauge-bar-fill" style="width: ${baselineBarWidth}%; background: #6366f1; opacity: 0.8;"></div>
                    </div>
                </div>

                <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 10px;"><strong>Extracted Modus Operandi (MO) Clusters:</strong></div>
                <div class="mo-cluster-list">${moList}</div>

                <div class="tactical-footer">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="2" style="flex-shrink:0;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                    <span><strong>Tactical Action:</strong> ${tacticalRecommendation}</span>
                </div>
            </div>
        `;
    });
}

function renderTrendsBarLineChart(findings) {
    const ctx = document.getElementById('fullTrendsChart');
    if (!ctx) return;
    if (fullTrendsChartInstance) fullTrendsChartInstance.destroy();

    const labels = findings.length > 0 ? findings.map(t => `${t.crime_type} (${t.location})`) : ['No Inquiry Spikes Analyzed Yet'];
    const counts = findings.length > 0 ? findings.map(t => t.case_count ?? 0) : [0];
    const rollingAvgs = findings.length > 0 ? findings.map(t => t.rolling_avg ?? t.case_count ?? 0) : [0];
    const barColors = findings.length > 0 ? findings.map(t => (t.is_spike || (t.pct_change && t.pct_change >= 25)) ? 'rgba(248, 113, 113, 0.85)' : 'rgba(139, 92, 246, 0.85)') : ['rgba(139, 92, 246, 0.3)'];
    const borderColors = findings.length > 0 ? findings.map(t => (t.is_spike || (t.pct_change && t.pct_change >= 25)) ? '#f87171' : '#8b5cf6') : ['#8b5cf6'];

    fullTrendsChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    type: 'line',
                    label: 'AI 3-Period Rolling Baseline',
                    data: rollingAvgs,
                    borderColor: '#a855f7',
                    backgroundColor: 'rgba(168, 85, 247, 0.15)',
                    borderWidth: 2.5,
                    pointBackgroundColor: '#a855f7',
                    pointRadius: 4,
                    tension: 0.3,
                    order: 1
                },
                {
                    type: 'bar',
                    label: 'Actual Incident Volume (Red = Spike)',
                    data: counts,
                    backgroundColor: barColors,
                    borderColor: borderColors,
                    borderWidth: 1.5,
                    borderRadius: 6,
                    order: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(62, 78, 110, 0.2)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 12 } } }
            },
            plugins: {
                legend: { labels: { color: '#f8fafc', font: { size: 13 } } },
                tooltip: {
                    callbacks: {
                        afterLabel: function (context) {
                            if (context.datasetIndex === 1 && findings[context.dataIndex]) {
                                const t = findings[context.dataIndex];
                                return t.pct_change ? `Surge Change: ${t.pct_change > 0 ? '+' : ''}${t.pct_change}% vs baseline` : '';
                            }
                            return '';
                        }
                    }
                }
            }
        }
    });
}

function renderHotspotShareChart(hotspots) {
    const ctx = document.getElementById('hotspotShareChart');
    if (!ctx) return;
    if (hotspotShareChartInstance) hotspotShareChartInstance.destroy();

    if (!hotspots || hotspots.length === 0) {
        hotspots = [
            { location: "No Hotspots Flagged Yet", case_count: 0, percentage: 100 }
        ];
    }

    const labels = hotspots.map(h => h.location);
    const dataVals = hotspots.map(h => h.percentage || h.case_count || 10);
    const bgColors = [
        'rgba(139, 92, 246, 0.85)',
        'rgba(99, 102, 241, 0.85)',
        'rgba(52, 211, 153, 0.85)',
        'rgba(248, 113, 113, 0.85)',
        'rgba(251, 191, 36, 0.85)'
    ];

    hotspotShareChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataVals,
                backgroundColor: bgColors,
                borderColor: '#0c0f20',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#cbd5e1', font: { size: 12 }, padding: 12 }
                },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return `${context.label}: ${context.raw}% concentration share`;
                        }
                    }
                }
            },
            cutout: '62%'
        }
    });
}

function filterTrendsByJurisdiction(jurisdiction, btnElement) {
    if (btnElement) {
        document.querySelectorAll('#trends-filter-pills .pill').forEach(p => p.classList.remove('active'));
        btnElement.classList.add('active');
    }

    if (!window.currentTrendsData || !window.currentTrendsData.trend_findings) return;
    const allFindings = window.currentTrendsData.trend_findings;

    let filtered = allFindings;
    if (jurisdiction !== 'all') {
        filtered = allFindings.filter(f => (f.location || '').toLowerCase().includes(jurisdiction.toLowerCase()));
    }

    renderTrendsDossiers(filtered);
    renderTrendsBarLineChart(filtered);
}

// Tab Switching Logic
function switchTab(tabId, btnElement) {
    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));

    document.getElementById(tabId).classList.add('active');
    if (btnElement) btnElement.classList.add('active');

    // Resize chart/graph if visible
    if (tabId === 'tab-graph' && networkInstance) {
        networkInstance.redraw();
    } else if (tabId === 'tab-trends' && trendsChartInstance) {
        trendsChartInstance.resize();
    }
}

// Quick Prompt Setter
function setQuery(text) {
    document.getElementById('query-input').value = text;
    executeInvestigation();
}

// Execute Main API Investigation
async function executeInvestigation() {
    const inputEl = document.getElementById('query-input');
    const sendBtn = document.getElementById('send-btn');
    const datasetSelectEl = document.getElementById('dataset-select');
    const datasetVal = datasetSelectEl ? datasetSelectEl.value : 'complex';
    const queryText = inputEl.value.trim();

    if (!queryText) return;

    // Save active status and query text to sessionStorage for seamless restoration across page switches within current session
    sessionStorage.setItem('activeInvestigationStatus', 'running');
    sessionStorage.setItem('lastUserQueryText', queryText);

    // Append User Message to Chat
    appendMessage(queryText, 'user');
    inputEl.value = '';

    // Show Loading state
    sendBtn.disabled = true;
    sendBtn.innerHTML = `<span>Investigating...</span><span class="status-dot"></span>`;
    appendMessage("Analyzing multi-agent blackboard, retrieving records, building syndicate graph, and double-checking courtroom claims...", 'system-loading');

    try {
        const requestBody = {
            query: queryText,
            session_id: localStorage.getItem('crime_session_id') || 'default'
        };
        // The command center currently has no dataset selector. Do not send
        // a synthetic "complex" value because that would override a dataset
        // uploaded into the active session.
        if (datasetSelectEl) requestBody.dataset = datasetVal;

        const controller = new AbortController();
        const timeoutId = window.setTimeout(() => controller.abort(), 90000);
        let response;
        try {
            response = await fetch('/api/investigate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
                signal: controller.signal
            });
        } catch (requestError) {
            if (requestError.name === 'AbortError') {
                throw new Error('The investigation timed out after 90 seconds. Check the dataset and try again.');
            }
            throw new Error('The backend is unavailable. Confirm the server is running and try again.');
        } finally {
            window.clearTimeout(timeoutId);
        }

        if (!response.ok) {
            let detail = 'API request failed.';
            try {
                const errData = await response.json();
                detail = errData.detail || detail;
            } catch (_) {
                // A proxy/static-server error may return HTML instead of JSON.
            }
            throw new Error(detail);
        }

        const data = await response.json();
        sessionStorage.setItem('latestCrimeData', JSON.stringify(data));
        sessionStorage.setItem('activeInvestigationStatus', 'completed');
        sessionStorage.setItem('lastAIAnswerText', data.answer_text || "No response generated.");

        // Remove loading message
        removeLoadingMessage();

        // Display AI Report in Chat — with live agent telemetry bar
        appendMessage(formatMarkdownToHTML(data.answer_text || "No response generated."), 'ai', {
            agents: data.agents_used || [],
            verificationRate: data.verification_rate ?? 100.0
        });


        // 1. Render Network Graph (`tab-graph`)
        if (data.network_graph && data.network_graph.nodes && data.network_graph.nodes.length > 0) {
            renderNetworkGraph(data.network_graph);
        } else {
            document.getElementById('network-graph-container').innerHTML = `
                <div class="empty-state">
                    <div class="drop-icon flex-center mb-2"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></div>
                    <p>No network connections detected for this query.</p>
                </div>
            `;
        }

        // 2. Render Trends & Spikes (`tab-trends`)
        renderTrends(data.trend_findings || []);

        // 3. Render Courtroom Audit (`tab-audit`)
        renderAudit(data.citations || [], data.verification_rate ?? 100.0, data.unsupported_claims || []);

    } catch (err) {
        sessionStorage.setItem('activeInvestigationStatus', 'failed');
        removeLoadingMessage();
        appendMessage(`Investigation Error: ${err.message}`, 'error');
        console.error(err);
    } finally {
        sendBtn.disabled = false;
        sendBtn.innerHTML = `
            <span>Launch Inquiry</span>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
        `;
    }
}

// ==========================================================================
// AGENT TELEMETRY BAR BUILDER
// Builds the live animated agent execution bar from real API response data.
// Each agent type gets its own color-coded pill with staggered fade-in animation.
// ==========================================================================
const AGENT_META = {
    planner_agent: { cssClass: 'agent-planner', label: 'Planner Agent' },
    query_agent: { cssClass: 'agent-query', label: 'Query Agent' },
    link_agent: { cssClass: 'agent-link', label: 'Link Agent' },
    trend_agent: { cssClass: 'agent-trend', label: 'Trend Agent' },
    risk_agent: { cssClass: 'agent-risk', label: 'Risk Agent' },
    verifier_agent: { cssClass: 'agent-verifier', label: 'Verifier Agent' },
};

function buildAgentTelemetryBar(agents, verificationRate) {
    if (!agents || agents.length === 0) return '';

    // Only show agents that actually ran — always append verifier since it always runs
    const pipelineAgents = [...agents];
    if (!pipelineAgents.includes('verifier_agent')) pipelineAgents.push('verifier_agent');

    // Build pills with staggered CSS animation delay
    let pillsHTML = '';
    pipelineAgents.forEach((agentKey, idx) => {
        const meta = AGENT_META[agentKey] || { cssClass: 'agent-query', label: agentKey };
        const delay = (idx * 0.08).toFixed(2);
        const isLast = idx === pipelineAgents.length - 1;
        pillsHTML += `<span class="agent-pill ${meta.cssClass}" style="animation-delay:${delay}s" title="${agentKey}"><span class="agent-pill-dot"></span>${meta.label}</span>`;
        if (!isLast) pillsHTML += `<span class="agent-pill-arrow">→</span>`;
    });

    // Verification rate badge
    const rate = typeof verificationRate === 'number' ? verificationRate : 100.0;
    const rateClass = rate >= 85 ? 'rate-high' : rate >= 60 ? 'rate-medium' : 'rate-low';
    const rateIcon = rate >= 85 ? '✓' : rate >= 60 ? '⚠' : '✗';
    const badgeHTML = `<span class="telemetry-verify-badge ${rateClass}" title="Verifier grounding rate: ${rate.toFixed(1)}%">${rateIcon} ${rate.toFixed(1)}% Grounded</span>`;

    return `
    <div class="agent-telemetry-bar">
        <div class="agent-telemetry-label">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"></path></svg>
            Agents Mobilised
        </div>
        <div class="agent-telemetry-pills">
            ${pillsHTML}
            ${badgeHTML}
        </div>
    </div>`;
}


// Chat UI Helper — accepts optional agentsMeta { agents, verificationRate }
function appendMessage(content, sender, agentsMeta) {
    const chatHistory = document.getElementById('chat-history');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender === 'user' ? 'user-message' : 'system-message'}`;

    if (sender === 'system-loading') {
        msgDiv.id = 'loading-bubble';
    }

    const avatar = sender === 'user'
        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`
        : (sender === 'error'
            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--status-high)" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`
            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`);

    // Build agent telemetry bar HTML for AI messages that have agent metadata
    const telemetryHTML = (sender === 'ai' && agentsMeta && agentsMeta.agents && agentsMeta.agents.length > 0)
        ? buildAgentTelemetryBar(agentsMeta.agents, agentsMeta.verificationRate)
        : '';

    // User and error strings are plain text; only the locally formatted AI
    // response is allowed to contain presentation markup.
    const renderedContent = sender === 'ai' || sender === 'system-loading'
        ? content
        : escapeHtml(String(content));
    msgDiv.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-content">${renderedContent}${telemetryHTML}</div>
    `;

    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function removeLoadingMessage() {
    const loadingBubble = document.getElementById('loading-bubble');
    if (loadingBubble) loadingBubble.remove();
}

function escapeHtml(value) {
    return value.replace(/[&<>"']/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    }[character]));
}

// Basic Markdown to HTML formatting for Composer Output. Escape first so
// generated text cannot introduce scripts or arbitrary attributes.
function formatMarkdownToHTML(md) {
    return escapeHtml(String(md || ''))
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        .replace(/\n/g, '<br>');
}

// 1. Vis.js Network Graph Renderer — Industry Grade
function renderNetworkGraph(graphData, containerId = 'network-graph-container') {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    // ── Node type → visual config map ──────────────────────────────────────
    const NODE_STYLES = {
        // Accused / Suspects — Red Dot
        accused: { shape: 'dot', size: 28, bg: '#ef4444', border: '#fca5a5', glow: 'rgba(239,68,68,0.6)', font: '#fef2f2' },
        suspect: { shape: 'dot', size: 28, bg: '#ef4444', border: '#fca5a5', glow: 'rgba(239,68,68,0.6)', font: '#fef2f2' },

        // Victims — Cyan Dot
        victim: { shape: 'dot', size: 22, bg: '#06b6d4', border: '#67e8f9', glow: 'rgba(6,182,212,0.5)', font: '#ecfeff' },

        // Persons / Narrative Entities — Purple Dot
        person: { shape: 'dot', size: 20, bg: '#8b5cf6', border: '#c4b5fd', glow: 'rgba(139,92,246,0.5)', font: '#f5f3ff' },
        narrative_entity: { shape: 'dot', size: 20, bg: '#8b5cf6', border: '#c4b5fd', glow: 'rgba(139,92,246,0.5)', font: '#f5f3ff' },

        // Locations / Addresses / Jurisdictions / Districts — Amber Gold Hexagon
        location: { shape: 'hexagon', size: 24, bg: '#f59e0b', border: '#fef08a', glow: 'rgba(245,158,11,0.75)', font: '#fffbeb' },
        address: { shape: 'hexagon', size: 24, bg: '#f59e0b', border: '#fef08a', glow: 'rgba(245,158,11,0.75)', font: '#fffbeb' },
        place: { shape: 'hexagon', size: 24, bg: '#f59e0b', border: '#fef08a', glow: 'rgba(245,158,11,0.75)', font: '#fffbeb' },
        district: { shape: 'hexagon', size: 24, bg: '#f59e0b', border: '#fef08a', glow: 'rgba(245,158,11,0.75)', font: '#fffbeb' },
        gpe: { shape: 'hexagon', size: 24, bg: '#f59e0b', border: '#fef08a', glow: 'rgba(245,158,11,0.75)', font: '#fffbeb' },
        loc: { shape: 'hexagon', size: 24, bg: '#f59e0b', border: '#fef08a', glow: 'rgba(245,158,11,0.75)', font: '#fffbeb' },
        site: { shape: 'hexagon', size: 24, bg: '#f59e0b', border: '#fef08a', glow: 'rgba(245,158,11,0.75)', font: '#fffbeb' },

        // Crimes / Incidents — Indigo Square
        crime: { shape: 'square', size: 18, bg: '#6366f1', border: '#a5b4fc', glow: 'rgba(99,102,241,0.5)', font: '#eef2ff' },
        case: { shape: 'square', size: 18, bg: '#6366f1', border: '#a5b4fc', glow: 'rgba(99,102,241,0.5)', font: '#eef2ff' },

        default: { shape: 'dot', size: 18, bg: '#64748b', border: '#94a3b8', glow: 'rgba(100,116,139,0.4)', font: '#f8fafc' },
    };

    // ── Build Vis.js nodes ──────────────────────────────────────────────────
    const visNodes = graphData.nodes.map(n => {
        let type = (n.type || 'default').toLowerCase();

        // Smart fallback detection: if basis or label indicates an address/location
        const basis = (n.basis || '').toLowerCase();
        const rawLabel = (n.label || n.name || n.id || '').toLowerCase();
        if (basis.includes('address') || basis.includes('location') || basis.includes('same_address') ||
            rawLabel.includes('road') || rawLabel.includes('nagar') || rawLabel.includes('street') ||
            rawLabel.includes('district') || rawLabel.includes('colony') || rawLabel.includes('layout')) {
            type = 'location';
        }

        const style = NODE_STYLES[type] || NODE_STYLES.default;
        const label = (n.label || n.name || n.id || '').toString();


        return {
            id: n.id,
            label: label.length > 18 ? label.substring(0, 16) + '…' : label,
            title: `<div style="background:#131830;border:1px solid rgba(139,92,246,0.4);border-radius:8px;padding:8px 12px;font-family:Inter,sans-serif;font-size:12px;color:#f8fafc;max-width:200px;">
                        <strong style="color:#c4b5fd">${label}</strong><br>
                        <span style="color:#94a3b8;font-size:11px;">Type: ${type.charAt(0).toUpperCase() + type.slice(1)}</span>
                        ${n.case_id ? `<br><span style="color:#94a3b8;font-size:11px;">Case: ${n.case_id}</span>` : ''}
                    </div>`,
            shape: style.shape,
            size: style.size,
            color: {
                background: style.bg,
                border: style.border,
                highlight: { background: style.border, border: '#ffffff' },
                hover: { background: style.border, border: '#ffffff' }
            },
            shadow: { enabled: true, color: style.glow, size: 18, x: 0, y: 0 },
            font: {
                color: style.font,
                face: 'Inter',
                size: 12,
                bold: { color: style.font, size: 12 },
                vadjust: style.shape === 'dot' ? 0 : 2
            },
            borderWidth: 2,
            borderWidthSelected: 3,
        };
    });

    // ── Edge color by relationship type ────────────────────────────────────
    function edgeColor(basis) {
        const b = (basis || '').toLowerCase();
        if (b.includes('co-accused') || b.includes('co_accused')) return { color: 'rgba(239,68,68,0.65)', highlight: '#f87171' };
        if (b.includes('victim')) return { color: 'rgba(6,182,212,0.55)', highlight: '#22d3ee' };
        if (b.includes('location') || b.includes('district')) return { color: 'rgba(245,158,11,0.55)', highlight: '#fbbf24' };
        return { color: 'rgba(139,92,246,0.55)', highlight: '#a78bfa' };
    }

    // ── Build Vis.js edges ──────────────────────────────────────────────────
    const visEdges = graphData.edges.map((e, idx) => {
        const ec = edgeColor(e.basis);
        return {
            id: `edge_${idx}`,
            from: e.source,
            to: e.target,
            label: e.basis || '',
            title: e.basis ? `<div style="background:#131830;border:1px solid rgba(139,92,246,0.35);border-radius:6px;padding:6px 10px;font-size:11px;color:#94a3b8;">${e.basis}</div>` : '',
            color: { ...ec, opacity: 0.85 },
            font: {
                color: '#64748b',
                face: 'JetBrains Mono',
                size: 10,
                align: 'middle',
                strokeWidth: 2,
                strokeColor: 'rgba(6,8,20,0.9)',
                vadjust: -4,
            },
            arrows: { to: { enabled: true, scaleFactor: 0.55, type: 'arrow' } },
            smooth: { enabled: true, type: 'curvedCW', roundness: 0.15 },
            width: 2,
            shadow: { enabled: true, color: ec.color, size: 6, x: 0, y: 0 },
        };
    });

    const data = {
        nodes: new vis.DataSet(visNodes),
        edges: new vis.DataSet(visEdges)
    };

    // ── Physics + Interaction options ───────────────────────────────────────
    const options = {
        nodes: { scaling: { min: 14, max: 34 } },
        edges: { scaling: { min: 1, max: 4 } },
        physics: {
            solver: 'barnesHut',
            barnesHut: {
                gravitationalConstant: -8000,
                centralGravity: 0.25,
                springLength: 160,
                springConstant: 0.04,
                damping: 0.15,
                avoidOverlap: 0.3
            },
            maxVelocity: 55,
            minVelocity: 0.1,
            timestep: 0.4,
            stabilization: { iterations: 200, fit: true }
        },
        interaction: {
            hover: true,
            tooltipDelay: 120,
            zoomView: true,
            dragView: true,
            navigationButtons: false,
            keyboard: true,
        },
        layout: { improvedLayout: true },
    };

    networkInstance = new vis.Network(container, data, options);

    // ── Evidence-rich hover card ─────────────────────────────────────────────
    const nodeLookup = new Map(graphData.nodes.map(node => [String(node.id), node]));
    const hoverCard = document.createElement('div');
    hoverCard.className = 'graph-hover-card is-hidden';
    container.appendChild(hoverCard);

    const escapeGraphValue = value => String(value ?? '').replace(/[&<>\"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', "'": '&#39;' }[char]));
    const detailRow = (key, value) => `<div class="graph-hover-card__row"><span class="graph-hover-card__key">${escapeGraphValue(key)}</span><span class="graph-hover-card__value">${escapeGraphValue(value)}</span></div>`;
    const positionHoverCard = pointer => {
        const point = pointer && (pointer.DOM || pointer.canvas);
        if (!point) return;
        const cardWidth = Math.min(320, Math.max(220, container.clientWidth - 24));
        const left = Math.max(12, Math.min(point.x + 16, container.clientWidth - cardWidth - 12));
        const top = Math.max(12, Math.min(point.y + 16, container.clientHeight - 245));
        hoverCard.style.left = `${left}px`;
        hoverCard.style.top = `${top}px`;
    };
    const showHoverCard = (kind, title, rows, pointer) => {
        hoverCard.innerHTML = `<div class="graph-hover-card__eyebrow">${escapeGraphValue(kind)}</div><div class="graph-hover-card__title">${escapeGraphValue(title)}</div>${rows.filter(row => row[1] !== undefined && row[1] !== null && String(row[1]).trim() !== '').map(row => detailRow(row[0], row[1])).join('')}`;
        hoverCard.classList.remove('is-hidden');
        positionHoverCard(pointer);
    };
    const hideHoverCard = () => hoverCard.classList.add('is-hidden');

    networkInstance.on('hoverNode', params => {
        const node = nodeLookup.get(String(params.node));
        if (!node) return;
        const label = node.label || node.name || node.id;
        const type = node.type || 'entity';
        showHoverCard('Network entity', label, [
            ['Type', type],
            ['Case', node.case_id],
            ['District', node.district],
            ['Crime', node.crime_type],
            ['Evidence', node.basis],
            ['Details', node.description],
            ['Identifier', node.id]
        ], params.pointer);
    });
    networkInstance.on('hoverEdge', params => {
        const edge = graphData.edges[Number(String(params.edge).replace('edge_', ''))];
        if (!edge) return;
        const source = nodeLookup.get(String(edge.source));
        const target = nodeLookup.get(String(edge.target));
        showHoverCard('Relationship evidence', edge.basis || edge.label || 'Linked entities', [
            ['From', source?.label || edge.source],
            ['To', target?.label || edge.target],
            ['Relationship', edge.basis || edge.relationship || edge.label],
            ['Source ID', edge.source],
            ['Target ID', edge.target]
        ], params.pointer);
    });
    networkInstance.on('blurNode', hideHoverCard);
    networkInstance.on('blurEdge', hideHoverCard);

    // ── Stats overlay ───────────────────────────────────────────────────────
    const statsBar = document.createElement('div');
    statsBar.className = 'graph-stats-bar';
    statsBar.innerHTML = `
        <span class="graph-stat-chip">⬡ ${visNodes.length} Entities</span>
        <span class="graph-stat-chip">↔ ${visEdges.length} Links</span>
    `;
    container.appendChild(statsBar);

    // ── Floating zoom controls ──────────────────────────────────────────────
    const controls = document.createElement('div');
    controls.className = 'graph-controls';
    controls.innerHTML = `
        <button class="graph-ctrl-btn" title="Zoom In"  onclick="networkInstance.moveTo({scale: networkInstance.getScale()*1.3, animation:{duration:300,easingFunction:'easeInOutQuad'}})">+</button>
        <button class="graph-ctrl-btn" title="Zoom Out" onclick="networkInstance.moveTo({scale: networkInstance.getScale()*0.75,animation:{duration:300,easingFunction:'easeInOutQuad'}})">−</button>
        <button class="graph-ctrl-btn" title="Fit All"  onclick="networkInstance.fit({animation:{duration:400,easingFunction:'easeInOutQuad'}})">⤢</button>
        <button class="graph-ctrl-btn" title="Reset Physics" onclick="networkInstance.setOptions({physics:{enabled:true}});networkInstance.stabilize()">⟳</button>
    `;
    container.appendChild(controls);

    // Disable physics after stabilisation for performance
    networkInstance.on('stabilizationIterationsDone', () => {
        networkInstance.setOptions({ physics: { enabled: false } });
        networkInstance.fit({ animation: { duration: 600, easingFunction: 'easeInOutQuad' } });
    });
}


// 2. Chart.js Trends & Spikes Renderer (Command Center Dashboard)
function renderTrends(trendFindings) {
    const alertsContainer = document.getElementById('trend-alerts-container');
    alertsContainer.innerHTML = '';

    if (!trendFindings || trendFindings.length === 0) {
        alertsContainer.innerHTML = `
            <div class="alert-card" style="background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.3);">
                <h4 style="color: var(--status-low); display: flex; align-items: center;"><span style="display:inline-block; width:8px; height:8px; background:#10b981; border-radius:50%; margin-right:8px;"></span>Normal Baseline Volume — No Spikes Flagged</h4>
                <p>All crime categories across monitored jurisdictions remain stable relative to 3-period rolling averages.</p>
            </div>
        `;
    } else {
        trendFindings.forEach(f => {
            const isSpike = f.is_spike || (f.pct_change && f.pct_change >= 25);
            const badgeStyle = isSpike ? 'background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; color: #fca5a5;' : 'background: rgba(0, 242, 254, 0.15); border: 1px solid #00f2fe; color: #a5f3fc;';
            const dotColor = isSpike ? '#ef4444' : '#00f2fe';
            const statusText = isSpike ? `CRITICAL SPIKE (+${f.pct_change ?? '25+'}% surge above baseline)` : `BASELINE PROGRESSION (${f.trend_direction || 'Stable'})`;
            const statusBadgeHTML = `<span style="display:inline-block; width:6px; height:6px; background:${dotColor}; border-radius:50%; margin-right:5px; vertical-align:middle;"></span>${statusText}`;
            const moList = (f.mo_patterns || []).length > 0 ? (f.mo_patterns || []).map(mo => `<span style="display:inline-block; background:rgba(255,255,255,0.08); padding: 2px 8px; border-radius: 4px; margin: 2px; font-size: 0.8rem;">${mo}</span>`).join(' ') : '<em>Standard historical pattern</em>';

            alertsContainer.innerHTML += `
                <div class="alert-card" style="${isSpike ? 'border-left: 4px solid #ef4444; background: rgba(239, 68, 68, 0.06);' : 'border-left: 4px solid #00f2fe;'}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <h4 style="margin: 0; font-size: 1rem; color: #f8fafc;">${f.crime_type || 'Crime'} <span style="color: #94a3b8; font-weight: normal;">in ${f.location || 'District'} (${f.period || 'Current'})</span></h4>
                        <span style="padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; display: inline-flex; align-items: center; ${badgeStyle}">${statusBadgeHTML}</span>
                    </div>
                    <p style="margin: 4px 0; font-size: 0.88rem; color: #cbd5e1;">Recorded <strong>${f.case_count ?? 0}</strong> incidents (Rolling Avg Baseline: <strong>${f.rolling_avg ?? f.case_count ?? 0}</strong> cases).</p>
                    <div style="margin-top: 8px; font-size: 0.82rem; color: #94a3b8;"><strong>Identified MO Clusters:</strong> ${moList}</div>
                </div>
            `;
        });
    }

    // Render multi-dataset AI chart (Bar = Volume, Line = Rolling Baseline)
    const ctx = document.getElementById('trendsChart');
    if (!ctx) return;
    if (trendsChartInstance) trendsChartInstance.destroy();

    const labels = trendFindings.length > 0 ? trendFindings.map(t => `${t.crime_type} (${t.location})`) : ['No Inquiry Spikes Analyzed Yet'];
    const counts = trendFindings.length > 0 ? trendFindings.map(t => t.case_count ?? 0) : [0];
    const rollingAvgs = trendFindings.length > 0 ? trendFindings.map(t => t.rolling_avg ?? t.case_count ?? 0) : [0];
    const barColors = trendFindings.length > 0 ? trendFindings.map(t => (t.is_spike || (t.pct_change && t.pct_change >= 25)) ? 'rgba(248, 113, 113, 0.85)' : 'rgba(139, 92, 246, 0.85)') : ['rgba(139, 92, 246, 0.3)'];
    const borderColors = trendFindings.length > 0 ? trendFindings.map(t => (t.is_spike || (t.pct_change && t.pct_change >= 25)) ? '#f87171' : '#8b5cf6') : ['#8b5cf6'];

    trendsChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    type: 'line',
                    label: 'AI 3-Period Rolling Baseline',
                    data: rollingAvgs,
                    borderColor: '#a855f7',
                    backgroundColor: 'rgba(168, 85, 247, 0.12)',
                    borderWidth: 2.5,
                    pointBackgroundColor: '#a855f7',
                    pointRadius: 4,
                    tension: 0.3,
                    order: 1
                },
                {
                    type: 'bar',
                    label: 'Actual Incident Volume (Red = Spike)',
                    data: counts,
                    backgroundColor: barColors,
                    borderColor: borderColors,
                    borderWidth: 1.5,
                    borderRadius: 6,
                    order: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(62, 78, 110, 0.2)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            },
            plugins: {
                legend: { labels: { color: '#f8fafc', font: { size: 12 } } },
                tooltip: {
                    callbacks: {
                        afterLabel: function (context) {
                            if (context.datasetIndex === 1 && trendFindings[context.dataIndex]) {
                                const t = trendFindings[context.dataIndex];
                                return t.pct_change ? `Surge Change: ${t.pct_change > 0 ? '+' : ''}${t.pct_change}% vs baseline` : '';
                            }
                            return '';
                        }
                    }
                }
            }
        }
    });
}

// 3. Courtroom Audit Renderer (audit.html functionality)
function renderAudit(citations, rate, unsupported) {
    const badge = document.getElementById('verification-status-badge');
    const container = document.getElementById('audit-table-container');
    if (!badge || !container) return;

    rate = Number.isFinite(Number(rate)) ? Number(rate) : 100.0;

    badge.innerText = `Verified: ${rate.toFixed(1)}%`;
    if (rate >= 90) {
        badge.className = 'verify-badge verified';
    } else {
        badge.className = 'verify-badge warning';
    }

    if (!citations || citations.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="drop-icon flex-center mb-2"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="M7 21h10"></path><path d="M12 3v18"></path><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"></path></svg></div>
                <p>No factual claims cited for this query.</p>
            </div>
        `;
        return;
    }

    let tableHtml = `
        <table class="audit-table">
            <thead>
                <tr>
                    <th>Case Source</th>
                    <th>Verified Grounding Factual Claim</th>
                </tr>
            </thead>
            <tbody>
    `;

    citations.forEach(c => {
        tableHtml += `
            <tr>
                <td class="cid-tag">[${c.record_id || 'FIR'}]</td>
                <td>
                    <strong>${c.claim || ''}</strong>
                    <div class="snippet-box">${c.raw_text_snippet || c.snippet ? `"${c.raw_text_snippet || c.snippet}"` : 'Verified against official FIR description'}</div>
                </td>
            </tr>
        `;
    });

    if (unsupported && unsupported.length > 0) {
        unsupported.forEach(u => {
            const unsupportedText = typeof u === 'string' ? u : (u.claim || u.text || 'Unsupported claim');
            tableHtml += `
                <tr style="background: rgba(239, 68, 68, 0.1);">
                    <td class="cid-tag" style="color: var(--status-high);">[UNSUPPORTED]</td>
                    <td>
                        <strong style="color: var(--status-high);">${unsupportedText}</strong>
                        <div class="snippet-box">Discarded by Verifier: No backing police record found.</div>
                    </td>
                </tr>
            `;
        });
    }

    tableHtml += `</tbody></table>`;
    container.innerHTML = tableHtml;
}

// Handle Enter to Submit
const queryInputEl = document.getElementById('query-input');
if (queryInputEl) {
    queryInputEl.addEventListener('keypress', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            executeInvestigation();
        }
    });
}

// ==========================================================================
// STANDALONE PAGE DATA LOADERS & HANDLERS (`audit.html`, `graph.html`, etc.)
// ==========================================================================

let allAuditCitations = [];
let allDatabaseRecords = [];
let auditFilterMode = 'all';

// 1. Audit Page Loader (`audit.html`)
function loadAuditPageData() {
    localStorage.removeItem('latestCrimeData');
    const stored = sessionStorage.getItem('latestCrimeData');
    if (stored) {
        try {
            const data = JSON.parse(stored);
            allAuditCitations = data.citations || [];
            const rate = data.verification_rate ?? 100.0;
            const unsupported = data.unsupported_claims || [];

            const rateEl = document.getElementById('audit-rate-val');
            if (rateEl) rateEl.innerText = `${rate.toFixed(1)}%`;

            renderAuditTableRows(allAuditCitations, unsupported);
            return;
        } catch (e) { console.error(e); }
    }

    // If empty or no recent query, show prompt
    const tbody = document.getElementById('audit-tbody');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="3" class="text-center" style="padding: 3rem;">
                    <div class="drop-icon flex-center mb-2"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></div>
                    <p>No active verification data found. Please run an investigation inquiry from the <a href="index.html" style="color: var(--accent-cyan);">Command Center</a> first.</p>
                </td>
            </tr>
        `;
    }
}

function renderAuditTableRows(citations, unsupported) {
    const tbody = document.getElementById('audit-tbody');
    if (!tbody) return;

    const searchVal = (document.getElementById('audit-search')?.value || '').toLowerCase();
    tbody.innerHTML = '';

    let renderedCount = 0;

    // Render verified citations if matching filter
    if (auditFilterMode === 'all' || auditFilterMode === 'verified') {
        citations.forEach(c => {
            const cid = (c.record_id || 'FIR').toLowerCase();
            const claim = (c.claim || '').toLowerCase();
            const snippet = (c.raw_text_snippet || c.snippet || '').toLowerCase();

            if (searchVal && !cid.includes(searchVal) && !claim.includes(searchVal) && !snippet.includes(searchVal)) return;

            renderedCount++;
            tbody.innerHTML += `
                <tr>
                    <td class="cid-tag">[${c.record_id || 'FIR'}]</td>
                    <td><span class="verify-badge verified">Verified</span></td>
                    <td>
                        <strong>${c.claim || ''}</strong>
                        <div class="snippet-box">${c.raw_text_snippet || c.snippet ? `"${c.raw_text_snippet || c.snippet}"` : 'Verified against official FIR description'}</div>
                    </td>
                </tr>
            `;
        });
    }

    // Render unsupported claims if matching filter
    if (auditFilterMode === 'all' || auditFilterMode === 'unsupported') {
        if (unsupported && unsupported.length > 0) {
            unsupported.forEach(u => {
                const unsupportedText = typeof u === 'string' ? u : (u.claim || u.text || 'Unsupported claim');
                if (searchVal && !unsupportedText.toLowerCase().includes(searchVal)) return;
                renderedCount++;
                tbody.innerHTML += `
                    <tr style="background: rgba(239, 68, 68, 0.1);">
                        <td class="cid-tag" style="color: var(--status-high);">[UNSUPPORTED]</td>
                        <td><span class="verify-badge warning" style="background: rgba(239,68,68,0.2); border-color: var(--status-high); color: var(--status-high);">Discarded</span></td>
                        <td>
                            <strong style="color: var(--status-high);">${unsupportedText}</strong>
                            <div class="snippet-box">Discarded by Verifier: No backing police record found in FIR repository.</div>
                        </td>
                    </tr>
                `;
            });
        }
    }

    if (renderedCount === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="text-center" style="padding: 2rem;">No matching citations found.</td></tr>`;
    }
}

function filterAuditTable() {
    const stored = sessionStorage.getItem('latestCrimeData');
    if (stored) {
        const data = JSON.parse(stored);
        renderAuditTableRows(data.citations || [], data.unsupported_claims || []);
    }
}

function setAuditFilter(mode, btnEl) {
    auditFilterMode = mode;
    document.querySelectorAll('.filter-pills .pill').forEach(p => p.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');
    filterAuditTable();
}

// 2. Graph Page Loader (`graph.html`)
function loadGraphPageData() {
    localStorage.removeItem('latestCrimeData');
    const stored = sessionStorage.getItem('latestCrimeData');
    if (stored) {
        try {
            const data = JSON.parse(stored);
            if (data.network_graph && data.network_graph.nodes && data.network_graph.nodes.length > 0) {
                renderFullNetworkGraph(data.network_graph);
                return;
            }
        } catch (e) { console.error(e); }
    }
}

function renderFullNetworkGraph(graphData) {
    renderNetworkGraph(graphData, 'full-graph-container');
}

function resetGraphPhysics() {
    if (networkInstance) {
        networkInstance.setOptions({ physics: { enabled: true } });
        networkInstance.stabilize();
    }
}

function fitGraphView() {
    if (networkInstance) {
        networkInstance.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
    }
}

// 4. Database Records Page Loader (`records.html`)
async function fetchDatabaseRecords() {
    const dbSelect = document.getElementById('db-select');
    const dsKey = dbSelect ? dbSelect.value : 'complex';
    const tbody = document.getElementById('db-tbody');
    const totalCountEl = document.getElementById('db-total-count');

    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 3rem;"><div class="drop-icon flex-center mb-2"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg></div><p>Fetching records from backend API...</p></td></tr>`;
    }

    try {
        const sessionId = localStorage.getItem('crime_session_id') || 'default';
        const res = await fetch(`/api/records?dataset=${encodeURIComponent(dsKey)}&session_id=${encodeURIComponent(sessionId)}`);
        if (!res.ok) {
            let detail = "Failed to load records";
            try {
                const errorData = await res.json();
                detail = errorData.detail || detail;
            } catch (_) { /* keep the readable fallback */ }
            throw new Error(detail);
        }
        const data = await res.json();
        allDatabaseRecords = data.records || [];

        if (totalCountEl) totalCountEl.innerText = allDatabaseRecords.length;
        renderDatabaseRows(allDatabaseRecords);
    } catch (e) {
        console.error(e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 2rem; color: var(--status-high);">Error loading database records: ${e.message}</td></tr>`;
    }
}

function renderDatabaseRows(records) {
    const tbody = document.getElementById('db-tbody');
    if (!tbody) return;

    const searchVal = (document.getElementById('db-search')?.value || '').toLowerCase();
    tbody.innerHTML = '';

    let count = 0;
    records.forEach(r => {
        const rowStr = `${r.case_id} ${r.date} ${r.district} ${r.crime_type} ${r.accused_name} ${r.co_accused_ids} ${r.description}`.toLowerCase();
        if (searchVal && !rowStr.includes(searchVal)) return;

        count++;
        tbody.innerHTML += `
            <tr>
                <td class="cid-tag">[${r.case_id || ''}]</td>
                <td><span style="font-family: var(--font-mono); font-size: 0.8rem;">${r.date || ''}</span></td>
                <td><strong>${r.district || ''}</strong></td>
                <td><span class="verify-badge" style="background: rgba(99,102,241,0.15); border-color: rgba(99,102,241,0.4); color: #a5b4fc;">${r.crime_type || ''}</span></td>
                <td><strong>${r.accused_name || ''}</strong></td>
                <td><span style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-secondary);">${r.co_accused_ids || 'None'}</span></td>
                <td><div class="snippet-box" style="margin: 0; color: #cbd5e1; font-size: 0.85rem; font-style: normal;">${r.description || ''}</div></td>
            </tr>
        `;
    });

    if (count === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="padding: 2rem;">No matching FIR records found.</td></tr>`;
    }
}

function filterDatabaseTable() {
    renderDatabaseRows(allDatabaseRecords);
}

async function saveCrimeRecord(event) {
    event.preventDefault();
    const message = document.getElementById('record-editor-message');
    const operation = document.getElementById('record-operation').value;
    const sessionId = localStorage.getItem('crime_session_id') || 'default';
    const record = {
        case_id: document.getElementById('record-case-id').value.trim(),
        date: document.getElementById('record-date').value || undefined,
        district: document.getElementById('record-district').value.trim() || undefined,
        crime_type: document.getElementById('record-crime-type').value.trim() || undefined,
        accused_name: document.getElementById('record-accused-name').value.trim() || undefined,
        description: document.getElementById('record-description').value.trim() || undefined
    };
    const cleanRecord = Object.fromEntries(Object.entries(record).filter(([, value]) => value !== undefined));
    const body = operation === 'create'
        ? { session_id: sessionId, record: cleanRecord }
        : { session_id: sessionId, case_id: cleanRecord.case_id, updates: Object.fromEntries(Object.entries(cleanRecord).filter(([key]) => key !== 'case_id')) };
    if (operation === 'update' && Object.keys(body.updates).length === 0) {
        message.className = 'status-box error';
        message.textContent = 'Add at least one field to update.';
        return;
    }
    message.className = 'status-box info';
    message.textContent = 'Saving record…';
    try {
        const response = await fetch(`/records/${operation}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'The record could not be saved.');
        message.className = 'status-box success';
        message.textContent = operation === 'create' ? 'Crime record added.' : 'Crime record updated.';
        await fetchDatabaseRecords();
    } catch (error) {
        message.className = 'status-box error';
        message.textContent = error.message;
    }
}

// ==========================================================================
// COMMAND CENTER STATE RESTORATION ON PAGE LOAD (`index.html`)
// ==========================================================================
function restoreCommandCenterState() {
    const chatHistory = document.getElementById('chat-history');
    if (!chatHistory) return; // Only execute on Command Center (`index.html`)

    // Clean up any legacy permanent items from previous browser sessions
    localStorage.removeItem('latestCrimeData');
    localStorage.removeItem('lastUserQueryText');
    localStorage.removeItem('lastAIAnswerText');
    localStorage.removeItem('activeInvestigationStatus');

    const storedDataStr = sessionStorage.getItem('latestCrimeData');
    const lastQueryText = sessionStorage.getItem('lastUserQueryText');
    const lastAnswerText = sessionStorage.getItem('lastAIAnswerText');
    const activeStatus = sessionStorage.getItem('activeInvestigationStatus');

    // 1. If an inquiry was running when the user navigated away to another page:
    if (activeStatus === 'running' && lastQueryText) {
        appendMessage(lastQueryText, 'user');
        appendMessage("Resuming investigation state across screen navigation... Re-launching query to ensure multi-agent blackboard completes your inquiry without loss.", 'system-loading');
        const inputEl = document.getElementById('query-input');
        if (inputEl) inputEl.value = lastQueryText;
        setTimeout(() => {
            executeInvestigation();
        }, 300);
        return;
    }

    // 2. If there is stored data from a completed query, automatically restore the entire screen!
    if (storedDataStr && activeStatus !== 'running') {
        try {
            const data = JSON.parse(storedDataStr);

            // Restore User Query and AI Answer in chat
            if (lastQueryText) {
                appendMessage(lastQueryText, 'user');
            }
            if (lastAnswerText || data.answer_text) {
                appendMessage(formatMarkdownToHTML(lastAnswerText || data.answer_text), 'ai', {
                    agents: data.agents_used || [],
                    verificationRate: data.verification_rate ?? 100.0
                });
            }

            // Restore Network Graph (`tab-graph`)
            if (data.network_graph && data.network_graph.nodes && data.network_graph.nodes.length > 0) {
                renderNetworkGraph(data.network_graph);
            } else {
                const netContainer = document.getElementById('network-graph-container');
                if (netContainer) {
                    netContainer.innerHTML = `
                        <div class="empty-state">
                            <div class="drop-icon flex-center mb-2"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></div>
                            <p>No network connections detected for this query.</p>
                        </div>
                    `;
                }
            }

            // Restore Trends & Spikes (`tab-trends`)
            renderTrends(data.trend_findings || []);

            // Restore Courtroom Audit (`tab-audit`)
            renderAudit(data.citations || [], data.verification_rate ?? 100.0, data.unsupported_claims || []);

            return;
        } catch (e) {
            console.error("Failed to restore Command Center state from localStorage:", e);
        }
    }

    // Default initial baseline states when opening Command Center before any query is run:
    renderTrends([]);
    renderAudit([], 100.0, []);
}

window.addEventListener('DOMContentLoaded', () => {
    restoreCommandCenterState();
});

// ==========================================================================
// VOICE INPUT MODULE (English en-IN / Kannada kn-IN Speech Recognition)
// ==========================================================================
let _voiceRecognition = null;
let _isVoiceRecording = false;
let _currentVoiceLang = 'en-IN'; // Default to English so English spoken queries convert to English text!

function switchMicLanguage(event) {
    if (event) event.stopPropagation(); // Don't trigger mic toggle when clicking tag
    const langTag = document.getElementById("mic-lang-tag");
    
    if (_currentVoiceLang === 'en-IN') {
        _currentVoiceLang = 'kn-IN';
        if (langTag) langTag.innerText = "KN";
    } else {
        _currentVoiceLang = 'en-IN';
        if (langTag) langTag.innerText = "EN";
    }

    if (_voiceRecognition && _isVoiceRecording) {
        _voiceRecognition.lang = _currentVoiceLang;
    }
}

function toggleVoiceInput() {
    const micBtn = document.getElementById("mic-btn");
    const queryInput = document.getElementById("query-input");

    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert("Voice recognition is supported in Google Chrome, Microsoft Edge, and modern browsers.");
        return;
    }

    if (_isVoiceRecording) {
        if (_voiceRecognition) {
            _voiceRecognition.stop();
        }
        _isVoiceRecording = false;
        if (micBtn) {
            micBtn.style.background = "var(--bg-tertiary, #1e293b)";
            micBtn.style.color = "var(--accent-cyan, #38bdf8)";
            micBtn.style.borderColor = "rgba(56,189,248,0.3)";
            micBtn.style.boxShadow = "none";
        }
        const langName = _currentVoiceLang === 'kn-IN' ? 'Kannada' : 'English';
        if (queryInput) queryInput.placeholder = `Enter investigation prompt or speak in ${langName}...`;
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    _voiceRecognition = new SpeechRecognition();
    _voiceRecognition.continuous = false;
    _voiceRecognition.interimResults = true;
    _voiceRecognition.lang = _currentVoiceLang || 'en-IN';

    _voiceRecognition.onstart = function() {
        _isVoiceRecording = true;
        if (micBtn) {
            micBtn.style.background = "#ef4444";
            micBtn.style.color = "#ffffff";
            micBtn.style.borderColor = "#ef4444";
            micBtn.style.boxShadow = "0 0 12px rgba(239, 68, 68, 0.7)";
        }
        const langName = _currentVoiceLang === 'kn-IN' ? 'Kannada (ಕನ್ನಡ)' : 'English';
        if (queryInput) queryInput.placeholder = `🎙️ Listening in ${langName}... Speak now...`;
    };

    _voiceRecognition.onresult = function(event) {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        if (queryInput && transcript) {
            queryInput.value = transcript;
        }
    };

    _voiceRecognition.onerror = function(event) {
        console.warn("[Voice] Speech recognition error:", event.error);
        _isVoiceRecording = false;
        if (micBtn) {
            micBtn.style.background = "var(--bg-tertiary, #1e293b)";
            micBtn.style.color = "var(--accent-cyan, #38bdf8)";
            micBtn.style.borderColor = "rgba(56,189,248,0.3)";
            micBtn.style.boxShadow = "none";
        }
        if (queryInput) queryInput.placeholder = "Enter investigation prompt or speak in Kannada / English...";
    };

    _voiceRecognition.onend = function() {
        _isVoiceRecording = false;
        if (micBtn) {
            micBtn.style.background = "var(--bg-tertiary, #1e293b)";
            micBtn.style.color = "var(--accent-cyan, #38bdf8)";
            micBtn.style.borderColor = "rgba(56,189,248,0.3)";
            micBtn.style.boxShadow = "none";
        }
        if (queryInput) queryInput.placeholder = "Enter investigation prompt or speak in Kannada / English...";
    };

    try {
        _voiceRecognition.start();
    } catch (err) {
        console.error("[Voice] Start error:", err);
    }
}


