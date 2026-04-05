# -*- coding: utf-8 -*-
"""Окно предпросмотра отдельных кадров телеметрии."""

import logging

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class PreviewWindow(QDialog):
    """Отдельное окно для предпросмотра отрендереных кадров."""

    def __init__(self, telemetry: dict, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр кадров телеметрии")
        self.setGeometry(100, 100, 1200, 800)
        self.telemetry = telemetry
        self.config = config
        self.current_frame_index = 0
        self.preview_pixmap = None

        # Главный layout
        main_layout = QVBoxLayout(self)

        # Область для изображения
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(QSize(640, 480))
        scroll_area.setWidget(self.image_label)
        main_layout.addWidget(scroll_area, 1)

        # Панель управления
        control_panel = QGroupBox("Управление кадром")
        control_layout = QVBoxLayout(control_panel)

        # Ползунок для выбора кадра
        slider_row = QHBoxLayout()
        self.frame_slider = QSlider(Qt.Horizontal)
        points = telemetry.get("points", [])
        max_frame = max(0, len(points) - 1)
        self.frame_slider.setRange(0, max_frame)
        self.frame_slider.setValue(0)
        self.frame_slider.setTickPosition(QSlider.TicksBelow)
        self.frame_slider.setTickInterval(max(1, max_frame // 20) if max_frame > 0 else 1)
        self.frame_slider.sliderMoved.connect(self._on_slider_moved)
        slider_row.addWidget(QLabel("Кадр:"), 0)
        slider_row.addWidget(self.frame_slider, 1)
        control_layout.addLayout(slider_row)

        # Информация о кадре
        info_row = QHBoxLayout()
        self.frame_info_label = QLabel()
        self._update_frame_info()
        info_row.addWidget(self.frame_info_label)
        info_row.addStretch()
        control_layout.addLayout(info_row)

        # Кнопки
        button_row = QHBoxLayout()
        render_btn = QPushButton("Показать кадр")
        render_btn.setToolTip("Горячая клавиша: Space")
        render_btn.clicked.connect(self._render_preview)
        prev_btn = QPushButton("◀ Предыдущий")
        prev_btn.setToolTip("Горячая клавиша: Left")
        prev_btn.clicked.connect(self._prev_frame)
        next_btn = QPushButton("Следующий ▶")
        next_btn.setToolTip("Горячая клавиша: Right")
        next_btn.clicked.connect(self._next_frame)
        button_row.addStretch()
        button_row.addWidget(prev_btn)
        button_row.addWidget(next_btn)
        button_row.addWidget(render_btn)
        control_layout.addLayout(button_row)

        main_layout.addWidget(control_panel, 0)

        # Сразу показываем первый кадр
        self._render_preview()

    def _on_slider_moved(self, value: int):
        """Обработчик движения ползунка."""
        self.current_frame_index = value
        self._update_frame_info()

    def _update_frame_info(self):
        """Обновляет информацию о текущем кадре."""
        points = self.telemetry.get("points", [])
        total = len(points)
        fps = self.telemetry.get("fps", 30.0)
        time_sec = self.current_frame_index / fps if fps > 0 else 0

        if total > 0 and self.current_frame_index < len(points):
            pt = points[self.current_frame_index]
            lat = pt.get("lat", 0.0) if isinstance(pt, dict) else getattr(pt, "lat", 0.0)
            lon = pt.get("lon", 0.0) if isinstance(pt, dict) else getattr(pt, "lon", 0.0)
            speed = pt.get("speed", 0.0) if isinstance(pt, dict) else getattr(pt, "speed", 0.0)
            info = f"Кадр {self.current_frame_index}/{total-1} | Время: {time_sec:.2f}с | " \
                   f"Позиция: {lat:.4f}, {lon:.4f} | Скорость: {speed:.1f} км/ч"
        else:
            info = f"Кадр {self.current_frame_index}/{total-1 if total > 0 else 0} | Время: {time_sec:.2f}с"

        self.frame_info_label.setText(info)

    def _render_preview(self):
        """Рендерит текущий кадр."""
        try:
            self.frame_info_label.setText(f"Рендеринг кадра {self.current_frame_index}...")
            QApplication.processEvents()

            from renderer.engine import RenderEngine
            engine = RenderEngine(self.config)
            preview_frame = engine.get_preview_frame(self.telemetry, frame_index=self.current_frame_index, skip_map=False)

            if preview_frame is None:
                self.image_label.setText("Ошибка при рендеринге кадра")
                return

            # Конвертируем PIL Image в QPixmap
            import io
            with io.BytesIO() as output:
                preview_frame.save(output, format="PNG")
                data = output.getvalue()
            pixmap = QPixmap()
            pixmap.loadFromData(data, "PNG")

            # Масштабируем для отображения
            max_width = 1024
            if pixmap.width() > max_width:
                pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)

            self.preview_pixmap = pixmap
            self.image_label.setPixmap(pixmap)

            self._update_frame_info()
        except Exception as e:
            logger.error(f"Ошибка рендеринга превью: {e}", exc_info=True)
            self.image_label.setText(f"Ошибка: {str(e)[:100]}")

    def _next_frame(self):
        """Переходит на следующий кадр."""
        points = self.telemetry.get("points", [])
        max_frame = len(points) - 1
        if self.current_frame_index < max_frame:
            self.current_frame_index += 1
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_frame_index)
            self.frame_slider.blockSignals(False)
            self._update_frame_info()

    def _prev_frame(self):
        """Переходит на предыдущий кадр."""
        if self.current_frame_index > 0:
            self.current_frame_index -= 1
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.current_frame_index)
            self.frame_slider.blockSignals(False)
            self._update_frame_info()

    def keyPressEvent(self, event):
        """Обработчик горячих клавиш."""
        if event.key() == Qt.Key_Space:
            self._render_preview()
        elif event.key() == Qt.Key_Right:
            self._next_frame()
        elif event.key() == Qt.Key_Left:
            self._prev_frame()
        else:
            super().keyPressEvent(event)
