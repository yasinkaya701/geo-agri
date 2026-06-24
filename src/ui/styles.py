import streamlit as st


def inject_custom_styles() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ══════════════════════════════════════════
   DESIGN TOKENS
══════════════════════════════════════════ */
:root {
  --bg0:        #05070D;
  --bg1:        #0A0E1A;
  --bg2:        #0F1422;
  --bg3:        #141929;
  --bg4:        #1A2035;
  --bg-hover:   #1F2740;

  --border-0:   rgba(255,255,255,0.04);
  --border-1:   rgba(255,255,255,0.08);
  --border-2:   rgba(255,255,255,0.14);
  --border-g:   rgba(52,211,153,0.30);

  --t0: #FFFFFF;
  --t1: #E2E8F0;
  --t2: #94A3B8;
  --t3: #475569;
  --t4: #2D3F55;

  --g0: #34D399;   /* emerald 400 */
  --g1: #10B981;   /* emerald 500 */
  --g2: #059669;   /* emerald 600 */
  --b0: #60A5FA;   /* blue 400 */
  --b1: #3B82F6;   /* blue 500 */
  --i0: #818CF8;   /* indigo 400 */
  --a0: #FBBF24;   /* amber 400 */
  --r0: #F87171;   /* red 400 */
  --c0: #22D3EE;   /* cyan 400 */

  --glow-g: 0 0 0 1px rgba(52,211,153,.2), 0 4px 24px rgba(16,185,129,.15);
  --glow-b: 0 0 0 1px rgba(59,130,246,.2), 0 4px 24px rgba(59,130,246,.12);
  --shadow-card: 0 1px 2px rgba(0,0,0,.5), 0 4px 12px rgba(0,0,0,.3);
  --shadow-xl: 0 8px 40px rgba(0,0,0,.6);

  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 16px;
  --r-xl: 20px;
  --r-pill: 999px;

  --f-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --f-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  --ease: cubic-bezier(.4,0,.2,1);
}

/* ══════════════════════════════════════════
   RESET & BASE
══════════════════════════════════════════ */
*, *::before, *::after { box-sizing: border-box; }

