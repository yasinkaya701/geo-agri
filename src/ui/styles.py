import streamlit as st


def inject_custom_styles() -> None:
    """Premium araştırmacı odaklı tasarım sistemi.
    
    Referanslar: Nature Portfolio, Google Scholar, Notion, Linear.
    Koyu akademik tema · Inter + JetBrains Mono · Glassmorphism + subtle glow
    """
    st.markdown("""
    <style>
    /* ── Google Fonts ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,300;0,14..32,400;0,14..32,500;0,14..32,600;0,14..32,700;0,14..32,800;1,14..32,400&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap');

    /* ── Design Tokens ── */
    :root {
        --bg-base:       #080C14;
        --bg-surface:    #0D1117;
        --bg-card:       #111827;
        --bg-card-hover: #161F2E;
        --bg-input:      #1C2333;
        --bg-muted:      #1A2236;

        --border:        rgba(255,255,255,0.07);
        --border-strong: rgba(255,255,255,0.13);
        --border-accent: rgba(16,185,129,0.35);

        --text-primary:  #F0F6FF;
        --text-secondary:#94A3B8;
        --text-muted:    #5B6F8A;
        --text-code:     #7DD3FC;

        --accent-green:  #10B981;
        --accent-green2: #34D399;
        --accent-blue:   #3B82F6;
        --accent-indigo: #6366F1;
        --accent-amber:  #F59E0B;
        --accent-red:    #EF4444;
        --accent-cyan:   #06B6D4;

        --glow-green: 0 0 20px rgba(16,185,129,0.15), 0 0 60px rgba(16,185,129,0.06);
        --glow-blue:  0 0 20px rgba(59,130,246,0.15),  0 0 60px rgba(59,130,246,0.06);

        --radius-sm: 6px;
        --radius-md: 10px;
        --radius-lg: 16px;
        --radius-xl: 22px;

        --shadow-card: 0 1px 3px rgba(0,0,0,0.4), 0 4px 16px rgba(0,0,0,0.3);
        --shadow-float:0 8px 32px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3);

        --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
        --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
        --font-head: 'Space Grotesk', 'Inter', sans-serif;

        --transition: 0.2s cubic-bezier(0.4,0,0.2,1);
    }

    /* ── Global Reset ── */
    html, body, [data-testid="stAppViewContainer"],
    [data-testid="stMain"], .main { 
        background-color: var(--bg-base) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-sans) !important;
    }

    /* Hide Streamlit chrome */
    #MainMenu, footer, header,
    [data-testid="stDeployButton"],
    [data-testid="stToolbar"] { display: none !important; }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 4px; height: 4px; }
    ::-webkit-scrollbar-track { background: var(--bg-surface); }
    ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 99px; }

    /* ── Typography ── */
    h1,h2,h3,h4,h5,h6 {
        font-family: var(--font-head) !important;
        color: var(--text-primary) !important;
        letter-spacing: -0.02em;
    }
    p, li, span { color: var(--text-secondary); line-height: 1.7; }
    code, pre {
        font-family: var(--font-mono) !important;
        background: var(--bg-input);
        color: var(--text-code);
        border-radius: var(--radius-sm);
        padding: 2px 6px;
        font-size: 0.85em;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: var(--bg-surface) !important;
        border-right: 1px solid var(--border) !important;
        padding-top: 0 !important;
    }
    [data-testid="stSidebar"]::before {
        content: '';
        display: block;
        height: 3px;
        background: linear-gradient(90deg, var(--accent-green), var(--accent-blue), var(--accent-indigo));
    }
    [data-testid="stSidebarNav"] { display: none !important; }

    /* ── App Header Bar ── */
    .app-header {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 20px 0 24px;
        border-bottom: 1px solid var(--border);
        margin-bottom: 28px;
    }
    .app-header-icon {
        width: 44px; height: 44px;
        background: linear-gradient(135deg, var(--accent-green), var(--accent-blue));
        border-radius: var(--radius-md);
        display: flex; align-items: center; justify-content: center;
        font-size: 22px; flex-shrink: 0;
        box-shadow: var(--glow-green);
    }
    .app-header-title {
        font-family: var(--font-head) !important;
        font-size: 1.35rem; font-weight: 700;
        color: var(--text-primary) !important;
        letter-spacing: -0.03em; margin: 0;
    }
    .app-header-sub {
        font-size: 0.78rem; color: var(--text-muted);
        letter-spacing: 0.06em; text-transform: uppercase;
        font-weight: 500; margin: 0;
    }
    .app-header-badges { display: flex; gap: 8px; margin-left: auto; }
    .badge {
        font-family: var(--font-mono); font-size: 0.7rem; font-weight: 500;
        padding: 3px 10px; border-radius: 99px;
        border: 1px solid var(--border-strong);
        color: var(--text-secondary); background: var(--bg-muted);
        letter-spacing: 0.02em;
    }
    .badge-green { border-color: var(--border-accent); color: var(--accent-green); background: rgba(16,185,129,0.08); }
    .badge-blue  { border-color: rgba(59,130,246,0.3); color: var(--accent-blue); background: rgba(59,130,246,0.08); }

    /* ── Cards ── */
    .card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 24px;
        box-shadow: var(--shadow-card);
        transition: border-color var(--transition), box-shadow var(--transition);
        margin-bottom: 16px;
    }
    .card:hover { border-color: var(--border-strong); }
    .card-accent {
        border-color: var(--border-accent);
        box-shadow: var(--shadow-card), var(--glow-green);
    }
    .card-title {
        font-family: var(--font-head);
        font-size: 0.95rem; font-weight: 600;
        color: var(--text-primary); margin-bottom: 4px;
        display: flex; align-items: center; gap: 8px;
    }
    .card-subtitle {
        font-size: 0.8rem; color: var(--text-muted);
        margin-bottom: 18px; line-height: 1.5;
    }

    /* ── Stat Cards ── */
    .stat-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr));
        gap: 12px; margin-bottom: 20px;
    }
    .stat-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: 16px; text-align: center;
        transition: all var(--transition);
    }
    .stat-card:hover {
        border-color: var(--border-accent);
        box-shadow: var(--glow-green);
        transform: translateY(-1px);
    }
    .stat-value {
        font-family: var(--font-head); font-size: 1.6rem; font-weight: 700;
        color: var(--text-primary); letter-spacing: -0.03em; display: block;
    }
    .stat-label {
        font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;
        letter-spacing: 0.08em; font-weight: 500; margin-top: 2px; display: block;
    }
    .stat-delta {
        font-family: var(--font-mono); font-size: 0.72rem;
        margin-top: 4px; display: block;
    }
    .delta-up   { color: var(--accent-green); }
    .delta-down { color: var(--accent-red); }
    .delta-flat { color: var(--text-muted); }

    /* ── Tabs ── */
    [data-testid="stTabs"] > div > div > div > button {
        font-family: var(--font-sans) !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        color: var(--text-muted) !important;
        border-radius: var(--radius-sm) !important;
        padding: 8px 14px !important;
        transition: all var(--transition) !important;
        border: none !important;
        background: transparent !important;
    }
    [data-testid="stTabs"] > div > div > div > button:hover {
        color: var(--text-primary) !important;
        background: var(--bg-muted) !important;
    }
    [data-testid="stTabs"] > div > div > div > button[aria-selected="true"] {
        color: var(--accent-green) !important;
        background: rgba(16,185,129,0.1) !important;
        border-bottom: 2px solid var(--accent-green) !important;
    }
    [data-testid="stTabsContent"] {
        border: 1px solid var(--border) !important;
        border-radius: 0 var(--radius-md) var(--radius-md) var(--radius-md) !important;
        background: var(--bg-surface) !important;
        padding: 20px !important;
    }

    /* ── Buttons ── */
    .stButton > button {
        font-family: var(--font-sans) !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        border-radius: var(--radius-md) !important;
        padding: 10px 20px !important;
        transition: all var(--transition) !important;
        border: 1px solid var(--border-strong) !important;
        background: var(--bg-card) !important;
        color: var(--text-primary) !important;
        letter-spacing: 0.01em !important;
    }
    .stButton > button:hover {
        background: var(--bg-card-hover) !important;
        border-color: var(--border-accent) !important;
        box-shadow: var(--glow-green) !important;
        transform: translateY(-1px) !important;
    }
    [data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, var(--accent-green), #059669) !important;
        border-color: var(--accent-green) !important;
        color: #fff !important;
        box-shadow: 0 2px 8px rgba(16,185,129,0.3) !important;
    }
    [data-testid="baseButton-primary"]:hover {
        background: linear-gradient(135deg, var(--accent-green2), var(--accent-green)) !important;
        box-shadow: 0 4px 16px rgba(16,185,129,0.45) !important;
    }

    /* ── Form inputs ── */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stDateInput > div > div > input,
    .stSelectbox > div > div > div,
    .stMultiSelect > div > div > div {
        background: var(--bg-input) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: var(--radius-md) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.85rem !important;
        transition: border-color var(--transition) !important;
    }
    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > div:focus {
        border-color: var(--accent-green) !important;
        box-shadow: 0 0 0 3px rgba(16,185,129,0.12) !important;
    }
    label { color: var(--text-secondary) !important; font-size: 0.8rem !important; font-weight: 500 !important; }

    /* ── Slider ── */
    [data-testid="stSlider"] > div > div > div > div {
        background: var(--accent-green) !important;
    }
    [data-testid="stSlider"] > div > div > div > div > div {
        background: var(--bg-card) !important;
        border: 2px solid var(--accent-green) !important;
        box-shadow: var(--glow-green) !important;
    }

    /* ── Metric ── */
    [data-testid="metric-container"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-md) !important;
        padding: 16px !important;
        transition: all var(--transition) !important;
    }
    [data-testid="metric-container"]:hover {
        border-color: var(--border-accent) !important;
        box-shadow: var(--glow-green) !important;
    }
    [data-testid="stMetricLabel"] { color: var(--text-muted) !important; font-size: 0.72rem !important; text-transform: uppercase !important; letter-spacing: 0.08em !important; }
    [data-testid="stMetricValue"] { color: var(--text-primary) !important; font-family: var(--font-head) !important; font-size: 1.6rem !important; font-weight: 700 !important; }
    [data-testid="stMetricDelta"] svg { display: none; }

    /* ── Alerts / Info ── */
    .stAlert {
        border-radius: var(--radius-md) !important;
        border: 1px solid var(--border) !important;
        background: var(--bg-card) !important;
        font-size: 0.83rem !important;
    }
    .stInfo    { border-color: rgba(59,130,246,0.3) !important; }
    .stSuccess { border-color: var(--border-accent) !important; }
    .stWarning { border-color: rgba(245,158,11,0.3) !important; }
    .stError   { border-color: rgba(239,68,68,0.3) !important; }

    /* ── Download Button ── */
    .stDownloadButton > button {
        background: var(--bg-muted) !important;
        border: 1px solid var(--border-strong) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-mono) !important;
        font-size: 0.78rem !important;
        border-radius: var(--radius-md) !important;
        transition: all var(--transition) !important;
    }
    .stDownloadButton > button:hover {
        border-color: var(--accent-blue) !important;
        color: var(--accent-blue) !important;
        box-shadow: var(--glow-blue) !important;
    }

    /* ── Progress bar ── */
    .stProgress > div > div > div { background: var(--accent-green) !important; border-radius: 99px !important; }
    .stProgress > div > div { background: var(--bg-input) !important; border-radius: 99px !important; }

    /* ── Spinner ── */
    [data-testid="stSpinner"] { color: var(--accent-green) !important; }

    /* ── Expander ── */
    [data-testid="stExpander"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-md) !important;
    }
    [data-testid="stExpander"] summary {
        color: var(--text-secondary) !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
    }

    /* ── Dataframe / Table ── */
    [data-testid="stDataFrame"] > div {
        border: 1px solid var(--border) !important;
        border-radius: var(--radius-md) !important;
        overflow: hidden !important;
    }
    .dvn-scroller { background: var(--bg-surface) !important; }

    /* ── Sidebar content ── */
    .sidebar-logo {
        display: flex; align-items: center; gap: 12px;
        padding: 20px 16px 16px;
        border-bottom: 1px solid var(--border);
        margin-bottom: 16px;
    }
    .sidebar-logo-icon {
        width: 36px; height: 36px;
        background: linear-gradient(135deg, var(--accent-green), var(--accent-blue));
        border-radius: 8px; display: flex; align-items: center;
        justify-content: center; font-size: 18px; flex-shrink: 0;
    }
    .sidebar-logo-text { font-family: var(--font-head); font-size: 1rem; font-weight: 700; color: var(--text-primary); }
    .sidebar-logo-sub  { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.1em; }

    .sidebar-section-label {
        font-size: 0.65rem; font-weight: 600; color: var(--text-muted);
        text-transform: uppercase; letter-spacing: 0.1em;
        padding: 12px 16px 6px; margin: 0;
    }

    /* ── Map container ── */
    .map-container {
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        overflow: hidden;
        box-shadow: var(--shadow-float);
    }

    /* ── Section divider ── */
    .section-divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
        margin: 24px 0;
    }

    /* ── Status pill ── */
    .status-pill {
        display: inline-flex; align-items: center; gap: 6px;
        font-family: var(--font-mono); font-size: 0.72rem; font-weight: 500;
        padding: 4px 12px; border-radius: 99px;
        border: 1px solid var(--border);
    }
    .status-pill::before { content: ''; width: 6px; height: 6px; border-radius: 50%; }
    .status-live   { border-color: var(--border-accent); color: var(--accent-green); }
    .status-live::before { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); animation: pulse 2s infinite; }
    .status-idle   { color: var(--text-muted); }
    .status-idle::before { background: var(--text-muted); }

    @keyframes pulse {
        0%,100% { opacity: 1; } 50% { opacity: 0.4; }
    }

    /* ── Glow cards (highlight) ── */
    .card-glow-green { box-shadow: var(--glow-green); border-color: var(--border-accent); }
    .card-glow-blue  { box-shadow: var(--glow-blue);  border-color: rgba(59,130,246,0.35); }

    /* ── Cesium / iframe container ── */
    .cesium-container {
        border: 1px solid var(--border-accent);
        border-radius: var(--radius-lg);
        overflow: hidden;
        box-shadow: var(--shadow-float), var(--glow-green);
        position: relative;
    }

    /* ── Horizontal rule override ── */
    hr { border-color: var(--border) !important; margin: 20px 0 !important; }

    /* ── Checkbox / Radio ── */
    [data-testid="stCheckbox"] label { color: var(--text-secondary) !important; font-size: 0.83rem !important; }
    [data-testid="stRadio"] label    { color: var(--text-secondary) !important; font-size: 0.83rem !important; }

    /* ── Column gaps ── */
    [data-testid="stColumn"] { padding: 0 8px !important; }
    [data-testid="stColumn"]:first-child { padding-left: 0 !important; }
    [data-testid="stColumn"]:last-child  { padding-right: 0 !important; }

    /* ── Scrollable sidebar ── */
    [data-testid="stSidebar"] > div { overflow-y: auto !important; }

    /* ── Plotly dark theme fix ── */
    .js-plotly-plot .plotly { background: transparent !important; }

    </style>
    """, unsafe_allow_html=True)


