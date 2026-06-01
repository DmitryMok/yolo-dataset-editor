"""
Design tokens and QSS stylesheet — Classic dark theme.
Colors converted from oklch (design spec) to sRGB hex.
"""

# ── Surfaces ──────────────────────────────────────────────────────────────────
BG        = "#1c1d20"
CHROME    = "#25262b"
PANEL     = "#25262b"
PANEL2    = "#2c2e33"
PANEL3    = "#34373d"

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER    = "#3a3d43"
BORDER_S  = "#313338"

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT       = "#d8dadf"
TEXT_DIM   = "#9298a0"
TEXT_FAINT = "#6c727a"

# ── Accent: oklch(0.64 0.12 248) → muted blue ─────────────────────────────────
ACCENT    = "#3e8ace"

# ── Semantic ──────────────────────────────────────────────────────────────────
DANGER    = "#d34a46"   # oklch(0.62 0.16 25)
OK_COLOR  = "#48ac74"   # oklch(0.68 0.13 150)
WARN      = "#c4a040"   # oklch(0.74 0.13 75)

# ── Split palette ─────────────────────────────────────────────────────────────
C_TRAIN  = "#5080cc"    # oklch(0.7  0.13 250)
C_VAL    = "#52c878"    # oklch(0.78 0.15 150)
C_TEST   = "#c4bc40"    # oklch(0.8  0.14 90)
C_REVIEW = "#c89038"    # oklch(0.78 0.16 60)

SPLIT_COLORS: dict[str, str] = {
    "train":  C_TRAIN,
    "val":    C_VAL,
    "test":   C_TEST,
    "review": C_REVIEW,
}


def _a(hex_color: str, alpha: int) -> str:
    """Return rgba() from #RRGGBB hex and alpha 0–255."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def make_stylesheet() -> str:
    a_soft   = _a(ACCENT, 40)
    a_mid    = _a(ACCENT, 80)
    danger_s = _a(DANGER, 40)
    train_s  = _a(C_TRAIN, 75)
    val_s    = _a(C_VAL,   75)
    test_s   = _a(C_TEST,  75)
    rev_s    = _a(C_REVIEW,75)

    return f"""
/* ──────────────────────────────────────────────────────────
   YoloLabel — Classic dark theme
   ────────────────────────────────────────────────────────── */

QMainWindow, QDialog {{
    background: {BG};
}}

QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
    selection-background-color: {a_mid};
    selection-color: {TEXT};
}}

/* ── Toolbar ────────────────────────────────────────────── */
#toolbar {{
    background: {CHROME};
    border-bottom: 1px solid {BORDER};
}}
QWidget#tzone {{
    background: transparent;
}}
#toolbar QCheckBox {{
    background: transparent;
}}
#toolbar QLabel {{
    background: transparent;
}}
#zone-sep {{
    background: {BORDER_S};
}}
#modetabs-bg {{
    background: {BG};
    border: 1px solid {BORDER_S};
    border-radius: 5px;
}}
#modetab {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    border-radius: 4px;
    padding: 0px 14px;
    font-weight: 600;
    font-size: 12px;
    min-height: 22px;
    max-height: 22px;
}}
#modetab:hover {{ color: {TEXT}; background: {PANEL2}; }}
#modetab:checked {{
    background: {PANEL2};
    color: {TEXT};
}}
#tbtn {{
    background: transparent;
    color: {TEXT};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0px 8px;
    font-size: 12px;
}}
#tbtn:hover {{ background: {PANEL2}; }}
#tbtn:pressed {{ background: {PANEL3}; }}
#tbtn:disabled {{ color: {TEXT_FAINT}; }}
QToolButton#tbtn {{
    padding: 0px 2px;
}}
QToolButton#tbtn::menu-button {{
    border-left: 1px solid {BORDER_S};
    width: 14px;
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}}
QToolButton#tbtn::menu-arrow {{
    width: 6px;
    height: 4px;
}}

/* ── Canvas nav bar ─────────────────────────────────────── */
#canvas-nav {{
    background: {BG};
    border-bottom: 1px solid {BORDER_S};
}}
#canvas-nav QWidget {{ background: transparent; }}
#nav-btn {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    border-radius: 4px;
    font-size: 18px;
    font-weight: 600;
    padding: 0px 0px 1px 0px;
    min-height: 24px;
    max-height: 24px;
}}
#nav-btn:hover {{ background: {PANEL2}; color: {TEXT}; }}
#nav-btn:disabled {{ color: {TEXT_FAINT}; }}
#nav-counter {{
    background: transparent;
    color: {TEXT_DIM};
    font-size: 12px;
    font-variant-numeric: tabular-nums;
}}
QCheckBox#auto-advance-cb {{
    background: transparent;
    font-size: 12px;
    color: {TEXT_DIM};
}}

QCheckBox#move-enabled-cb {{
    background: transparent;
    font-size: 12px;
    color: {TEXT_DIM};
}}

/* ── Assign row ─────────────────────────────────────────── */
#assign-row {{
    background: {BG};
    border-bottom: 1px solid {BORDER_S};
}}
#assign-row QWidget {{ background: transparent; }}
#assign-lbl {{
    background: transparent;
    color: {TEXT_FAINT};
    font-size: 10px;
    font-weight: 700;
}}
#cur-lbl {{
    background: transparent;
    color: {TEXT_FAINT};
    font-size: 10px;
    font-weight: 700;
}}
/* Split badge button — styled dynamically via setStyleSheet */
#split-badge-btn {{
    background: {PANEL3};
    color: {TEXT};
    border: none;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 800;
    padding: 2px 6px;
    min-height: 18px;
}}
#split-badge-btn::menu-indicator {{ image: none; }}
#seg-bg {{
    background: transparent;
    border: none;
}}
#split-btn {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    border-radius: 4px;
    padding: 0px 12px;
    font-size: 12px;
    font-weight: 600;
    min-height: 24px;
    max-height: 24px;
}}
#split-btn:hover {{ color: {TEXT}; background: {PANEL3}; }}
#split-btn:disabled {{ color: {TEXT_FAINT}; }}
#split-btn[split="train"]:checked {{ background: {train_s}; color: #fff; }}
#split-btn[split="val"]:checked   {{ background: {val_s};   color: #fff; }}
#split-btn[split="test"]:checked  {{ background: {test_s};  color: #1a1a0a; }}
#split-btn[split="review"]:checked {{
    background: {rev_s};
    color: #fff;
    border: 1px solid {C_REVIEW};
}}