html, body {
  margin: 0; padding: 0;
  font-family: var(--f-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* App shells */
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
.main, .block-container,
[data-testid="stMainBlockContainer"] {
  background: var(--bg0) !important;
  color: var(--t1) !important;
  font-family: var(--f-sans) !important;
}

.block-container, [data-testid="stMainBlockContainer"] {
  padding: 2rem 2.5rem 4rem !important;
  max-width: 1400px !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header,
[data-testid="stDeployButton"],
[data-testid="stStatusWidget"],
[data-testid="stToolbar"] { display: none !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg1); }
::-webkit-scrollbar-thumb { background: var(--bg4); border-radius: 99px; }
::-webkit-scrollbar-thumb:hover { background: var(--t3); }

/* ══════════════════════════════════════════
   TYPOGRAPHY
══════════════════════════════════════════ */
h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {
  font-family: var(--f-sans) !important;
  color: var(--t0) !important;
  font-weight: 700 !important;
  letter-spacing: -0.025em !important;
  margin-bottom: 0.5rem !important;
}

p, li, [data-testid="stMarkdownContainer"] p {
  color: var(--t2) !important;
  font-size: 0.88rem !important;
  line-height: 1.75 !important;
}

strong, b { color: var(--t1) !important; font-weight: 600 !important; }

code, kbd, [data-testid="stMarkdownContainer"] code {
  font-family: var(--f-mono) !important;
  font-size: 0.8em !important;
  background: var(--bg4) !important;
  color: var(--c0) !important;
  border: 1px solid var(--border-1) !important;
  border-radius: 5px !important;
  padding: 1px 6px !important;
}

hr { border: none !important; border-top: 1px solid var(--border-1) !important; margin: 1.5rem 0 !important; }

/* ══════════════════════════════════════════
   SIDEBAR
══════════════════════════════════════════ */
[data-testid="stSidebar"] {
  background: var(--bg1) !important;
  border-right: 1px solid var(--border-1) !important;
  width: 280px !important;
}
[data-testid="stSidebar"] > div:first-child {
  padding: 0 !important;
}
[data-testid="stSidebar"] section {
  padding: 0 !important;
}
[data-testid="stSidebarContent"] {
  padding: 0 !important;
}
[data-testid="stSidebarNav"] { display: none !important; }

/* Sidebar inner content */
[data-testid="stSidebar"] .block-container,
[data-testid="stSidebar"] [data-testid="stMainBlockContainer"],
[data-testid="stSidebar"] .element-container {
  background: transparent !important;
  padding: 0 !important;
}

[data-testid="stSidebar"] label {
  color: var(--t3) !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
}

[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stRadio label {
  color: var(--t2) !important;
  font-size: 0.78rem !important;
  text-transform: none !important;
  letter-spacing: 0 !important;
  font-weight: 500 !important;
}

/* ══════════════════════════════════════════
   BUTTONS — complete override
══════════════════════════════════════════ */
/* Base button */
.stButton > button,
button[kind="secondary"] {
  font-family: var(--f-sans) !important;
  font-size: 0.84rem !important;
  font-weight: 600 !important;
  color: var(--t1) !important;
  background: var(--bg3) !important;
  border: 1px solid var(--border-2) !important;
  border-radius: var(--r-md) !important;
  padding: 0.55rem 1.2rem !important;
  transition: all 0.15s var(--ease) !important;
  cursor: pointer !important;
  letter-spacing: 0.01em !important;
  box-shadow: 0 1px 2px rgba(0,0,0,.4) !important;
  line-height: 1.4 !important;
  white-space: nowrap !important;
}
.stButton > button:hover {
  background: var(--bg4) !important;
  border-color: var(--border-g) !important;
  color: var(--t0) !important;
  box-shadow: var(--glow-g) !important;
  transform: translateY(-1px) !important;
}
.stButton > button:active {
  transform: translateY(0) !important;
  box-shadow: none !important;
}

/* Primary button */
.stButton > button[kind="primary"],
[data-testid="baseButton-primary"],
button[data-baseweb="button"][kind="primary"] {
  background: linear-gradient(135deg, var(--g1) 0%, var(--g2) 100%) !important;
  border: 1px solid var(--g1) !important;
  color: #fff !important;
  box-shadow: 0 2px 10px rgba(16,185,129,.35) !important;
  font-weight: 700 !important;
}
.stButton > button[kind="primary"]:hover,
[data-testid="baseButton-primary"]:hover {
  background: linear-gradient(135deg, var(--g0) 0%, var(--g1) 100%) !important;
  box-shadow: 0 4px 20px rgba(52,211,153,.45), 0 0 0 1px rgba(52,211,153,.3) !important;
  transform: translateY(-2px) !important;
  border-color: var(--g0) !important;
}

/* Download button */
.stDownloadButton > button {
  font-family: var(--f-mono) !important;
  font-size: 0.78rem !important;
  font-weight: 500 !important;
  background: var(--bg2) !important;
  border: 1px solid var(--border-2) !important;
  color: var(--t2) !important;
  border-radius: var(--r-md) !important;
  padding: 0.5rem 1rem !important;
  transition: all 0.15s var(--ease) !important;
}
.stDownloadButton > button:hover {
  border-color: var(--b0) !important;
  color: var(--b0) !important;
  background: rgba(59,130,246,.08) !important;
  box-shadow: var(--glow-b) !important;
}

/* ══════════════════════════════════════════
   FORM INPUTS
══════════════════════════════════════════ */
/* Text inputs */
.stTextInput input,
.stNumberInput input,
.stDateInput input,
.stTextArea textarea {
  font-family: var(--f-sans) !important;
  font-size: 0.84rem !important;
  color: var(--t0) !important;
  background: var(--bg2) !important;
  border: 1px solid var(--border-2) !important;
  border-radius: var(--r-md) !important;
  padding: 0.5rem 0.75rem !important;
  transition: border-color 0.15s var(--ease), box-shadow 0.15s var(--ease) !important;
  caret-color: var(--g0) !important;
  outline: none !important;
}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
  border-color: var(--g1) !important;
  box-shadow: 0 0 0 3px rgba(16,185,129,.15) !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
  color: var(--t3) !important;
}

/* Select boxes */
.stSelectbox > div > div,
.stMultiSelect > div > div > div {
  font-family: var(--f-sans) !important;
  font-size: 0.84rem !important;
  background: var(--bg2) !important;
  border: 1px solid var(--border-2) !important;
  border-radius: var(--r-md) !important;
  color: var(--t0) !important;
}
.stSelectbox > div > div:focus-within,
.stMultiSelect > div > div > div:focus-within {
  border-color: var(--g1) !important;
  box-shadow: 0 0 0 3px rgba(16,185,129,.15) !important;
}

/* Dropdown menu */
[data-baseweb="popover"] {
  background: var(--bg3) !important;
  border: 1px solid var(--border-2) !important;
  border-radius: var(--r-md) !important;
  box-shadow: var(--shadow-xl) !important;
  overflow: hidden !important;
}
[data-baseweb="select"] [aria-selected="true"],
[data-baseweb="menu"] li:hover {
  background: var(--bg4) !important;
  color: var(--t0) !important;
}

/* Labels */
.stTextInput label, .stSelectbox label, .stNumberInput label,
.stDateInput label, .stTextArea label, .stMultiSelect label,
.stCheckbox label, .stRadio label, .stSlider label {
  font-family: var(--f-sans) !important;
  font-size: 0.78rem !important;
  font-weight: 600 !important;
  color: var(--t2) !important;
  letter-spacing: 0.01em !important;
  margin-bottom: 0.3rem !important;
}

/* ══════════════════════════════════════════
   SLIDERS
══════════════════════════════════════════ */
.stSlider > div > div > div > div {
  background: var(--g1) !important;
  height: 4px !important;
  border-radius: 2px !important;
}
.stSlider > div > div > div {
  background: var(--bg4) !important;
  height: 4px !important;
  border-radius: 2px !important;
}
/* Thumb */
.stSlider [data-testid="stThumbValue"] {
  background: var(--bg3) !important;
  border: 2px solid var(--g1) !important;
  border-radius: 50% !important;
  width: 16px !important; height: 16px !important;
  box-shadow: 0 0 8px rgba(16,185,129,.4) !important;
  cursor: grab !important;
}
.stSlider [data-testid="stTickBarMin"],
.stSlider [data-testid="stTickBarMax"] {
  color: var(--t3) !important;
  font-size: 0.72rem !important;
  font-family: var(--f-mono) !important;
}

/* ══════════════════════════════════════════
   RADIO & CHECKBOX
══════════════════════════════════════════ */
.stRadio > div {
  gap: 4px !important;
}
.stRadio > div > label {
  background: var(--bg2) !important;
  border: 1px solid var(--border-1) !important;
  border-radius: var(--r-md) !important;
  padding: 0.5rem 0.85rem !important;
  color: var(--t2) !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
  transition: all 0.15s var(--ease) !important;
  cursor: pointer !important;
}
.stRadio > div > label:hover {
  background: var(--bg3) !important;
  border-color: var(--border-2) !important;
  color: var(--t1) !important;
}
.stRadio > div > label[data-baseweb="radio"]:has(input:checked),
.stRadio > div > label[aria-checked="true"] {
  background: rgba(16,185,129,.12) !important;
  border-color: var(--g1) !important;
  color: var(--g0) !important;
}

/* ══════════════════════════════════════════
   TABS
══════════════════════════════════════════ */
[data-testid="stTabs"] [role="tablist"] {
  background: var(--bg1) !important;
  border-bottom: 1px solid var(--border-1) !important;
  gap: 2px !important;
  padding: 0 4px !important;
}
[data-testid="stTabs"] button[role="tab"] {
  font-family: var(--f-sans) !important;
  font-size: 0.81rem !important;
  font-weight: 500 !important;
  color: var(--t3) !important;
  background: transparent !important;
  border: none !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  padding: 0.65rem 1rem !important;
  transition: all 0.15s var(--ease) !important;
  white-space: nowrap !important;
}
[data-testid="stTabs"] button[role="tab"]:hover {
  color: var(--t1) !important;
  background: var(--bg2) !important;
  border-radius: var(--r-sm) var(--r-sm) 0 0 !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
  color: var(--g0) !important;
  border-bottom-color: var(--g1) !important;
  font-weight: 600 !important;
}
[data-testid="stTabsContent"] {
  background: var(--bg1) !important;
  border: 1px solid var(--border-1) !important;
  border-top: none !important;
  border-radius: 0 0 var(--r-md) var(--r-md) !important;
  padding: 1.5rem !important;
}

/* ══════════════════════════════════════════
   METRICS
══════════════════════════════════════════ */
[data-testid="metric-container"] {
  background: var(--bg2) !important;
  border: 1px solid var(--border-1) !important;
  border-radius: var(--r-lg) !important;
  padding: 1.1rem 1.25rem !important;
  transition: border-color .15s var(--ease), box-shadow .15s var(--ease) !important;
  position: relative !important;
  overflow: hidden !important;
}
[data-testid="metric-container"]::before {
  content: '' !important;
  position: absolute !important;
  top: 0 !important; left: 0 !important; right: 0 !important;
  height: 2px !important;
  background: linear-gradient(90deg, var(--g1), var(--b1)) !important;
  opacity: 0 !important;
  transition: opacity .15s !important;
}
[data-testid="metric-container"]:hover {
  border-color: var(--border-g) !important;
  box-shadow: var(--glow-g) !important;
}
[data-testid="metric-container"]:hover::before { opacity: 1 !important; }

[data-testid="stMetricLabel"] {
  font-size: 0.7rem !important;
  font-weight: 700 !important;
  color: var(--t3) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.1em !important;
}
[data-testid="stMetricValue"] {
  font-size: 1.75rem !important;
  font-weight: 800 !important;
  color: var(--t0) !important;
  letter-spacing: -0.04em !important;
  font-family: var(--f-sans) !important;
  line-height: 1.2 !important;
}
[data-testid="stMetricDelta"] {
  font-family: var(--f-mono) !important;
  font-size: 0.75rem !important;
  font-weight: 500 !important;
}

/* ══════════════════════════════════════════
   ALERTS
══════════════════════════════════════════ */
[data-testid="stAlert"] {
  background: var(--bg2) !important;
  border-radius: var(--r-md) !important;
  border: 1px solid var(--border-1) !important;
  padding: 0.75rem 1rem !important;
  font-size: 0.83rem !important;
}
[data-testid="stInfo"] {
  background: rgba(59,130,246,.08) !important;
  border-color: rgba(59,130,246,.25) !important;
}
[data-testid="stSuccess"] {
  background: rgba(16,185,129,.08) !important;
  border-color: rgba(16,185,129,.25) !important;
}
[data-testid="stWarning"] {
  background: rgba(251,191,36,.07) !important;
  border-color: rgba(251,191,36,.22) !important;
}
[data-testid="stError"] {
  background: rgba(248,113,113,.08) !important;
  border-color: rgba(248,113,113,.25) !important;
}
[data-testid="stAlert"] p { color: inherit !important; font-size: 0.83rem !important; }

/* ══════════════════════════════════════════
   EXPANDER
══════════════════════════════════════════ */
[data-testid="stExpander"] {
  background: var(--bg2) !important;
  border: 1px solid var(--border-1) !important;
  border-radius: var(--r-md) !important;
  overflow: hidden !important;
}
[data-testid="stExpander"] summary {
  font-size: 0.84rem !important;
  font-weight: 600 !important;
  color: var(--t1) !important;
  padding: 0.75rem 1rem !important;
  background: var(--bg2) !important;
  transition: background .15s !important;
}
[data-testid="stExpander"] summary:hover { background: var(--bg3) !important; }

/* ══════════════════════════════════════════
   PROGRESS BAR
══════════════════════════════════════════ */
.stProgress > div > div {
  background: var(--bg4) !important;
  border-radius: 99px !important;
  height: 6px !important;
}
.stProgress > div > div > div {
  background: linear-gradient(90deg, var(--g1), var(--g0)) !important;
  border-radius: 99px !important;
  transition: width .3s var(--ease) !important;
}

/* ══════════════════════════════════════════
   DATAFRAME / TABLES
══════════════════════════════════════════ */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border-1) !important;
  border-radius: var(--r-md) !important;
  overflow: hidden !important;
}
.dvn-scroller, .stDataFrame iframe { background: var(--bg1) !important; }

