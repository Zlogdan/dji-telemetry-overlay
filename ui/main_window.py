# -*- coding: utf-8 -*-
"""
Главное окно приложения DJI Telemetry Overlay.
Пользовательский интерфейс на русском языке.
"""

import json
import logging
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QGroupBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QProgressBar,
    QAction, QSplitter, QFrame, QScrollArea,
    QFormLayout, QMessageBox, QComboBox, QTabWidget, QApplication,
)
from PyQt5.QtCore import Qt, QThread
from PyQt5.QtGui import QFont

from config.config_manager import ConfigManager
from modules.map_view import MAP_PROVIDERS, MAP_PROVIDER_LABELS
from ui.layout_canvas import ModuleLayoutCanvas
from ui.preview_window import PreviewWindow
from ui.workers import TelemetryWorker, RenderWorker

logger = logging.getLogger(__name__)


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
        self._apply_config_to_ui()

    # ── Построение интерфейса ────────────────────────────────────────

    def _setup_ui(self):
        """Строит основной интерфейс."""
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self._build_main_tab(), "Основное")
        self.tabs.addTab(self._build_settings_tab(), "Настройки")
        self.tabs.addTab(self._build_layout_tab(), "Расположение")

    def _build_main_tab(self) -> QWidget:
        """Вкладка «Основное»: файлы, действия и предпросмотр."""
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
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

        return widget

    def _build_settings_tab(self) -> QWidget:
        """Вкладка «Настройки»: модули, параметры отображения, производительность."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(self._build_modules_group())
        layout.addWidget(self._build_params_group())
        layout.addWidget(self._build_export_group())
        layout.addWidget(self._build_performance_group())
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    def _build_layout_tab(self) -> QWidget:
        """Вкладка визуального позиционирования модулей."""
        widget = QWidget()
        main_layout = QHBoxLayout(widget)
        main_layout.setSpacing(8)

        # Верхняя панель со статусом
        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.layout_status_label = QLabel("Загрузите телеметрию для просмотра превью")
        self.layout_status_label.setStyleSheet("color: #6B8E23; font-size: 11px;")
        top_layout.addWidget(self.layout_status_label)

        # Холст карты
        self.layout_canvas = ModuleLayoutCanvas(self.config_manager.config)
        self.layout_canvas.set_show_preview(True)  # Явно включаем отображение превью
        self.layout_canvas.moduleMoved.connect(self._sync_layout_controls)
        top_layout.addWidget(self.layout_canvas, 1)

        main_layout.addWidget(top_panel, 1)

        panel = QGroupBox("Выбранный модуль")
        form = QFormLayout(panel)

        self.layout_module_combo = QComboBox()
        self.layout_module_combo.currentIndexChanged.connect(self._on_layout_module_changed)
        form.addRow("Модуль:", self.layout_module_combo)

        self.layout_x_spin = QSpinBox()
        self.layout_x_spin.setRange(0, 10000)
        self.layout_x_spin.valueChanged.connect(self._update_layout_module)
        form.addRow("X:", self.layout_x_spin)

        self.layout_y_spin = QSpinBox()
        self.layout_y_spin.setRange(0, 10000)
        self.layout_y_spin.valueChanged.connect(self._update_layout_module)
        form.addRow("Y:", self.layout_y_spin)

        self.layout_w_spin = QSpinBox()
        self.layout_w_spin.setRange(20, 4000)
        self.layout_w_spin.valueChanged.connect(self._update_layout_module)
        form.addRow("Ширина:", self.layout_w_spin)

        self.layout_h_spin = QSpinBox()
        self.layout_h_spin.setRange(20, 4000)
        self.layout_h_spin.valueChanged.connect(self._update_layout_module)
        form.addRow("Высота:", self.layout_h_spin)

        apply_bounds_btn = QPushButton("Прижать к границам")
        apply_bounds_btn.clicked.connect(self._clamp_layout_modules)
        form.addRow(apply_bounds_btn)

        preview_btn = QPushButton("Открыть полный предпросмотр")
        preview_btn.clicked.connect(self._show_preview_window)
        form.addRow(preview_btn)

        main_layout.addWidget(panel)

        self._refresh_layout_module_list()
        return widget

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
            cb = QCheckBox(f"Текст ({label})")
            cb.setChecked(tm.get("enabled", True))
            # Захватываем type_str и module_idx явно чтобы избежать проблем с замыканием
            cb.stateChanged.connect(lambda state, type_str="text", module_idx=i: self._toggle_module(type_str, state, module_idx))
            layout.addWidget(cb)
            self.module_checkboxes[f"text_{field}_{i}"] = (cb, "text", i)

        # Остальные модули
        for type_key, type_label in module_labels.items():
            matching = [m for m in modules_cfg if m.get("type") == type_key]
            for idx, mod in enumerate(matching):
                cb = QCheckBox(type_label)
                cb.setChecked(mod.get("enabled", True))
                cb.stateChanged.connect(lambda state, type_str=type_key, module_idx=idx: self._toggle_module(type_str, state, module_idx))
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

        # Провайдер карты
        self.map_provider_combo = QComboBox()
        for key in MAP_PROVIDERS:
            self.map_provider_combo.addItem(MAP_PROVIDER_LABELS.get(key, key), key)
        current_provider = self._get_current_map_provider()
        idx = self.map_provider_combo.findData(current_provider)
        if idx >= 0:
            self.map_provider_combo.setCurrentIndex(idx)
        self.map_provider_combo.currentIndexChanged.connect(self._update_map_provider)
        layout.addRow("Провайдер карты:", self.map_provider_combo)

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
        self.width_spin.valueChanged.connect(lambda v: self._update_canvas_size("width", v))
        layout.addRow("Ширина кадра:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 4320)
        self.height_spin.setValue(self.config_manager.config.get("height", 1080))
        self.height_spin.setSingleStep(16)
        self.height_spin.valueChanged.connect(lambda v: self._update_canvas_size("height", v))
        layout.addRow("Высота кадра:", self.height_spin)

        return group

    def _build_export_group(self) -> QGroupBox:
        """Группа настроек экспорта: режим, формат, FPS."""
        group = QGroupBox("Экспорт")
        layout = QFormLayout(group)
        layout.setSpacing(6)

        export_cfg = self.config_manager.config.setdefault("export", {})

        self.export_mode_combo = QComboBox()
        self.export_mode_combo.addItem("Видео", "video")
        self.export_mode_combo.addItem("PNG sequence", "png_sequence")
        mode = str(export_cfg.get("mode", "video"))
        mode_idx = self.export_mode_combo.findData(mode)
        self.export_mode_combo.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)
        self.export_mode_combo.currentIndexChanged.connect(self._on_export_mode_changed)
        layout.addRow("Режим:", self.export_mode_combo)

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItem("ProRes MOV (alpha)", "mov")
        self.output_format_combo.addItem("WebM VP9 (alpha)", "webm")
        out_fmt = str(export_cfg.get("output_format", "mov"))
        fmt_idx = self.output_format_combo.findData(out_fmt)
        self.output_format_combo.setCurrentIndex(fmt_idx if fmt_idx >= 0 else 0)
        self.output_format_combo.currentIndexChanged.connect(self._on_output_format_changed)
        layout.addRow("Формат:", self.output_format_combo)

        self.render_fps_spin = QDoubleSpinBox()
        self.render_fps_spin.setRange(0.0, 240.0)
        self.render_fps_spin.setDecimals(2)
        self.render_fps_spin.setSingleStep(1.0)
        self.render_fps_spin.setValue(float(export_cfg.get("render_fps", 30)))
        self.render_fps_spin.setToolTip(
            "FPS оверлея. 0 = использовать FPS исходного видео.\n"
            "Для экономии размера обычно 1-30 FPS."
        )
        self.render_fps_spin.valueChanged.connect(lambda v: self._update_export_config("render_fps", float(v)))
        layout.addRow("FPS оверлея:", self.render_fps_spin)

        return group

    def _build_performance_group(self) -> QGroupBox:
        """Группа настроек производительности (актуально для 4K/120fps)."""
        group = QGroupBox("Производительность (4K / 120fps)")
        layout = QFormLayout(group)
        layout.setSpacing(6)

        perf = self.config_manager.config.get("performance", {})

        # Таймаут ffprobe
        self.ffprobe_timeout_spin = QSpinBox()
        self.ffprobe_timeout_spin.setRange(10, 600)
        self.ffprobe_timeout_spin.setValue(int(perf.get("ffprobe_timeout", 30)))
        self.ffprobe_timeout_spin.setSuffix(" с")
        self.ffprobe_timeout_spin.setToolTip(
            "Максимальное время ожидания при анализе видеофайла (ffprobe).\n"
            "Для файлов 8+ ГБ рекомендуется увеличить до 120–300 с."
        )
        self.ffprobe_timeout_spin.valueChanged.connect(
            lambda v: self._update_perf_config("ffprobe_timeout", v)
        )
        layout.addRow("Таймаут ffprobe:", self.ffprobe_timeout_spin)

        # Таймаут ffmpeg
        self.ffmpeg_timeout_spin = QSpinBox()
        self.ffmpeg_timeout_spin.setRange(10, 600)
        self.ffmpeg_timeout_spin.setValue(int(perf.get("ffmpeg_timeout", 60)))
        self.ffmpeg_timeout_spin.setSuffix(" с")
        self.ffmpeg_timeout_spin.setToolTip(
            "Максимальное время ожидания при извлечении потока данных (ffmpeg).\n"
            "Для длинных видео рекомендуется увеличить до 120–300 с."
        )
        self.ffmpeg_timeout_spin.valueChanged.connect(
            lambda v: self._update_perf_config("ffmpeg_timeout", v)
        )
        layout.addRow("Таймаут ffmpeg:", self.ffmpeg_timeout_spin)

        # Уровень сжатия PNG
        self.png_compress_spin = QSpinBox()
        self.png_compress_spin.setRange(0, 9)
        self.png_compress_spin.setValue(int(perf.get("png_compress_level", 1)))
        self.png_compress_spin.setToolTip(
            "Уровень сжатия PNG-кадров при рендеринге.\n"
            "0 — без сжатия (быстрее, больше нагрузка на pipe).\n"
            "1 — быстрое сжатие (рекомендуется для 4K/120fps).\n"
            "9 — максимальное сжатие (медленнее)."
        )
        self.png_compress_spin.valueChanged.connect(
            lambda v: self._update_perf_config("png_compress_level", v)
        )
        layout.addRow("Сжатие PNG (0–9):", self.png_compress_spin)

        self.prores_qscale_spin = QSpinBox()
        self.prores_qscale_spin.setRange(1, 31)
        self.prores_qscale_spin.setValue(int(perf.get("prores_qscale", 11)))
        self.prores_qscale_spin.setToolTip("Качество ProRes: меньше значение = выше качество и больше размер.")
        self.prores_qscale_spin.valueChanged.connect(
            lambda v: self._update_perf_config("prores_qscale", v)
        )
        layout.addRow("ProRes qscale (1-31):", self.prores_qscale_spin)

        self.vp9_crf_spin = QSpinBox()
        self.vp9_crf_spin.setRange(0, 63)
        self.vp9_crf_spin.setValue(int(perf.get("vp9_crf", 34)))
        self.vp9_crf_spin.setToolTip("Качество VP9: меньше значение = выше качество и больше размер.")
        self.vp9_crf_spin.valueChanged.connect(
            lambda v: self._update_perf_config("vp9_crf", v)
        )
        layout.addRow("VP9 CRF (0-63):", self.vp9_crf_spin)

        self.vp9_cpu_spin = QSpinBox()
        self.vp9_cpu_spin.setRange(0, 8)
        self.vp9_cpu_spin.setValue(int(perf.get("vp9_cpu_used", 2)))
        self.vp9_cpu_spin.setToolTip("Скорость кодирования VP9: больше значение = быстрее, но хуже сжатие.")
        self.vp9_cpu_spin.valueChanged.connect(
            lambda v: self._update_perf_config("vp9_cpu_used", v)
        )
        layout.addRow("VP9 cpu-used (0-8):", self.vp9_cpu_spin)

        hint = QLabel(
            "⚠ Для видео 4K/120fps рекомендуется: таймауты 120–300 с, сжатие PNG = 0 или 1."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addRow(hint)

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
            "Выберите видеофайл и нажмите «Извлечь телеметрию»."
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

    def _apply_config_to_ui(self):
        """Синхронизирует контролы интерфейса с текущей конфигурацией."""
        cfg = self.config_manager.config
        perf = cfg.get("performance", {})
        export_cfg = cfg.get("export", {})

        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        self.width_spin.setValue(int(cfg.get("width", 1920)))
        self.height_spin.setValue(int(cfg.get("height", 1080)))
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)

        self.ffprobe_timeout_spin.blockSignals(True)
        self.ffmpeg_timeout_spin.blockSignals(True)
        self.png_compress_spin.blockSignals(True)
        self.prores_qscale_spin.blockSignals(True)
        self.vp9_crf_spin.blockSignals(True)
        self.vp9_cpu_spin.blockSignals(True)

        self.ffprobe_timeout_spin.setValue(int(perf.get("ffprobe_timeout", 30)))
        self.ffmpeg_timeout_spin.setValue(int(perf.get("ffmpeg_timeout", 60)))
        self.png_compress_spin.setValue(int(perf.get("png_compress_level", 1)))
        self.prores_qscale_spin.setValue(int(perf.get("prores_qscale", 11)))
        self.vp9_crf_spin.setValue(int(perf.get("vp9_crf", 34)))
        self.vp9_cpu_spin.setValue(int(perf.get("vp9_cpu_used", 2)))

        self.ffprobe_timeout_spin.blockSignals(False)
        self.ffmpeg_timeout_spin.blockSignals(False)
        self.png_compress_spin.blockSignals(False)
        self.prores_qscale_spin.blockSignals(False)
        self.vp9_crf_spin.blockSignals(False)
        self.vp9_cpu_spin.blockSignals(False)

        self.export_mode_combo.blockSignals(True)
        self.output_format_combo.blockSignals(True)
        self.render_fps_spin.blockSignals(True)

        mode = str(export_cfg.get("mode", "video"))
        mode_idx = self.export_mode_combo.findData(mode)
        self.export_mode_combo.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)

        out_fmt = str(export_cfg.get("output_format", "mov"))
        fmt_idx = self.output_format_combo.findData(out_fmt)
        self.output_format_combo.setCurrentIndex(fmt_idx if fmt_idx >= 0 else 0)

        self.render_fps_spin.setValue(float(export_cfg.get("render_fps", 30)))

        self.export_mode_combo.blockSignals(False)
        self.output_format_combo.blockSignals(False)
        self.render_fps_spin.blockSignals(False)

        self.layout_canvas.set_config(cfg)
        self._refresh_layout_module_list()
        self._on_export_mode_changed(self.export_mode_combo.currentIndex())
        self._sync_output_for_export_settings()

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
            mode = self.export_mode_combo.currentData() if hasattr(self, "export_mode_combo") else "video"
            out_fmt = self.output_format_combo.currentData() if hasattr(self, "output_format_combo") else "mov"
            if mode == "png_sequence":
                suggested_output = str(output_dir / f"{video_stem}_overlay_png")
            else:
                suggested_output = str(output_dir / f"{video_stem}_overlay.{out_fmt}")
            if not self.output_path_edit.text():
                self.output_path_edit.setText(suggested_output)
            self.statusBar().showMessage(f"Выбрано видео: {path}")

    def _browse_output(self):
        """Открывает диалог выбора выходного файла."""
        mode = self.export_mode_combo.currentData() if hasattr(self, "export_mode_combo") else "video"
        if mode == "png_sequence":
            path = QFileDialog.getExistingDirectory(
                self,
                "Папка для PNG sequence",
                str(Path.home() / "overlay_frames")
            )
            if path:
                self.output_path_edit.setText(path)
            return

        selected_fmt = self.output_format_combo.currentData() if hasattr(self, "output_format_combo") else "mov"
        default_name = f"overlay_output.{selected_fmt}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить оверлей как",
            str(Path.home() / default_name),
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
        self._worker = TelemetryWorker(
            video_path,
            perf_config=self.config_manager.config.get("performance", {}),
            extract_config=self.config_manager.config.get("extraction", {}),
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_telemetry_extracted)
        self._worker.error.connect(self._on_extraction_error)
        self._worker.progress.connect(self.status_label.setText)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)

        self._thread.start()

    def _on_telemetry_extracted(self, telemetry: dict):
        """Обрабатывает успешно извлечённую телеметрию."""
        self.telemetry_data = telemetry
        self.extract_btn.setEnabled(True)
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

        if pts:
            self.render_btn.setEnabled(True)
            # Открываем окно предпросмотра
            self._show_preview_window()
            # Обновляем превью при загрузке новой телеметрии
            self._refresh_layout_preview()
        else:
            self.render_btn.setEnabled(False)
            self.status_label.setText("Телеметрия не найдена в файле")
            self.statusBar().showMessage("Телеметрия не найдена")
            self.layout_canvas.set_preview_image(None)
            self.layout_status_label.setText("Телеметрия не найдена")

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
            if self.export_mode_combo.currentData() == "png_sequence":
                output_path = str(Path.home() / "overlay_frames")
            else:
                output_path = str(Path.home() / f"overlay_output.{self.output_format_combo.currentData()}")
            self.output_path_edit.setText(output_path)

        if self.export_mode_combo.currentData() != "png_sequence":
            output_path = self._ensure_output_extension(output_path)
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
        mode = self.config_manager.config.get("export", {}).get("mode", "video")
        done_msg = "PNG sequence сохранена" if mode == "png_sequence" else "Оверлей сохранён"
        self.statusBar().showMessage(f"{done_msg}: {output_path}")
        QMessageBox.information(
            self,
            "Рендеринг завершён",
            f"{done_msg}:\n{output_path}"
        )

    def _on_render_error(self, error_msg: str):
        """Обрабатывает ошибку рендеринга."""
        self.render_btn.setEnabled(True)
        self.extract_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ошибка рендеринга")
        self.statusBar().showMessage("Ошибка рендеринга")
        QMessageBox.critical(self, "Ошибка рендеринга", error_msg)

    def _toggle_module(self, type_key: str, state: int, idx: int):
        """Включает/отключает модуль в конфигурации по типу и индексу."""
        enabled = state == Qt.Checked
        modules = self.config_manager.config.get("modules", [])
        matching = [m for m in modules if m.get("type") == type_key]
        if idx < len(matching):
            matching[idx]["enabled"] = enabled
        self.layout_canvas.update()

    def _update_map_zoom(self, value: int):
        """Обновляет масштаб карты в конфигурации."""
        for mod in self.config_manager.config.get("modules", []):
            if mod.get("type") == "map":
                mod["zoom"] = value
        self._refresh_layout_preview()

    def _get_current_map_provider(self) -> str:
        """Возвращает текущий провайдер карты из конфигурации."""
        for mod in self.config_manager.config.get("modules", []):
            if mod.get("type") == "map":
                return mod.get("map_provider", "osm")
        return "osm"

    def _update_map_provider(self, index: int):
        """Обновляет провайдер карты в конфигурации."""
        provider = self.map_provider_combo.itemData(index)
        for mod in self.config_manager.config.get("modules", []):
            if mod.get("type") == "map":
                mod["map_provider"] = provider
        self._refresh_layout_preview()

    def _update_max_speed(self, value: int):
        """Обновляет максимальную скорость в конфигурации."""
        for mod in self.config_manager.config.get("modules", []):
            if mod.get("type") == "speedometer":
                mod["max_speed"] = value

    def _update_perf_config(self, key: str, value):
        """Обновляет настройку производительности в конфигурации."""
        if "performance" not in self.config_manager.config:
            self.config_manager.config["performance"] = {}
        self.config_manager.config["performance"][key] = value

    def _update_export_config(self, key: str, value):
        """Обновляет настройки экспорта в конфигурации."""
        if "export" not in self.config_manager.config:
            self.config_manager.config["export"] = {}
        self.config_manager.config["export"][key] = value

    def _on_export_mode_changed(self, index: int):
        mode = self.export_mode_combo.itemData(index)
        self._update_export_config("mode", mode)
        self.output_format_combo.setEnabled(mode == "video")
        self._sync_output_for_export_settings()

    def _on_output_format_changed(self, index: int):
        out_fmt = self.output_format_combo.itemData(index)
        self._update_export_config("output_format", out_fmt)
        self._sync_output_for_export_settings()

    def _sync_output_for_export_settings(self):
        path = self.output_path_edit.text().strip()
        mode = self.export_mode_combo.currentData()

        if mode == "png_sequence":
            if not path or Path(path).suffix.lower() in (".mov", ".webm"):
                self.output_path_edit.setText(str(Path.home() / "overlay_frames"))
            return

        if not path:
            self.output_path_edit.setText(str(Path.home() / f"overlay_output.{self.output_format_combo.currentData()}"))
            return

        self.output_path_edit.setText(self._ensure_output_extension(path))

    def _ensure_output_extension(self, output_path: str) -> str:
        p = Path(output_path)
        target_ext = f".{self.output_format_combo.currentData()}"
        if p.suffix.lower() != target_ext:
            p = p.with_suffix(target_ext)
        return str(p)

    def _update_canvas_size(self, key: str, value: int):
        self.config_manager.config[key] = value
        self._clamp_layout_modules()
        self.layout_canvas.update()

    def _refresh_layout_module_list(self):
        modules = self.config_manager.config.get("modules", [])
        current_idx = self.layout_module_combo.currentIndex() if hasattr(self, "layout_module_combo") else 0
        self.layout_module_combo.blockSignals(True)
        self.layout_module_combo.clear()
        for idx, mod in enumerate(modules):
            label = f"{idx + 1}. {mod.get('type', 'module')}"
            if mod.get("type") == "text" and mod.get("field"):
                label += f" ({mod.get('field')})"
            self.layout_module_combo.addItem(label, idx)
        self.layout_module_combo.blockSignals(False)

        if self.layout_module_combo.count() > 0:
            self.layout_module_combo.setCurrentIndex(min(max(current_idx, 0), self.layout_module_combo.count() - 1))
            self._on_layout_module_changed(self.layout_module_combo.currentIndex())
        else:
            self.layout_canvas.set_active_index(-1)

    def _sync_layout_controls(self, module_index: int):
        modules = self.config_manager.config.get("modules", [])
        if module_index < 0 or module_index >= len(modules):
            return

        mod = modules[module_index]
        self.layout_module_combo.blockSignals(True)
        self.layout_module_combo.setCurrentIndex(module_index)
        self.layout_module_combo.blockSignals(False)

        self.layout_x_spin.blockSignals(True)
        self.layout_y_spin.blockSignals(True)
        self.layout_w_spin.blockSignals(True)
        self.layout_h_spin.blockSignals(True)

        self.layout_x_spin.setValue(int(mod.get("x", 0)))
        self.layout_y_spin.setValue(int(mod.get("y", 0)))
        self.layout_w_spin.setValue(int(mod.get("width", 200)))
        self.layout_h_spin.setValue(int(mod.get("height", 120)))

        self.layout_x_spin.blockSignals(False)
        self.layout_y_spin.blockSignals(False)
        self.layout_w_spin.blockSignals(False)
        self.layout_h_spin.blockSignals(False)

        self.layout_canvas.set_active_index(module_index)

    def _on_layout_module_changed(self, index: int):
        self._sync_layout_controls(index)

    def _update_layout_module(self, _value: int):
        idx = self.layout_module_combo.currentIndex()
        modules = self.config_manager.config.get("modules", [])
        if idx < 0 or idx >= len(modules):
            return

        mod = modules[idx]
        mod["x"] = int(self.layout_x_spin.value())
        mod["y"] = int(self.layout_y_spin.value())
        mod["width"] = int(self.layout_w_spin.value())
        mod["height"] = int(self.layout_h_spin.value())
        self._clamp_layout_modules()
        self.layout_canvas.update()

    def _clamp_layout_modules(self):
        width = int(self.config_manager.config.get("width", 1920))
        height = int(self.config_manager.config.get("height", 1080))
        for mod in self.config_manager.config.get("modules", []):
            w = max(20, int(mod.get("width", 200)))
            h = max(20, int(mod.get("height", 120)))
            x = max(0, min(int(mod.get("x", 0)), max(0, width - w)))
            y = max(0, min(int(mod.get("y", 0)), max(0, height - h)))
            mod["width"] = w
            mod["height"] = h
            mod["x"] = x
            mod["y"] = y

    def _on_tab_changed(self, index: int):
        """Обработчик смены вкладки — обновляет превью при открытии Расположение."""
        if index == 2:  # Вкладка "Расположение"
            self._refresh_layout_preview()

    def _refresh_layout_preview(self):
        """Обновляет превью первого кадра на вкладке расположения."""
        if not self.telemetry_data:
            logger.debug("Нет данных телеметрии для превью")
            self.layout_canvas.set_preview_image(None)
            self.layout_status_label.setText("Телеметрия не загружена")
            return

        try:
            pts = self.telemetry_data.get("points", [])
            logger.info(f"Обновление превью: {len(pts)} точек телеметрии")
            self.layout_status_label.setText(f"Рендеринг превью ({len(pts)} точек)...")
            QApplication.processEvents()  # Даём UI обновиться
            
            from renderer.engine import RenderEngine
            engine = RenderEngine(self.config_manager.config)
            preview_frame = engine.get_preview_frame(self.telemetry_data, frame_index=0)
            
            if preview_frame is None:
                logger.warning("get_preview_frame вернул None")
                self.layout_status_label.setText("Ошибка: превью не отрендерено")
                self.layout_canvas.set_preview_image(None)
            else:
                logger.info(f"Превью успешно отрендерено: {preview_frame.size}")
                self.layout_canvas.set_preview_image(preview_frame)
                self.layout_status_label.setText(f"Превью готово ({preview_frame.size[0]}x{preview_frame.size[1]})")
        except Exception as e:
            logger.error(f"Ошибка рендера превью: {e}", exc_info=True)
            self.layout_status_label.setText(f"Ошибка превью: {str(e)[:60]}")
            self.layout_canvas.set_preview_image(None)
        finally:
            self.layout_canvas.update()

    def _show_preview_window(self):
        """Открывает окно предпросмотра кадров."""
        if not self.telemetry_data:
            QMessageBox.warning(self, "Ошибка", "Нет данных телеметрии!")
            return
        
        try:
            preview_window = PreviewWindow(self.telemetry_data, self.config_manager.config, self)
            preview_window.exec()
        except Exception as e:
            logger.error(f"Ошибка открытия окна предпросмотра: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть окно предпросмотра:\n{str(e)}")

    def _load_config(self):
        """Загружает конфигурацию из файла."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить конфигурацию", str(Path.home()),
            "JSON (*.json);;Все файлы (*)"
        )
        if path:
            try:
                self.config_manager = ConfigManager(path)
                self._apply_config_to_ui()
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
