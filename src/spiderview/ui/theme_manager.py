from __future__ import annotations
import json
from copy import deepcopy
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
THEMES = {
"Dark": dict(window="#14171C",panel="#171B21",surface="#1B1F26",surface_alt="#222832",border="#343B46",text="#D8DEE9",muted="#8994A5",accent="#657FF5",selection="#2B3440",canvas="#14171C",card="#202630",card_border="#3A4658",note="#D9A441",icon="#C6D0E0",success="#4CC38A",warning="#E7B455",error="#F16B75",critical="#D66BFF"),
"Light": dict(window="#F4F6FA",panel="#FFFFFF",surface="#FFFFFF",surface_alt="#E9EDF4",border="#CDD4DF",text="#202938",muted="#667085",accent="#315FEA",selection="#DCE6FF",canvas="#F4F6FA",card="#FFFFFF",card_border="#C5CEDB",note="#A66A00",icon="#445168",success="#16794B",warning="#966000",error="#C12D3A",critical="#8B35B5"),
"Dark+": dict(window="#090B10",panel="#0C1018",surface="#101621",surface_alt="#171F2D",border="#65748B",text="#FFFFFF",muted="#C0CBDC",accent="#7EA7FF",selection="#203B63",canvas="#080B11",card="#101725",card_border="#7B8BA5",note="#FFD166",icon="#FFFFFF",success="#61F2AE",warning="#FFD166",error="#FF727C",critical="#E5A0FF"),
"Light+": dict(window="#FFFFFF",panel="#FFFFFF",surface="#FFFFFF",surface_alt="#F0F3F8",border="#596579",text="#111827",muted="#374151",accent="#003CC7",selection="#D5E4FF",canvas="#FFFFFF",card="#FFFFFF",card_border="#596579",note="#7A4B00",icon="#172033",success="#006B3C",warning="#784900",error="#B00020",critical="#65008F")}
THEME_DESCRIPTIONS={"Dark":"Tema escuro equilibrado.","Light":"Tema claro equilibrado.","Dark+":"Alto contraste escuro, inspirado no VS Code.","Light+":"Alto contraste claro, inspirado no VS Code."}
class ThemeManager:
    SETTINGS_KEY="appearance/theme"; CUSTOM_KEY="appearance/custom_theme"
    def __init__(self):
        self.settings=QSettings("OZAP","SpiderView")
        self.current_name=str(self.settings.value(self.SETTINGS_KEY,"Dark"))
        raw=self.settings.value(self.CUSTOM_KEY,"")
        try: custom=json.loads(raw) if isinstance(raw,str) and raw else raw
        except (ValueError,TypeError): custom={}
        self.custom=deepcopy(THEMES["Dark"]); self.custom.update({k:v for k,v in (custom or {}).items() if k in self.custom and QColor(str(v)).isValid()})
        if self.current_name not in THEMES and self.current_name!="Personalizado": self.current_name="Dark"
    @property
    def colors(self): return self.custom if self.current_name=="Personalizado" else THEMES.get(self.current_name,THEMES["Dark"])
    def set_theme(self,name):
        self.current_name=name if name in THEMES or name=="Personalizado" else "Dark"
        self.settings.setValue(self.SETTINGS_KEY,self.current_name)
    def save_custom(self,colors):
        self.custom.update({k:v for k,v in colors.items() if k in self.custom and QColor(str(v)).isValid()})
        self.settings.setValue(self.CUSTOM_KEY,json.dumps(self.custom)); self.set_theme("Personalizado")
    def apply(self,app,window=None):
        c=self.colors
        app.setStyleSheet(f"""
QWidget {{ color:{c['text']}; }}
QMainWindow,QDialog {{ background:{c['window']}; }}
QMenuBar {{ background:{c['panel']}; color:{c['text']}; border-bottom:1px solid {c['border']}; padding:3px 6px; }}
QMenuBar::item {{ background:transparent; border-radius:5px; padding:6px 10px; }}
QMenuBar::item:selected,QMenu::item:selected {{ background:{c['selection']}; }}
QMenu {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; padding:5px; }}
QMenu::item {{ border-radius:4px; padding:7px 28px 7px 10px; }}
QMenu::separator {{ height:1px; background:{c['border']}; margin:5px 8px; }}
QToolBar,QDockWidget::title {{ background:{c['panel']}; border:0; }}
QDockWidget::title {{ padding:7px; border-bottom:1px solid {c['border']}; }}
QTabWidget::pane {{ border:1px solid {c['border']}; background:{c['surface']}; }}
QTabBar::tab {{ background:{c['surface_alt']}; color:{c['text']}; border:1px solid {c['border']}; padding:7px 12px; }}
QTabBar::tab:selected {{ background:{c['selection']}; }}
QLineEdit,QTextEdit,QPlainTextEdit,QComboBox,QSpinBox,QDoubleSpinBox,QListWidget,QTreeWidget,QTableWidget {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; selection-background-color:{c['selection']}; }}
QPushButton,QToolButton {{ background:{c['surface_alt']}; color:{c['text']}; border:1px solid {c['border']}; border-radius:4px; padding:5px 9px; }}
QPushButton:hover,QToolButton:hover {{ border-color:{c['accent']}; }}
QStatusBar {{ background:{c['panel']}; color:{c['text']}; border-top:1px solid {c['border']}; }}
QToolTip {{ background:{c['surface']}; color:{c['text']}; border:1px solid {c['border']}; }}
""")
        if window is not None:
            if hasattr(window,"canvas"): window.canvas.setBackgroundBrush(QColor(c["canvas"]))
            if hasattr(window,"graph_overview"): window.graph_overview.update()