/* ══════════════════════════════════════════
   SPINNER
══════════════════════════════════════════ */
[data-testid="stSpinner"] > div { border-top-color: var(--g0) !important; }

/* ══════════════════════════════════════════
   COLUMNS
══════════════════════════════════════════ */
[data-testid="column"] { padding: 0 0.5rem !important; }
[data-testid="column"]:first-child { padding-left: 0 !important; }
[data-testid="column"]:last-child  { padding-right: 0 !important; }

/* ══════════════════════════════════════════
   CUSTOM COMPONENTS
══════════════════════════════════════════ */

/* ─── App Header ─── */
.geo-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 0 22px;
  border-bottom: 1px solid var(--border-1);
  margin-bottom: 24px;
}
.geo-header-logo {
  width: 48px; height: 48px;
  background: linear-gradient(135deg, #1A2840 0%, #1C3A5E 100%);
  border: 1px solid rgba(52,211,153,.3);
  border-radius: var(--r-lg);
  display: grid; place-items: center;
  font-size: 24px;
  box-shadow: 0 0 20px rgba(52,211,153,.1);
  flex-shrink: 0;
}
.geo-header-text { flex: 1; min-width: 0; }
.geo-header-title {
  font-size: 1.3rem; font-weight: 800;
  color: var(--t0); letter-spacing: -0.03em;
  line-height: 1.2; margin: 0;
}
.geo-header-sub {
  font-size: 0.72rem; color: var(--t3);
  font-weight: 600; letter-spacing: 0.1em;
  text-transform: uppercase; margin: 3px 0 0;
}
.geo-header-right {
  display: flex; align-items: center; gap: 8px;
  flex-shrink: 0;
}

/* ─── Badges ─── */
.badge {
  display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--f-mono); font-size: 0.68rem; font-weight: 500;
  padding: 3px 10px; border-radius: var(--r-pill);
  border: 1px solid var(--border-2);
  color: var(--t3); background: var(--bg2);
  white-space: nowrap; letter-spacing: 0.04em;
}
.badge-green {
  color: var(--g0); background: rgba(52,211,153,.08);
  border-color: rgba(52,211,153,.25);
}
.badge-blue {
  color: var(--b0); background: rgba(59,130,246,.08);
  border-color: rgba(59,130,246,.25);
}
.badge-amber {
  color: var(--a0); background: rgba(251,191,36,.08);
  border-color: rgba(251,191,36,.25);
}
.badge-dot::before {
  content: ''; width: 5px; height: 5px; border-radius: 50%;
  background: currentColor; display: inline-block;
}
.badge-live {
  color: var(--g0); background: rgba(52,211,153,.08);
  border-color: rgba(52,211,153,.25);
  animation: badge-pulse 2s ease-in-out infinite;
}
@keyframes badge-pulse {
  0%,100% { box-shadow: 0 0 0 0 rgba(52,211,153,.25); }
  50%      { box-shadow: 0 0 0 4px rgba(52,211,153,.0); }
}

