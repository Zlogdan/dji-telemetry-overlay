# -*- coding: utf-8 -*-
"""
Главное окно приложения DJI Telemetry Overlay.
Пользовательский интерфейс на русском языке.
"""

import json
import os
import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QGroupBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QProgressBar, QStatusBar, QMenuBar,
    QAction, QSplitter, QFrame, QScrollArea,
    QFormLayout, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QPalette

from config.config_manager import ConfigManager


class TelemetryWorker(QObject):
    """Рабочий поток для извлечения телеметрии."""

    # Сигналы
    finished = pyqtSignal(dict)          # телеметрия успешно извлечена
    error = pyqtSignal(str)              # произошла ошибка
    progress = pyqtSignal(str)           # сообщение о прогрессе

    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path

    def run(self):
        """Выполняет извлечение телеметрии."""
        try:
            self.progress.emit("Анализ видеофайла...")
            from core.extractor import extract_telemetry
            telemetry = extract_telemetry(self.video_path)
            self.progress.emit(f"Извлечено точек: {len(telemetry.get('points', []))}")
            self.finished.emit(telemetry)
        except Exception as e:
            self.error.emit(f"Ошибка извлечения: {str(e)}")


class RenderWorker(QObject):
    """Рабочий поток для рендеринга оверлея."""

    finished = pyqtSignal(str)           # путь к выходному файлу
    error = pyqtSignal(str)              # ошибка
    progress = pyqtSignal(int, int)      # текущий кадр, всего кадров

    def __init__(self, telemetry: dict, output_path: str, config: dict):
        super().__init__()
        self.telemetry = telemetry
        self.output_path = output_path
        self.config = config

    def run(self):
        """Выполняет рендеринг оверлея."""
        try:
            from renderer.engine import RenderEngine
            engine = RenderEngine(self.config)
            engine.render_to_video(
                self.telemetry,
                self.output_path,
                progress_callback=self.progress.emit
            )
            self.finished.emit(self.output_path)
        except Exception as e:
            self.error.emit(f"Ошибка рендеринга: {str(e)}")


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.telemetry_data = None
        self._thread = None
        self._worker = None

        self.setWindowTitle("DJI Telemetry Overlay")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()

    # ── Построение интерфейса ────────────────────────────────────────

    def _setup_ui(self):
        """Строит основной интерфейс."""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Левая панель управления
        left_widget = QWidget()
        left_widget.setMaximumWidth(380)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(6)

        left_layout.addWidget(self._build_files_group())
        left_layout.addWidget(self._build_actions_group())
        left_layout.addWidget(self._build_modules_group())
        left_layout.addWidget(self._build_params_group())
        left_layout.addStretch()

        # Правая панель результатов
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(6)

        right_layout.addWidget(self._build_preview_group())

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _build_files_group(self) -> QGroupBox:
        """Группа выбора файлов."""
        group = QGroupBox("Файлы")
        layout = QFormLayout(group)
        layout.setSpacing(6)

        # Исходное видео
        video_row = QWidget()
        video_layout = QHBoxLayout(video_row)
        video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setReadOnly(True)
        self.video_path_edit.setPlaceholderText("Не выбран...")
        browse_video_btn = QPushButton("Обзор...")
        browse_video_btn.setFixedWidth(80)
        browse_video_btn.clicked.connect(self._browse_video)
        video_layout.addWidget(self.video_path_edit)
        video_layout.addWidget(browse_video_btn)
        layout.addRow("Исходное видео:", video_row)

        # Выходной файл
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("overlay_output.mov")
        browse_output_btn = QPushButton("Обзор...")
        browse_output_btn.setFixedWidth(80)
        browse_output_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(self.output_path_edit)
        output_layout.addWidget(browse_output_btn)
        layout.addRow("Выходной файл:", output_row)

        return group

    def _build_actions_group(self) -> QGroupBox:
        """Группа кнопок действий."""
        group = QGroupBox("Действия")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        # Кнопка извлечения телеметрии
        self.extract_btn = QPushButton("Извлечь телеметрию")
        self.extract_btn.setMinimumHeight(38)
        self.extract_btn.setStyleSheet(
            "QPushButton { background-color: #2d7a2d; color: white; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3a9e3a; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self.extract_btn.clicked.connect(self._extract_telemetry)
        layout.addWidget(self.extract_btn)

        # Демо-телеметрия
        demo_btn = QPushButton("Использовать демо-телеметрию")
        demo_btn.setMinimumHeight(30)
        demo_btn.setStyleSheet(
            "QPushButton { background-color: #555; color: #ddd; border-radius: 4px; }"
            "QPushButton:hover { background-color: #666; }"
        )
        demo_btn.clicked.connect(self._use_demo_telemetry)
        layout.addWidget(demo_btn)

        # Кнопка создания оверлея
        self.render_btn = QPushButton("Создать оверлей")
        self.render_btn.setMinimumHeight(38)
        self.render_btn.setEnabled(False)
        self.render_btn.setStyleSheet(
            "QPushButton { background-color: #1a5a8a; color: white; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2070aa; }"
            "QPushButton:disabled { background-color: #555; color: #888; }"
        )
        self.render_btn.clicked.connect(self._render_overlay)
        layout.addWidget(self.render_btn)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Статус
        self.status_label = QLabel("Готов к работе")
        self.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.status_label)

        return group

    def _build_modules_group(self) -> QGroupBox:
        """Группа выбора активных модулей."""
        group = QGroupBox("Модули")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self.module_checkboxes = {}
        modules_cfg = self.config_manager.config.get("modules", [])

        # Маппинг типов на русские названия
        module_labels = {
            "speedometer": "Спидометр",
            "map": "Карта",
            "heading": "Компас",
        }

        # Текстовые поля
        text_modules = [m for m in modules_cfg if m.get("type") == "text"]
        for i, tm in enumerate(text_modules):
            field = tm.get("field", "")
            label = tm.get("label", f"Текст ({field})")
            key = f"text_{field}"
            cb = QCheckBox(f"Текст ({label})")
            cb.setChecked(tm.get("enabled", True))
            cb.stateChanged.connect(lambda state, k=key, idx=i: self._toggle_module(k, state, idx))
            layout.addWidget(cb)
            self.module_checkboxes[key] = (cb, "text", i)

        # Остальные модули
        for type_key, type_label in module_labels.items():
            matching = [m for m in modules_cfg if m.get("type") == type_key]
            for idx, mod in enumerate(matching):
                cb = QCheckBox(type_label)
                cb.setChecked(mod.get("enabled", True))
                cb.stateChanged.connect(lambda state, k=type_key, i=idx: self._toggle_module(k, state, i))
                layout.addWidget(cb)
                self.module_checkboxes[f"{type_key}_{idx}"] = (cb, type_key, idx)

        return group

    def _build_params_group(self) -> QGroupBox:
        """Группа настройки параметров."""
        group = QGroupBox("Параметры")
        layout = QFormLayout(group)
        layout.setSpacing(6)

        # Масштаб карты
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(1, 19)
        self.zoom_spin.setValue(14)
        self.zoom_spin.setSuffix("  (уровень)")
        self.zoom_spin.valueChanged.connect(self._update_map_zoom)
        layout.addRow("Масштаб карты:", self.zoom_spin)

        # Максимальная скорость
        self.max_speed_spin = QSpinBox()
        self.max_speed_spin.setRange(10, 500)
        self.max_speed_spin.setValue(150)
        self.max_speed_spin.setSuffix(" км/ч")
        self.max_speed_spin.valueChanged.connect(self._update_max_speed)
        layout.addRow("Макс. скорость:", self.max_speed_spin)

        # Размер кадра
        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 7680)
        self.width_spin.setValue(self.config_manager.config.get("width", 1920))
        self.width_spin.setSingleStep(16)
        self.width_spin.valueChanged.connect(lambda v: self.config_manager.config.update({"width": v}))
        layout.addRow("Ширина кадра:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 4320)
        self.height_spin.setValue(self.config_manager.config.get("height", 1080))
        self.height_spin.setSingleStep(16)
        self.height_spin.valueChanged.connect(lambda v: self.config_manager.config.update({"height": v}))
        layout.addRow("Высота кадра:", self.height_spin)

        return group

    def _build_preview_group(self) -> QGroupBox:
        """Правая панель предпросмотра телеметрии."""
        group = QGroupBox("Предпросмотр телеметрии")
        layout = QVBoxLayout(group)

        # Метаданные
        self.meta_label = QLabel("Нет данных телеметрии")
        self.meta_label.setStyleSheet("color: #aaa; font-size: 12px;")
        layout.addWidget(self.meta_label)

        # Текстовая область с телеметрией
        self.telemetry_text = QTextEdit()
        self.telemetry_text.setReadOnly(True)
        self.telemetry_text.setFont(QFont("Monospace", 10))
        self.telemetry_text.setPlaceholderText(
            "Здесь будет отображаться извлечённая телеметрия в формате JSON...\n\n"
            "Выберите видеофайл и нажмите «Извлечь телеметрию»,\n"
            "или используйте «Демо-телеметрию» для тестирования."
        )
        layout.addWidget(self.telemetry_text)

        return group

    # ── Меню ────────────────────────────────────────────────────────

    def _setup_menu(self):
        """Создаёт строку меню."""
        menubar = self.menuBar()

        # Меню "Файл"
        file_menu = menubar.addMenu("Файл")

        open_action = QAction("Открыть видео", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._browse_video)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        load_config_action = QAction("Загрузить конфиг...", self)
        load_config_action.triggered.connect(self._load_config)
        file_menu.addAction(load_config_action)

        save_config_action = QAction("Сохранить конфиг...", self)
        save_config_action.setShortcut("Ctrl+S")
        save_config_action.triggered.connect(self._save_config)
        file_menu.addAction(save_config_action)

        file_menu.addSeparator()

        exit_action = QAction("Выход", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню "Справка"
        help_menu = menubar.addMenu("Справка")

        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """Создаёт строку состояния."""
        self.statusBar().showMessage("DJI Telemetry Overlay готов к работе")

    # ── Обработчики событий ──────────────────────────────────────────

    def _browse_video(self):
        """Открывает диалог выбора видеофайла."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите видеофайл DJI",
            str(Path.home()),
            "Видео (*.mp4 *.mov *.MP4 *.MOV);;Все файлы (*)"
        )
        if path:
            self.video_path_edit.setText(path)
            # Предлагаем имя выходного файла
            video_stem = Path(path).stem
            output_dir = Path(path).parent
            suggested_output = str(output_dir / f"{video_stem}_overlay.mov")
            if not self.output_path_edit.text():
                self.output_path_edit.setText(suggested_output)
            self.statusBar().showMessage(f"Выбрано видео: {path}")

    def _browse_output(self):
        """Открывает диалог выбора выходного файла."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить оверлей как",
            str(Path.home() / "overlay_output.mov"),
            "ProRes MOV (*.mov);;WebM (*.webm);;Все файлы (*)"
        )
        if path:
            self.output_path_edit.setText(path)

    def _extract_telemetry(self):
        """Запускает извлечение телеметрии из видео."""
        video_path = self.video_path_edit.text()
        if not video_path:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите видеофайл!")
            return

        self.extract_btn.setEnabled(False)
        self.render_btn.setEnabled(False)
        self.status_label.setText("Извлечение телеметрии...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # неопределённый прогресс

        # Создаём поток
        self._thread = QThread()
        self._worker = TelemetryWorker(video_path)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_telemetry_extracted)
        self._worker.error.connect(self._on_extraction_error)
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def _use_demo_telemetry(self):
        """Генерирует демонстрационную телеметрию."""
        self.status_label.setText("Генерация демо-телеметрии...")
        try:
            from core.extractor import generate_demo_telemetry
            telemetry = generate_demo_telemetry(duration=60.0, fps=30.0)
            self._on_telemetry_extracted(telemetry)
        except Exception as e:
            self._on_extraction_error(f"Ошибка генерации демо: {str(e)}")

    def _on_telemetry_extracted(self, telemetry: dict):
        """Обрабатывает успешно извлечённую телеметрию."""
        self.telemetry_data = telemetry
        self.extract_btn.setEnabled(True)
        self.render_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        pts = telemetry.get("points", [])
        fps = telemetry.get("fps", 0)
        dur = telemetry.get("duration", 0)
        src = telemetry.get("source", "unknown")

        self.meta_label.setText(
            f"Точек: {len(pts)}  |  FPS: {fps:.1f}  |  "
            f"Длительность: {dur:.1f}с  |  Источник: {src}"
        )

        # Показываем первые и последние точки
        preview_pts = pts[:5] + (["..."] if len(pts) > 10 else []) + pts[-5:] if len(pts) > 5 else pts
        preview_data = {
            "fps": fps,
            "duration": dur,
            "total_points": len(pts),
            "source": src,
            "preview_points": preview_pts
        }
        self.telemetry_text.setPlainText(
            json.dumps(preview_data, ensure_ascii=False, indent=2)
        )

        self.status_label.setText(f"Телеметрия готова: {len(pts)} точек")
        self.statusBar().showMessage(f"Телеметрия извлечена: {len(pts)} точек")

    def _on_extraction_error(self, error_msg: str):
        """Обрабатывает ошибку извлечения."""
        self.extract_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Ошибка: {error_msg}")
        self.statusBar().showMessage("Ошибка извлечения телеметрии")
        QMessageBox.critical(self, "Ошибка извлечения", error_msg)

    def _render_overlay(self):
        """Запускает рендеринг оверлея."""
        if not self.telemetry_data:
            QMessageBox.warning(self, "Ошибка", "Сначала извлеките телеметрию!")
            return

        output_path = self.output_path_edit.text()
        if not output_path:
            output_path = str(Path.home() / "overlay_output.mov")
            self.output_path_edit.setText(output_path)

        self.render_btn.setEnabled(False)
        self.extract_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Рендеринг оверлея...")

        config = self.config_manager.config.copy()

        # Создаём поток рендеринга
        self._thread = QThread()
        self._worker = RenderWorker(self.telemetry_data, output_path, config)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_render_finished)
        self._worker.error.connect(self._on_render_error)
        self._worker.progress.connect(self._on_render_progress)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def _on_render_progress(self, current: int, total: int):
        """Обновляет прогресс-бар при рендеринге."""
        if total > 0:
            pct = int(100 * current / total)
            self.progress_bar.setValue(pct)
            self.status_label.setText(f"Рендеринг: кадр {current}/{total} ({pct}%)")

    def _on_render_finished(self, output_path: str):
        """Обрабатывает завершение рендеринга."""
        self.render_btn.setEnabled(True)
        self.extract_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Готово: {output_path}")
        self.statusBar().showMessage(f"Оверлей сохранён: {output_path}")
        QMessageBox.information(
            self,
            "Рендеринг завершён",
            f"Оверлей успешно создан:\n{output_path}"
        )

    def _on_render_error(self, error_msg: str):
        """Обрабатывает ошибку рендеринга."""
        self.render_btn.setEnabled(True)
        self.extract_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ошибка рендеринга")
        self.statusBar().showMessage("Ошибка рендеринга")
        QMessageBox.critical(self, "Ошибка рендеринга", error_msg)

    def _toggle_module(self, key: str, state: int, idx: int):
        """Включает/отключает модуль в конфигурации."""
        enabled = state == Qt.Checked
        modules = self.config_manager.config.get("modules", [])
        type_key = key.split("_")[0]
        matching = [m for m in modules if m.get("type") == type_key]
        if idx < len(matching):
            matching[idx]["enabled"] = enabled

    def _update_map_zoom(self, value: int):
        """Обновляет масштаб карты в конфигурации."""
        for mod in self.config_manager.config.get("modules", []):
            if mod.get("type") == "map":
                mod["zoom"] = value

    def _update_max_speed(self, value: int):
        """Обновляет максимальную скорость в конфигурации."""
        for mod in self.config_manager.config.get("modules", []):
            if mod.get("type") == "speedometer":
                mod["max_speed"] = value

    def _load_config(self):
        """Загружает конфигурацию из файла."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить конфигурацию", str(Path.home()),
            "JSON (*.json);;Все файлы (*)"
        )
        if path:
            try:
                self.config_manager = ConfigManager(path)
                self.statusBar().showMessage(f"Конфигурация загружена: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить конфиг:\n{e}")

    def _save_config(self):
        """Сохраняет конфигурацию в файл."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить конфигурацию", str(Path.home() / "config.json"),
            "JSON (*.json);;Все файлы (*)"
        )
        if path:
            try:
                self.config_manager.save(path)
                self.statusBar().showMessage(f"Конфигурация сохранена: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить конфиг:\n{e}")

    def _show_about(self):
        """Показывает окно «О программе»."""
        QMessageBox.about(
            self,
            "О программе",
            "<b>DJI Telemetry Overlay</b><br><br>"
            "Версия 1.0<br><br>"
            "Приложение для создания прозрачного видеооверлея<br>"
            "с телеметрическими данными из видео DJI.<br><br>"
            "Функции:<br>"
            "• Извлечение GPS-телеметрии из видео DJI<br>"
            "• Спидометр, карта, компас, текстовые поля<br>"
            "• Рендеринг в ProRes 4444 с альфа-каналом<br><br>"
            "Требования: Python 3.8+, FFmpeg, PyQt5, Pillow"
        )
