# -*- coding: utf-8 -*-
"""Холст визуального расположения модулей поверх кадра."""

import logging

from PyQt5.QtCore import Qt, QRect, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class ModuleLayoutCanvas(QWidget):
    """Холст для визуального перемещения модулей мышью с превью первого кадра."""

    moduleMoved = pyqtSignal(int)
    previewRequested = pyqtSignal()

    def __init__(self, config: dict):
        super().__init__()
        self.setMinimumSize(640, 360)
        self.config = config
        self.active_index = -1
        self._dragging = False
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._preview_image = None
        self._show_preview = True

    def set_config(self, config: dict):
        self.config = config
        self.active_index = -1
        self._preview_image = None
        self.update()

    def set_preview_image(self, img):
        """Устанавливает изображение превью."""
        self._preview_image = img
        self.update()

    def set_show_preview(self, show: bool):
        """Включает/отключает отображение превью."""
        self._show_preview = show
        self.update()

    def set_active_index(self, index: int):
        self.active_index = index
        self.update()

    def _canvas_metrics(self):
        width = max(1, int(self.config.get("width", 1920)))
        height = max(1, int(self.config.get("height", 1080)))
        scale = min((self.width() - 20) / width, (self.height() - 20) / height)
        scale = max(0.05, scale)
        draw_w = int(width * scale)
        draw_h = int(height * scale)
        ox = (self.width() - draw_w) // 2
        oy = (self.height() - draw_h) // 2
        return width, height, scale, ox, oy, draw_w, draw_h

    def _module_rect(self, module: dict) -> QRect:
        width, height, scale, ox, oy, _, _ = self._canvas_metrics()
        x = int(module.get("x", 0))
        y = int(module.get("y", 0))
        w = int(module.get("width", 200))
        h = int(module.get("height", 120))
        if w <= 0:
            w = 200
        if h <= 0:
            h = 120
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        return QRect(
            ox + int(x * scale),
            oy + int(y * scale),
            max(12, int(w * scale)),
            max(12, int(h * scale)),
        )

    def paintEvent(self, event):
        _ = event
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        width, height, scale, ox, oy, draw_w, draw_h = self._canvas_metrics()

        # Фон
        p.fillRect(self.rect(), QColor(28, 28, 31))

        # Отрисовываем превью, если есть
        if self._preview_image is not None and self._show_preview:
            try:
                import io
                # Конвертируем PIL Image в QPixmap через PNG bytes
                with io.BytesIO() as output:
                    self._preview_image.save(output, format="PNG")
                    data = output.getvalue()
                pix = QPixmap()
                pix.loadFromData(data, "PNG")
                scaled_pix = pix.scaledToWidth(draw_w, Qt.SmoothTransformation)
                p.drawPixmap(ox, oy, scaled_pix)
            except Exception as e:
                logger.debug(f"Ошибка отрисовки превью: {e}")
        else:
            # Если превью нет, рисуем просто сетку
            p.setPen(QPen(QColor(80, 80, 90), 1))
            p.setBrush(QBrush(QColor(18, 18, 22)))
            p.drawRect(ox, oy, draw_w, draw_h)

        # Рисуем рамки модулей поверх превью
        modules = self.config.get("modules", [])
        for idx, mod in enumerate(modules):
            rect = self._module_rect(mod)
            enabled = bool(mod.get("enabled", True))
            is_active = idx == self.active_index

            if is_active:
                pen = QPen(QColor(245, 196, 66), 2)
                brush = QBrush(QColor(245, 196, 66, 70))
            elif enabled:
                pen = QPen(QColor(77, 163, 255), 1)
                brush = QBrush(QColor(77, 163, 255, 55))
            else:
                pen = QPen(QColor(130, 130, 130), 1, Qt.DashLine)
                brush = QBrush(QColor(120, 120, 120, 35))

            p.setPen(pen)
            p.setBrush(brush)
            p.drawRect(rect)

            label = f"{idx + 1}. {mod.get('type', 'module')}"
            p.setPen(QPen(QColor(235, 235, 235), 1))
            p.drawText(rect.adjusted(4, 2, -4, -2), Qt.AlignLeft | Qt.AlignTop, label)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        modules = self.config.get("modules", [])
        for idx in range(len(modules) - 1, -1, -1):
            rect = self._module_rect(modules[idx])
            if rect.contains(event.pos()):
                self.active_index = idx
                self.moduleMoved.emit(idx)
                self._dragging = True
                self._drag_offset_x = event.pos().x() - rect.x()
                self._drag_offset_y = event.pos().y() - rect.y()
                self.update()
                return

    def mouseMoveEvent(self, event):
        if not self._dragging or self.active_index < 0:
            return

        modules = self.config.get("modules", [])
        if self.active_index >= len(modules):
            return

        width, height, scale, ox, oy, _, _ = self._canvas_metrics()
        mod = modules[self.active_index]
        w = max(1, int(mod.get("width", 200)))
        h = max(1, int(mod.get("height", 120)))

        px = event.pos().x() - self._drag_offset_x
        py = event.pos().y() - self._drag_offset_y

        x = int((px - ox) / scale)
        y = int((py - oy) / scale)
        x = max(0, min(x, width - w))
        y = max(0, min(y, height - h))

        mod["x"] = x
        mod["y"] = y
        self.moduleMoved.emit(self.active_index)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