/* ─── Cards ─── */
.geo-card {
  background: var(--bg2);
  border: 1px solid var(--border-1);
  border-radius: var(--r-lg);
  padding: 1.25rem 1.4rem;
  box-shadow: var(--shadow-card);
  margin-bottom: 1rem;
  transition: border-color .15s var(--ease);
}
.geo-card:hover { border-color: var(--border-2); }
.geo-card-accent {
  border-color: var(--border-g);
  background: linear-gradient(135deg, rgba(16,185,129,.04) 0%, var(--bg2) 60%);
}
.geo-card-title {
  font-size: 0.9rem; font-weight: 700;
  color: var(--t0); margin: 0 0 4px;
  display: flex; align-items: center; gap: 8px;
}
.geo-card-desc {
  font-size: 0.78rem; color: var(--t3);
  line-height: 1.5; margin: 0;
}

/* ─── Stat Row ─── */
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px,1fr));
  gap: 10px; margin-bottom: 1.25rem;
}
.stat-item {
  background: var(--bg2);
  border: 1px solid var(--border-1);
  border-radius: var(--r-md);
  padding: 1rem;
  text-align: center;
  transition: all .15s var(--ease);
  cursor: default;
}
.stat-item:hover {
  border-color: var(--border-g);
  box-shadow: var(--glow-g);
  transform: translateY(-2px);
}
.stat-item .sv {
  display: block;
  font-size: 1.55rem; font-weight: 800;
  color: var(--t0); letter-spacing: -0.04em;
  line-height: 1.1;
}
.stat-item .sl {
  display: block;
  font-size: 0.67rem; font-weight: 700;
  color: var(--t3); text-transform: uppercase;
  letter-spacing: 0.1em; margin-top: 3px;
}
.stat-item .sd {
  display: block;
  font-family: var(--f-mono); font-size: 0.7rem;
  margin-top: 4px;
}
.sd-up   { color: var(--g0); }
.sd-down { color: var(--r0); }
.sd-flat { color: var(--t3); }

