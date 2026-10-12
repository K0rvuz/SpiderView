from __future__ import annotations
from copy import deepcopy
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox,QColorDialog,QComboBox,QDialog,QDialogButtonBox,QFormLayout,QGroupBox,QHBoxLayout,QLabel,QListWidget,QPushButton,QStackedWidget,QVBoxLayout,QWidget,QApplication)
from .icons import icon
from .theme_manager import THEMES,THEME_DESCRIPTIONS,ThemeManager
TOKENS={"window":"Fundo principal","panel":"Barras e painéis","surface":"Superfícies","surface_alt":"Superfície secundária","border":"Bordas","text":"Texto principal","muted":"Texto secundário","accent":"Destaque","selection":"Seleção","canvas":"Fundo do canvas","card":"Fundo dos cards","card_border":"Borda dos cards","note":"Cor das notas","icon":"Cor dos ícones SVG","success":"Sucesso","warning":"Aviso","error":"Alto risco","critical":"Crítico"}
class SettingsDialog(QDialog):
    def __init__(self,theme_manager:ThemeManager,parent=None):
        super().__init__(parent); self.theme_manager=theme_manager; self.settings=QSettings("OZAP","SpiderView")
        self.setWindowTitle("Configurações do SpiderView"); self.resize(760,540)
        outer=QVBoxLayout(self); content=QHBoxLayout(); self.categories=QListWidget(); self.categories.setFixedWidth(175); self.categories.addItems(["Aparência","OWASP ZAP","SpiderView"]); self.pages=QStackedWidget()
        content.addWidget(self.categories); content.addWidget(self.pages,1); outer.addLayout(content,1)
        self.pages.addWidget(self._appearance_page()); self.pages.addWidget(self._zap_page()); self.pages.addWidget(self._spider_page())
        self.categories.currentRowChanged.connect(self.pages.setCurrentIndex); self.categories.setCurrentRow(0)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(self.reject); buttons.accepted.connect(self.accept); outer.addWidget(buttons)
    def _appearance_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.addWidget(QLabel("<h2>Aparência</h2><p>Escolha um tema ou crie sua própria paleta.</p>"))
        self.theme_combo=QComboBox(); self.theme_combo.addItems(["Dark","Light","Dark+","Light+","Personalizado"]); self.theme_combo.setCurrentText(self.theme_manager.current_name); self.theme_combo.currentTextChanged.connect(self._select_theme)
        layout.addWidget(QLabel("Tema")); layout.addWidget(self.theme_combo); self.description=QLabel(); self.description.setWordWrap(True); layout.addWidget(self.description)
        group=QGroupBox("Cores do tema personalizado"); form=QFormLayout(group); self.color_buttons={}
        for token,label in TOKENS.items():
            row=QHBoxLayout(); button=QPushButton(self.theme_manager.custom[token]); button.setIcon(icon("palette",self.theme_manager.custom["icon"])); button.clicked.connect(lambda _=False,t=token:self._choose_color(t)); row.addWidget(button); preview=QLabel("  "); preview.setFixedWidth(28); row.addWidget(preview); self.color_buttons[token]=(button,preview); form.addRow(label,row)
        layout.addWidget(group,1); reset=QPushButton("Restaurar cores padrão"); reset.clicked.connect(self._reset_custom); layout.addWidget(reset); self._update_description(); self._refresh_colors(); return page
    def _zap_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.addWidget(QLabel("<h2>OWASP ZAP</h2><p>Preferências de integração e análise.</p>"))
        self.zap_enabled=QCheckBox("Habilitar integração com OWASP ZAP"); self.zap_enabled.setChecked(self.settings.value("zap/enabled",True,type=bool)); layout.addWidget(self.zap_enabled)
        self.zap_passive=QCheckBox("Permitir análise passiva"); self.zap_passive.setChecked(self.settings.value("zap/passive_enabled",True,type=bool)); layout.addWidget(self.zap_passive)
        self.zap_active=QCheckBox("Permitir scans ativos (exigem autorização explícita)"); self.zap_active.setChecked(self.settings.value("zap/active_enabled",False,type=bool)); layout.addWidget(self.zap_active)
        layout.addWidget(QLabel("Scans ativos permanecem desabilitados por padrão.")); layout.addStretch(1); return page
    def _spider_page(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.addWidget(QLabel("<h2>SpiderView</h2>"))
        self.auto_map=QCheckBox("Atualizar o grafo automaticamente durante a navegação"); self.auto_map.setChecked(self.settings.value("spiderview/auto_map",True,type=bool)); layout.addWidget(self.auto_map)
        self.preserve_layout=QCheckBox("Preservar o layout manual ao atualizar o grafo"); self.preserve_layout.setChecked(self.settings.value("spiderview/preserve_layout",True,type=bool)); layout.addWidget(self.preserve_layout); layout.addStretch(1); return page
    def _select_theme(self,name):
        self.theme_manager.set_theme(name); self._update_description(); self._refresh_colors(); self.theme_manager.apply(QApplication.instance(),self.parent())
    def _update_description(self):
        name=self.theme_combo.currentText(); self.description.setText("Paleta editável pelo usuário." if name=="Personalizado" else THEME_DESCRIPTIONS[name])
    def _refresh_colors(self):
        if not hasattr(self, "color_buttons"):
            return
        for token,(button,preview) in self.color_buttons.items():
            color=self.theme_manager.custom[token]; button.setText(color); preview.setStyleSheet(f"background:{color};border:1px solid #777;"); button.setEnabled(self.theme_combo.currentText()=="Personalizado")
    def _choose_color(self,token):
        color=QColorDialog.getColor(QColor(self.theme_manager.custom[token]),self,f"Cor: {TOKENS[token]}")
        if color.isValid():
            colors=dict(self.theme_manager.custom); colors[token]=color.name(); self.theme_manager.save_custom(colors); self.theme_combo.setCurrentText("Personalizado"); self._refresh_colors(); self.theme_manager.apply(QApplication.instance(),self.parent())
    def _reset_custom(self):
        self.theme_manager.save_custom(deepcopy(THEMES["Dark"])); self.theme_combo.setCurrentText("Personalizado"); self._refresh_colors(); self.theme_manager.apply(QApplication.instance(),self.parent())
    def accept(self):
        self.settings.setValue("zap/enabled",self.zap_enabled.isChecked()); self.settings.setValue("zap/passive_enabled",self.zap_passive.isChecked()); self.settings.setValue("zap/active_enabled",self.zap_active.isChecked()); self.settings.setValue("spiderview/auto_map",self.auto_map.isChecked()); self.settings.setValue("spiderview/preserve_layout",self.preserve_layout.isChecked()); super().accept()
