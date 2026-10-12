from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
PATHS={
"file":'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
"open":'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
"save":'<path d="M4 3h14l3 3v15H3V3z"/><path d="M7 3v6h10V3M7 21v-7h10v7"/>',
"export":'<path d="M12 3v12m-5-5 5 5 5-5"/><path d="M4 17v4h16v-4"/>',
"plus":'<path d="M12 5v14M5 12h14"/>',
"note":'<path d="M5 3h14v14l-4 4H5z"/><path d="M15 21v-5h4M8 8h8M8 12h6"/>',
"edit":'<path d="m4 16-1 5 5-1L20 8l-4-4z"/><path d="m14 6 4 4"/>',
"trash":'<path d="M3 6h18M8 6V3h8v3m-11 0 1 15h10l1-15M10 10v7m4-7v7"/>',
"browser":'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.1M10 6.5h.1"/>',
"console":'<path d="m4 6 6 6-6 6M12 18h8"/>',
"eye":'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
"layout":'<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="5" rx="1"/><rect x="13" y="10" width="8" height="11" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/>',
"vertical":'<path d="M12 3v18M5 7l7-4 7 4M5 17l7 4 7-4"/>',
"tools":'<path d="M14 6a5 5 0 0 0-6 6L3 17a2 2 0 0 0 3 3l5-5a5 5 0 0 0 6-6l-3 3-3-3z"/>',
"shield":'<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11z"/><path d="m9 12 2 2 4-4"/>',
"settings":'<circle cx="12" cy="12" r="3"/><path d="M19 13.5l2 1.5-2 3-2-1a8 8 0 0 1-2 1l-.5 2h-3l-.5-2a8 8 0 0 1-2-1l-2 1-2-3 2-1.5a8 8 0 0 1 0-3L3 9l2-3 2 1a8 8 0 0 1 2-1l.5-2h3l.5 2a8 8 0 0 1 2 1l2-1 2 3-2 1.5a8 8 0 0 1 0 3z"/>',
"palette":'<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1.5-3.3 2 2 0 0 1 1.5-3.3H18a3 3 0 0 0 3-3C21 6.8 17 3 12 3z"/><circle cx="7.5" cy="10" r="1"/><circle cx="11" cy="7" r="1"/>',
"scan":'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M8 10h5M10.5 7.5v5"/>',
"tree":'<circle cx="12" cy="4" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 6v6M5 17v-5h14v5"/>',
"reset":'<path d="M3 11a9 9 0 1 1 2 6M3 4v7h7"/>',
"help":'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4.4 1.6c-1.1 1-1.9 1.2-1.9 3M12 17h.01"/>'
}
def icon(name, color="#C6D0E0", size=16):
    """Renderiza o SVG em alta densidade para manter traços nítidos ao reduzir."""
    body = PATHS.get(name, PATHS["help"])
    scale = 4
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f'{body}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    result = QIcon()
    result.addPixmap(pixmap)
    return result
