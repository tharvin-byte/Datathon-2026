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
        const workspace  = document.getElementById('workspace');
        const handle     = document.getElementById('panel-resize-handle');
        if (!workspace || !handle) return;

        // Restore saved width from previous session
        const savedWidth = localStorage.getItem('chatPanelWidth');
        if (savedWidth) workspace.style.setProperty('--chat-panel-width', savedWidth);

        let isDragging = false;
        let startX     = 0;
        let startWidth = 0;

        handle.addEventListener('mousedown', (e) => {
            isDragging = true;
            startX     = e.clientX;
            startWidth = workspace.getBoundingClientRect().left
                       ? parseInt(getComputedStyle(workspace).getPropertyValue('--chat-panel-width') || '420', 10)
                       : 420;
            // Measure actual current width from the chat panel itself
            const chatPanel = document.getElementById('chat-panel');
            if (chatPanel) startWidth = chatPanel.getBoundingClientRect().width;

            handle.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const delta    = e.clientX - startX;
            const minWidth = 280;
            const maxWidth = Math.floor(window.innerWidth * 0.70);
            const newWidth = Math.min(maxWidth, Math.max(minWidth, startWidth + delta));
            workspace.style.setProperty('--chat-panel-width', newWidth + 'px');
        });

        document.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            handle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            // Persist the chosen width so it survives refresh
            const w = workspace.style.getPropertyValue('--chat-panel-width');
            if (w) localStorage.setItem('chatPanelWidth', w);
            // Redraw chart/graph if visible
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
                        afterLabel: function(context) {
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
                        label: function(context) {
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

        const response = await fetch('/api/investigate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

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
    planner_agent:  { cssClass: 'agent-planner',  label: 'Planner Agent'   },
    query_agent:    { cssClass: 'agent-query',    label: 'Query Agent'     },
    link_agent:     { cssClass: 'agent-link',     label: 'Link Agent'      },
    trend_agent:    { cssClass: 'agent-trend',    label: 'Trend Agent'     },
    risk_agent:     { cssClass: 'agent-risk',     label: 'Risk Agent'      },
    verifier_agent: { cssClass: 'agent-verifier', label: 'Verifier Agent'  },
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

    msgDiv.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-content">${content}${telemetryHTML}</div>
    `;

    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function removeLoadingMessage() {
    const loadingBubble = document.getElementById('loading-bubble');
    if (loadingBubble) loadingBubble.remove();
}

// Basic Markdown to HTML formatting for Composer Output
function formatMarkdownToHTML(md) {
    return md
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        .replace(/\n/g, '<br>');
}

// 1. Vis.js Network Graph Renderer
function renderNetworkGraph(graphData) {
    const container = document.getElementById('network-graph-container');
    container.innerHTML = ''; // Clear previous

    const visNodes = graphData.nodes.map(n => ({
        id: n.id,
        label: n.label || n.name || n.id,
        shape: ['person', 'accused', 'victim'].includes(n.type) ? 'dot' : 'box',
        size: ['person', 'accused', 'victim'].includes(n.type) ? 24 : 18,
        color: {
            background: ['person', 'accused', 'victim'].includes(n.type) ? '#00f2fe' : '#6366f1',
            border: '#fff',
            highlight: { background: '#4facfe', border: '#fff' }
        },
        font: { color: '#f8fafc', face: 'Inter', size: 14 }
    }));

    const visEdges = graphData.edges.map(e => ({
        from: e.source,
        to: e.target,
        label: e.basis || '',
        color: { color: 'rgba(99, 102, 241, 0.6)', highlight: '#00f2fe' },
        font: { color: '#94a3b8', size: 11, align: 'middle' },
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        width: 2
    }));

    const data = {
        nodes: new vis.DataSet(visNodes),
        edges: new vis.DataSet(visEdges)
    };

    const options = {
        physics: {
            forceAtlas2Based: {
                gravitationalConstant: -60,
                centralGravity: 0.01,
                springLength: 120,
                springConstant: 0.08
            },
            maxVelocity: 50,
            solver: 'forceAtlas2Based',
            timestep: 0.35,
            stabilization: { iterations: 150 }
        },
        interaction: { hover: true, zoomView: true }
    };

    networkInstance = new vis.Network(container, data, options);
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
                        afterLabel: function(context) {
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
    const container = document.getElementById('full-graph-container');
    if (!container) return;
    container.innerHTML = '';

    const visNodes = graphData.nodes.map(n => ({
        id: n.id,
        label: n.label || n.name || n.id,
        shape: ['person', 'accused', 'victim'].includes(n.type) ? 'dot' : 'box',
        size: ['person', 'accused', 'victim'].includes(n.type) ? 28 : 22,
        color: {
            background: ['person', 'accused', 'victim'].includes(n.type) ? '#00f2fe' : '#6366f1',
            border: '#fff',
            highlight: { background: '#4facfe', border: '#fff' }
        },
        font: { color: '#f8fafc', face: 'Inter', size: 15 }
    }));

    const visEdges = graphData.edges.map(e => ({
        from: e.source,
        to: e.target,
        label: e.basis || '',
        color: { color: 'rgba(99, 102, 241, 0.7)', highlight: '#00f2fe' },
        font: { color: '#94a3b8', size: 12, align: 'middle' },
        arrows: { to: { enabled: true, scaleFactor: 0.6 } },
        width: 2.5
    }));

    const data = {
        nodes: new vis.DataSet(visNodes),
        edges: new vis.DataSet(visEdges)
    };

    const options = {
        physics: {
            forceAtlas2Based: {
                gravitationalConstant: -70,
                centralGravity: 0.01,
                springLength: 140,
                springConstant: 0.08
            },
            maxVelocity: 50,
            solver: 'forceAtlas2Based',
            timestep: 0.35,
            stabilization: { iterations: 150 }
        },
        interaction: { hover: true, zoomView: true }
    };

    networkInstance = new vis.Network(container, data, options);
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
        const res = await fetch(`/api/records?dataset=${encodeURIComponent(dsKey)}`);
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

        } catch (e) {
            console.error("Failed to restore Command Center state from localStorage:", e);
        }
    }
}

window.addEventListener('DOMContentLoaded', () => {
    restoreCommandCenterState();
});