/* ─── Section Label ─── */
.section-label {
  font-size: 0.67rem; font-weight: 700;
  color: var(--t3); text-transform: uppercase;
  letter-spacing: 0.1em; margin: 0 0 8px;
  display: flex; align-items: center; gap: 6px;
}
.section-label::after {
  content: ''; flex: 1; height: 1px;
  background: var(--border-1);
}

/* ─── Sidebar Logo ─── */
.sidebar-logo {
  display: flex; align-items: center; gap: 11px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--border-1);
  margin-bottom: 4px;
}
.sidebar-logo-icon {
  width: 34px; height: 34px;
  background: linear-gradient(135deg, var(--g2), var(--b1));
  border-radius: 9px;
  display: grid; place-items: center;
  font-size: 17px; flex-shrink: 0;
}
.sidebar-logo-name {
  font-weight: 800; font-size: 1rem;
  color: var(--t0); letter-spacing: -0.02em;
  line-height: 1.1;
}
.sidebar-logo-ver {
  font-family: var(--f-mono); font-size: 0.64rem;
  color: var(--t3); font-weight: 500;
}

/* Sidebar section label */
.sidebar-section-label {
  font-size: 0.65rem; font-weight: 700;
  color: var(--t4); text-transform: uppercase;
  letter-spacing: 0.1em; padding: 14px 16px 5px;
  margin: 0;
}

