// KSP CRIME AI — SHARED VERTICAL SIDEBAR & NAVIGATION COMPONENT
// Eliminates multi-page duplication, uses professional SVG vector icons (no emojis),
// and auto-highlights the current active page while syncing session/role metadata.

document.addEventListener("DOMContentLoaded", () => {
    applySavedTheme();
    renderNavigation();
    loadSessionMeta();
    initThemeToggle();
});

function applySavedTheme() {
    const theme = localStorage.getItem("crime_theme") || "dark";
    document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
}

function initThemeToggle() {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    const updateLabel = () => {
        const isLight = document.documentElement.dataset.theme === "light";
        toggle.setAttribute("aria-label", isLight ? "Switch to dark mode" : "Switch to light mode");
        toggle.querySelector(".theme-toggle-label").textContent = isLight ? "Dark mode" : "Light mode";
        toggle.classList.toggle("is-light", isLight);
    };
    toggle.addEventListener("click", () => {
        const nextTheme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
        document.documentElement.dataset.theme = nextTheme;
        localStorage.setItem("crime_theme", nextTheme);
        updateLabel();
    });
    updateLabel();
}

// SVG Icons (Lucide vector paths)
const ICONS = {
    shield: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent-cyan)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
    dashboard: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"></rect><rect width="7" height="5" x="14" y="3" rx="1"></rect><rect width="7" height="9" x="14" y="12" rx="1"></rect><rect width="7" height="5" x="3" y="16" rx="1"></rect></svg>`,
    home: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>`,
    network: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"></line><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"></line></svg>`,
    chart: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"></path><path d="m19 9-5 5-4-4-3 3"></path></svg>`,
    scale: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="M7 21h10"></path><path d="M12 3v18"></path><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"></path></svg>`,
    folder: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"></path></svg>`,
    bot: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect><path d="M2 14h2"></path><path d="M20 14h2"></path><path d="M15 13v2"></path><path d="M9 13v2"></path></svg>`,
    upload: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" x2="12" y1="3" y2="15"></line></svg>`,
    history: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path><path d="M12 7v5l4 2"></path></svg>`,
    lock: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`
};

function renderNavigation() {
    // Check if target container exists or if we need to replace existing header/sidebar
    let sidebarContainer = document.getElementById("sidebar-container");
    if (!sidebarContainer) {
        sidebarContainer = document.querySelector("aside.sidebar");
    }

    if (!sidebarContainer) {
        // If still no aside, look for old horizontal header.navbar to convert
        const oldHeader = document.querySelector("header.navbar");
        if (oldHeader) {
            sidebarContainer = document.createElement("aside");
            sidebarContainer.className = "sidebar";
            sidebarContainer.id = "sidebar-container";
            oldHeader.parentNode.insertBefore(sidebarContainer, oldHeader);
            oldHeader.remove();
        } else {
            return; // No insertion point found
        }
    } else {
        sidebarContainer.className = "sidebar";
        sidebarContainer.id = "sidebar-container";
    }

    // Determine active page
    let currentPath = window.location.pathname.split("/").pop() || "index.html";
    if (currentPath === "" || currentPath === "/") currentPath = "index.html";

    const navLinks = [
        { section: "OVERVIEW" },
        { href: "dashboard.html", label: "Dashboard", icon: ICONS.dashboard, permission: "dashboard:view" },
        { href: "index.html", label: "Command Center", icon: ICONS.home, permission: "investigation:run" },
        
        { section: "INVESTIGATION SUITE" },
        { href: "graph.html", label: "Syndicate Map", icon: ICONS.network, permission: "graph:view" },
        { href: "trends.html", label: "Crime Spikes", icon: ICONS.chart, permission: "trends:view" },
        { href: "audit.html", label: "Courtroom Audit", icon: ICONS.scale, permission: "audit:view" },
        { href: "records.html", label: "Database Records", icon: ICONS.folder, permission: "records:view" },
        
        { section: "SYSTEM & DATA" },
        { href: "agent_status.html", label: "Agent Timeline", icon: ICONS.bot, permission: "agent_status:view" },
        { href: "upload.html", label: "Dataset Ingestion", icon: ICONS.upload, permission: "dataset:upload" },
        { href: "history.html", label: "Session History", icon: ICONS.history, permission: "history:view" },
        { href: "login.html", label: "Officer Gate", icon: ICONS.lock }
    ];

    let navHtml = `
        <div class="sidebar-header">
            <div class="logo-box">
                <span class="logo-icon">${ICONS.shield}</span>
                <div>
                    <h1 class="logo-title">CRIME AI</h1>
                    <span class="logo-subtitle">KSP Intelligence Platform</span>
                </div>
            </div>
            <button class="theme-toggle" id="theme-toggle" type="button" aria-label="Switch to light mode">
                <span class="theme-toggle-mark" aria-hidden="true"></span>
                <span class="theme-toggle-label">Light mode</span>
            </button>
        </div>
        <nav class="sidebar-nav">
    `;

    const rawRole = (localStorage.getItem("crime_role") || "investigator").toLowerCase();
    const role = { state: "admin", dgp: "admin", commissioner: "senior_officer", senior: "senior_officer", inspector: "investigator", constable: "local_officer" }[rawRole] || rawRole;
    const navPermissions = {
        admin: ["dashboard:view", "investigation:run", "records:view", "graph:view", "trends:view", "audit:view", "history:view", "agent_status:view", "dataset:upload"],
        senior_officer: ["dashboard:view", "investigation:run", "records:view", "graph:view", "trends:view", "audit:view", "history:view", "agent_status:view"],
        investigator: ["dashboard:view", "investigation:run", "records:view", "graph:view", "trends:view", "audit:view", "history:view", "agent_status:view"],
        local_officer: ["dashboard:view", "investigation:run", "records:view", "history:view", "agent_status:view"]
    };
    const allowedPermissions = navPermissions[role] || navPermissions.local_officer;
    navLinks.forEach(item => {
        if (item.permission && !allowedPermissions.includes(item.permission)) return;
        if (item.section) {
            navHtml += `<div class="nav-section-label">${item.section}</div>`;
        } else {
            const isActive = (currentPath === item.href) ? "active" : "";
            navHtml += `
                <a href="${item.href}" class="nav-item ${isActive}">
                    ${item.icon}
                    <span>${item.label}</span>
                </a>
            `;
        }
    });

    navHtml += `
        </nav>
        <div class="sidebar-footer">
            <div class="user-status">
                <span class="status-dot"></span>
                <span id="sidebar-role">Role: Investigator</span>
            </div>
            <div class="district-badge" id="sidebar-district">Jurisdiction: Mysuru</div>
            <div class="session-badge" id="sidebar-session">Session: default</div>
        </div>
    `;

    sidebarContainer.innerHTML = navHtml;
    loadSessionMeta();
}

function loadSessionMeta() {
    const role = localStorage.getItem("crime_role") || "investigator";
    const district = localStorage.getItem("crime_district") || "Mysuru";
    const sid = localStorage.getItem("crime_session_id") || "default";
    
    const rElem = document.getElementById("sidebar-role");
    const dElem = document.getElementById("sidebar-district");
    const sElem = document.getElementById("sidebar-session");
    
    if (rElem) rElem.textContent = `Role: ${role.charAt(0).toUpperCase() + role.slice(1)}`;
    if (dElem) dElem.textContent = `Jurisdiction: ${district.charAt(0).toUpperCase() + district.slice(1)}`;
    if (sElem) sElem.textContent = `Session: ${sid}`;
}