/* ── Panels ─────────────────────────────────────────────── */
#panel-left {{
    background: {PANEL};
    border-right: 1px solid {BORDER};
}}
#panel-right {{
    background: {PANEL};
    border-left: 1px solid {BORDER};
}}

/* ── Panel header row ───────────────────────────────────── */
#panel-header-row {{
    background: {PANEL};
    border-bottom: 1px solid {BORDER_S};
}}
#phead {{
    background: transparent;
    color: {TEXT_DIM};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
#panel-head-btn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 0px;
}}
#panel-head-btn:hover {{ background: {PANEL3}; }}
#panel-head-btn:pressed {{ background: {BORDER}; }}
#panel-head-btn-danger {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 0px;
}}
#panel-head-btn-danger:hover {{ background: {danger_s}; }}
#panel-head-btn-danger:pressed {{ background: {danger_s}; }}
#cur-block {{ background: transparent; }}

/* ── Status bar ─────────────────────────────────────────── */
QStatusBar {{
    background: {CHROME};
    color: {TEXT_DIM};
    font-size: 11px;
    border-top: 1px solid {BORDER};
}}
QStatusBar::item {{ border: none; }}

/* ── Splitter ────────────────────────────────────────────── */
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ── List widget ─────────────────────────────────────────── */
QListWidget {{
    background: {BG};
    border: none;
    outline: 0;
}}
QListWidget::item {{
    padding: 2px 8px;
    border-radius: 3px;
    border: none;
    min-height: 24px;
}}
QListWidget::item:hover {{ background: {PANEL2}; }}
QListWidget::item:selected {{
    background: {a_soft};
    color: {TEXT};
    border-left: 2px solid {ACCENT};
}}

/* ── ComboBox ────────────────────────────────────────────── */
QComboBox {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 8px;
    color: {TEXT};
    min-height: 26px;
}}
QComboBox:hover {{ border-color: {TEXT_FAINT}; }}
QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    selection-background-color: {a_mid};
    color: {TEXT};
    outline: 0;
}}

/* ── Push buttons (generic) ──────────────────────────────── */
QPushButton {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    border-radius: 4px;
    color: {TEXT};
    padding: 4px 12px;
    min-height: 26px;
    font-size: 12px;
}}
QPushButton:hover {{ background: {PANEL3}; border-color: {TEXT_FAINT}; }}
QPushButton:pressed {{ background: {PANEL3}; }}
QPushButton:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #fff;
}}
QPushButton:disabled {{
    color: {TEXT_FAINT};
    border-color: {PANEL3};
    background: {PANEL2};
}}
QPushButton#danger-btn {{ color: {DANGER}; }}
QPushButton#danger-btn:hover {{ background: {danger_s}; }}

/* ── CheckBox ────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT};
    spacing: 6px;
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {BG};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{ border-color: {TEXT_FAINT}; }}

/* ── Sliders ─────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {PANEL3};
    border-radius: 2px;
    margin: 0;
}}
QSlider::handle:horizontal {{
    background: {TEXT_DIM};
    border: none;
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: {TEXT}; }}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* ── GroupBox ─────────────────────────────────────────────── */
QGroupBox {{
    background: transparent;
    border: 1px solid {BORDER_S};
    border-radius: 5px;
    margin-top: 8px;
    padding-top: 8px;
    font-size: 11px;
    font-weight: 700;
    color: {TEXT_DIM};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {TEXT_DIM};
}}

/* ── Menu ────────────────────────────────────────────────── */
QMenu {{
    background: {PANEL2};
    border: 1px solid {BORDER};
    color: {TEXT};
    padding: 3px 0;
}}
QMenu::item {{
    padding: 5px 20px;
    border-radius: 3px;
    margin: 1px 4px;
}}
QMenu::item:selected {{ background: {a_soft}; }}
QMenu::separator {{
    height: 1px;
    background: {BORDER_S};
    margin: 3px 6px;
}}

/* ── ToolButton (generic + toolbar) ─────────────────────── */
QToolButton {{
    background: transparent;
    color: {TEXT};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 12px;
}}
QToolButton:hover {{ background: {PANEL2}; }}
QToolButton:pressed {{ background: {PANEL3}; }}

/* ── Dialog ──────────────────────────────────────────────── */
QDialog {{
    background: {PANEL};
}}
QDialog QWidget {{ background: {PANEL}; }}
QDialogButtonBox QPushButton {{ min-width: 70px; }}

/* ── Scroll bars ─────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {PANEL3};
    border-radius: 6px;
    min-height: 30px;
    border: 3px solid {PANEL};
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ── Graphics view (canvas) ──────────────────────────────── */
QGraphicsView {{
    background: {BG};
    border: none;
}}

/* ── Tooltip ─────────────────────────────────────────────── */
QToolTip {{
    background: {PANEL3};
    border: 1px solid {BORDER};
    color: {TEXT};
    padding: 4px 8px;
    border-radius: 4px;
}}
"""