/* ─── Map wrapper ─── */
.map-wrap {
  border: 1px solid var(--border-1);
  border-radius: var(--r-lg);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

/* ─── Divider ─── */
.divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-2) 40%, transparent);
  margin: 1.5rem 0;
}

/* ══════════════════════════════════════════
   ANIMATIONS
══════════════════════════════════════════ */
@keyframes fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.fade-in { animation: fade-in .35s var(--ease) both; }

@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.shimmer {
  background: linear-gradient(90deg, var(--bg3) 25%, var(--bg4) 50%, var(--bg3) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--r-md);
}

</style>
"""


# ─── Helper components ────────────────────────────────────────

def app_header(status: str = "live") -> None:
    live_html = (
        '<span class="badge badge-live badge-dot">LIVE</span>'
        if status == "live"
        else '<span class="badge">IDLE</span>'
    )
    st.markdown(f"""
    <div class="geo-header fade-in">
      <div class="geo-header-logo">🛰️</div>
      <div class="geo-header-text">
        <p class="geo-header-title">GEO-AGRI</p>
        <p class="geo-header-sub">Agricultural Remote Sensing Platform</p>
      </div>
      <div class="geo-header-right">
        {live_html}
        <span class="badge badge-green">GEE · earth-500319</span>
        <span class="badge badge-blue">Sentinel-2</span>
        <span class="badge">v2.0</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def geo_card(title: str = "", desc: str = "", accent: bool = False) -> None:
    cls = "geo-card geo-card-accent" if accent else "geo-card"
    inner = ""
    if title:
        inner += f'<p class="geo-card-title">{title}</p>'
    if desc:
        inner += f'<p class="geo-card-desc">{desc}</p>'
    st.markdown(f'<div class="{cls}">{inner}', unsafe_allow_html=True)


def end_card() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def stat_row(stats: list) -> None:
    """stats = [{"label", "value", "delta"?, "delta_type"?}]"""
    html = '<div class="stat-row">'
    for s in stats:
        dt  = s.get("delta_type", "flat")
        sym = "↑ " if dt == "up" else ("↓ " if dt == "down" else "")
        delta_html = (
            f'<span class="sd sd-{dt}">{sym}{s["delta"]}</span>'
            if s.get("delta") else ""
        )
        html += f"""
        <div class="stat-item">
          <span class="sv">{s["value"]}</span>
          <span class="sl">{s["label"]}</span>
          {delta_html}
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def section_label(text: str) -> None:
    st.markdown(f'<p class="section-label">{text}</p>', unsafe_allow_html=True)


def divider() -> None:
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)


def badge(text: str, kind: str = "") -> str:
    cls = f"badge badge-{kind}" if kind else "badge"
    return f'<span class="{cls}">{text}</span>'