def app_header(title: str, subtitle: str, version: str = "v2.0", status: str = "live") -> None:
    """Sayfanın üst kısmındaki profesyonel header bileşeni."""
    status_html = (
        '<span class="status-pill status-live">LIVE</span>'
        if status == "live"
        else '<span class="status-pill status-idle">IDLE</span>'
    )
    st.markdown(f"""
    <div class="app-header">
        <div class="app-header-icon">🛰️</div>
        <div>
            <p class="app-header-title">{title}</p>
            <p class="app-header-sub">{subtitle}</p>
        </div>
        <div class="app-header-badges">
            {status_html}
            <span class="badge badge-green">GEE Connected</span>
            <span class="badge badge-blue">Sentinel-2</span>
            <span class="badge">{version}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


def card(title: str = "", subtitle: str = "", accent: bool = False) -> None:
    """Glass card bileşeni başlangıcı."""
    cls = "card card-accent card-glow-green" if accent else "card"
    st.markdown(f"""<div class="{cls}">
        {"" if not title else f'<div class="card-title">{title}</div>'}
        {"" if not subtitle else f'<div class="card-subtitle">{subtitle}</div>'}
    """, unsafe_allow_html=True)


def end_card() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def stat_grid(stats: list) -> None:
    """stats = [{"label": str, "value": str, "delta": str, "delta_type": "up"|"down"|"flat"}, ...]"""
    items = ""
    for s in stats:
        delta_cls = f"delta-{s.get('delta_type','flat')}"
        delta_sym = "↑" if s.get("delta_type") == "up" else ("↓" if s.get("delta_type") == "down" else "—")
        delta_html = f'<span class="stat-delta {delta_cls}">{delta_sym} {s.get("delta","")}</span>' if s.get("delta") else ""
        items += f"""
        <div class="stat-card">
            <span class="stat-value">{s["value"]}</span>
            <span class="stat-label">{s["label"]}</span>
            {delta_html}
        </div>"""
    st.markdown(f'<div class="stat-grid">{items}</div>', unsafe_allow_html=True)


def section_divider() -> None:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
