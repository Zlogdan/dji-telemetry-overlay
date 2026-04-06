# -*- coding: utf-8 -*-
"""Функции построения интерфейса для MainWindow."""

from modules.map_view import MAP_PROVIDERS, MAP_PROVIDER_LABELS
from ui.layout_canvas import ModuleLayoutCanvas

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def setup_ui(window):
    """Строит основной интерфейс."""
    window.tabs = QTabWidget()
    window.tabs.currentChanged.connect(window._on_tab_changed)
    window.setCentralWidget(window.tabs)

    window.tabs.addTab(build_main_tab(window), "Основное")
    window.tabs.addTab(build_settings_tab(window), "Настройки")
    window.tabs.addTab(build_layout_tab(window), "Расположение")
    window.tabs.addTab(build_batch_tab(window), "Пакетная обработка")


def build_main_tab(window) -> QWidget:
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

    left_layout.addWidget(build_files_group(window))
    left_layout.addWidget(build_actions_group(window))
    left_layout.addStretch()

    # Правая панель результатов
    right_widget = QWidget()
    right_layout = QVBoxLayout(right_widget)
    right_layout.setSpacing(6)
    right_layout.addWidget(build_preview_group(window))

    splitter.addWidget(left_widget)
    splitter.addWidget(right_widget)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)

    return widget


def build_settings_tab(window) -> QWidget:
    """Вкладка «Настройки»: модули, параметры отображения, производительность."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setSpacing(10)
    layout.setContentsMargins(12, 12, 12, 12)

    layout.addWidget(build_params_group(window))
    layout.addWidget(build_export_group(window))
    layout.addWidget(build_performance_group(window))
    layout.addStretch()

    scroll.setWidget(container)
    return scroll


def build_layout_tab(window) -> QWidget:
    """Вкладка визуального позиционирования модулей."""
    widget = QWidget()
    main_layout = QHBoxLayout(widget)
    main_layout.setSpacing(8)

    # Верхняя панель со статусом
    top_panel = QWidget()
    top_layout = QVBoxLayout(top_panel)
    top_layout.setContentsMargins(0, 0, 0, 0)

    window.layout_status_label = QLabel("Загрузите телеметрию для просмотра превью")
    window.layout_status_label.setStyleSheet("color: #6B8E23; font-size: 11px;")
    top_layout.addWidget(window.layout_status_label)

    # Холст карты
    window.layout_canvas = ModuleLayoutCanvas(window.config_manager.config)
    window.layout_canvas.set_show_preview(True)  # Явно включаем отображение превью
    window.layout_canvas.moduleMoved.connect(window._sync_layout_controls)
    top_layout.addWidget(window.layout_canvas, 1)

    main_layout.addWidget(top_panel, 1)

    right_panel = QWidget()
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(8)

    right_layout.addWidget(build_modules_group(window))
    right_layout.addWidget(build_map_controls_group(window))

    panel = QGroupBox("Выбранный модуль")
    form = QFormLayout(panel)

    window.layout_module_combo = QComboBox()
    window.layout_module_combo.currentIndexChanged.connect(window._on_layout_module_changed)
    form.addRow("Модуль:", window.layout_module_combo)

    window.layout_x_spin = QSpinBox()
    window.layout_x_spin.setRange(0, 10000)
    window.layout_x_spin.valueChanged.connect(window._update_layout_module)
    form.addRow("X:", window.layout_x_spin)

    window.layout_y_spin = QSpinBox()
    window.layout_y_spin.setRange(0, 10000)
    window.layout_y_spin.valueChanged.connect(window._update_layout_module)
    form.addRow("Y:", window.layout_y_spin)

    window.layout_w_spin = QSpinBox()
    window.layout_w_spin.setRange(20, 4000)
    window.layout_w_spin.valueChanged.connect(window._update_layout_module)
    form.addRow("Ширина:", window.layout_w_spin)

    window.layout_h_spin = QSpinBox()
    window.layout_h_spin.setRange(20, 4000)
    window.layout_h_spin.valueChanged.connect(window._update_layout_module)
    form.addRow("Высота:", window.layout_h_spin)

    apply_bounds_btn = QPushButton("Прижать к границам")
    apply_bounds_btn.clicked.connect(window._clamp_layout_modules)
    form.addRow(apply_bounds_btn)

    preview_btn = QPushButton("Открыть полный предпросмотр")
    preview_btn.clicked.connect(window._show_preview_window)
    form.addRow(preview_btn)

    right_layout.addWidget(panel)
    right_layout.addStretch()
    main_layout.addWidget(right_panel)

    window._refresh_layout_module_list()
    return widget


def build_files_group(window) -> QGroupBox:
    """Группа выбора файлов."""
    group = QGroupBox("Файлы")
    layout = QFormLayout(group)
    layout.setSpacing(6)

    # Исходное видео
    video_row = QWidget()
    video_layout = QHBoxLayout(video_row)
    video_layout.setContentsMargins(0, 0, 0, 0)
    window.video_path_edit = QLineEdit()
    window.video_path_edit.setReadOnly(True)
    window.video_path_edit.setPlaceholderText("Не выбран...")
    browse_video_btn = QPushButton("Обзор...")
    browse_video_btn.setFixedWidth(80)
    browse_video_btn.clicked.connect(window._browse_video)
    video_layout.addWidget(window.video_path_edit)
    video_layout.addWidget(browse_video_btn)
    layout.addRow("Исходное видео:", video_row)

    # Выходной файл
    output_row = QWidget()
    output_layout = QHBoxLayout(output_row)
    output_layout.setContentsMargins(0, 0, 0, 0)
    window.output_path_edit = QLineEdit()
    window.output_path_edit.setPlaceholderText("overlay_output.mov")
    browse_output_btn = QPushButton("Обзор...")
    browse_output_btn.setFixedWidth(80)
    browse_output_btn.clicked.connect(window._browse_output)
    output_layout.addWidget(window.output_path_edit)
    output_layout.addWidget(browse_output_btn)
    layout.addRow("Выходной файл:", output_row)

    return group


def build_actions_group(window) -> QGroupBox:
    """Группа кнопок действий."""
    group = QGroupBox("Действия")
    layout = QVBoxLayout(group)
    layout.setSpacing(6)

    # Кнопка извлечения телеметрии
    window.extract_btn = QPushButton("Извлечь телеметрию")
    window.extract_btn.setMinimumHeight(38)
    window.extract_btn.setStyleSheet(
        "QPushButton { background-color: #2d7a2d; color: white; font-weight: bold; border-radius: 4px; }"
        "QPushButton:hover { background-color: #3a9e3a; }"
        "QPushButton:disabled { background-color: #555; color: #888; }"
    )
    window.extract_btn.clicked.connect(window._extract_telemetry)
    layout.addWidget(window.extract_btn)

    # Кнопка создания оверлея
    window.render_btn = QPushButton("Создать оверлей")
    window.render_btn.setMinimumHeight(38)
    window.render_btn.setEnabled(False)
    window.render_btn.setStyleSheet(
        "QPushButton { background-color: #1a5a8a; color: white; font-weight: bold; border-radius: 4px; }"
        "QPushButton:hover { background-color: #2070aa; }"
        "QPushButton:disabled { background-color: #555; color: #888; }"
    )
    window.render_btn.clicked.connect(window._render_overlay)
    layout.addWidget(window.render_btn)

    # Прогресс-бар
    window.progress_bar = QProgressBar()
    window.progress_bar.setVisible(False)
    window.progress_bar.setTextVisible(True)
    layout.addWidget(window.progress_bar)

    # Статус
    window.status_label = QLabel("Готов к работе")
    window.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
    layout.addWidget(window.status_label)

    return group


def build_modules_group(window) -> QGroupBox:
    """Группа выбора активных модулей."""
    group = QGroupBox("Модули")
    layout = QVBoxLayout(group)
    layout.setSpacing(4)

    window.module_checkboxes = {}
    modules_cfg = window.config_manager.config.get("modules", [])

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
        cb.stateChanged.connect(lambda state, type_str="text", module_idx=i: window._toggle_module(type_str, state, module_idx))
        layout.addWidget(cb)
        window.module_checkboxes[f"text_{field}_{i}"] = (cb, "text", i)

    # Остальные модули
    for type_key, type_label in module_labels.items():
        matching = [m for m in modules_cfg if m.get("type") == type_key]
        for idx, mod in enumerate(matching):
            cb = QCheckBox(type_label)
            cb.setChecked(mod.get("enabled", True))
            cb.stateChanged.connect(lambda state, type_str=type_key, module_idx=idx: window._toggle_module(type_str, state, module_idx))
            layout.addWidget(cb)
            window.module_checkboxes[f"{type_key}_{idx}"] = (cb, type_key, idx)

    return group


def build_params_group(window) -> QGroupBox:
    """Группа настройки параметров."""
    group = QGroupBox("Параметры")
    layout = QFormLayout(group)
    layout.setSpacing(6)

    # Размер кадра
    window.width_spin = QSpinBox()
    window.width_spin.setRange(320, 7680)
    window.width_spin.setValue(window.config_manager.config.get("width", 1920))
    window.width_spin.setSingleStep(16)
    window.width_spin.valueChanged.connect(lambda v: window._update_canvas_size("width", v))
    layout.addRow("Ширина кадра:", window.width_spin)

    window.height_spin = QSpinBox()
    window.height_spin.setRange(240, 4320)
    window.height_spin.setValue(window.config_manager.config.get("height", 1080))
    window.height_spin.setSingleStep(16)
    window.height_spin.valueChanged.connect(lambda v: window._update_canvas_size("height", v))
    layout.addRow("Высота кадра:", window.height_spin)

    return group


def build_map_controls_group(window) -> QGroupBox:
    """Группа настройки карты и спидометра на вкладке расположения."""
    group = QGroupBox("Карта и скорость")
    layout = QFormLayout(group)
    layout.setSpacing(6)

    # Масштаб карты
    window.zoom_spin = QSpinBox()
    window.zoom_spin.setRange(1, 19)
    window.zoom_spin.setValue(14)
    window.zoom_spin.setSuffix("  (уровень)")
    window.zoom_spin.valueChanged.connect(window._update_map_zoom)
    layout.addRow("Масштаб карты:", window.zoom_spin)

    # Провайдер карты
    window.map_provider_combo = QComboBox()
    for key in MAP_PROVIDERS:
        window.map_provider_combo.addItem(MAP_PROVIDER_LABELS.get(key, key), key)
    current_provider = window._get_current_map_provider()
    idx = window.map_provider_combo.findData(current_provider)
    if idx >= 0:
        window.map_provider_combo.setCurrentIndex(idx)
    window.map_provider_combo.currentIndexChanged.connect(window._update_map_provider)
    layout.addRow("Провайдер карты:", window.map_provider_combo)

    # Максимальная скорость
    window.max_speed_spin = QSpinBox()
    window.max_speed_spin.setRange(10, 500)
    window.max_speed_spin.setValue(150)
    window.max_speed_spin.setSuffix(" км/ч")
    window.max_speed_spin.valueChanged.connect(window._update_max_speed)
    layout.addRow("Макс. скорость:", window.max_speed_spin)

    return group


def build_export_group(window) -> QGroupBox:
    """Группа настроек экспорта: режим, формат, FPS."""
    group = QGroupBox("Экспорт")
    layout = QFormLayout(group)
    layout.setSpacing(6)

    export_cfg = window.config_manager.config.setdefault("export", {})

    window.export_mode_combo = QComboBox()
    window.export_mode_combo.addItem("Видео", "video")
    window.export_mode_combo.addItem("PNG sequence", "png_sequence")
    mode = str(export_cfg.get("mode", "video"))
    mode_idx = window.export_mode_combo.findData(mode)
    window.export_mode_combo.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)
    window.export_mode_combo.currentIndexChanged.connect(window._on_export_mode_changed)
    layout.addRow("Режим:", window.export_mode_combo)

    window.output_format_combo = QComboBox()
    window.output_format_combo.addItem("ProRes MOV (alpha)", "mov")
    window.output_format_combo.addItem("WebM VP9 (alpha)", "webm")
    out_fmt = str(export_cfg.get("output_format", "mov"))
    fmt_idx = window.output_format_combo.findData(out_fmt)
    window.output_format_combo.setCurrentIndex(fmt_idx if fmt_idx >= 0 else 0)
    window.output_format_combo.currentIndexChanged.connect(window._on_output_format_changed)
    layout.addRow("Формат:", window.output_format_combo)

    window.render_fps_spin = QDoubleSpinBox()
    window.render_fps_spin.setRange(0.0, 240.0)
    window.render_fps_spin.setDecimals(2)
    window.render_fps_spin.setSingleStep(1.0)
    window.render_fps_spin.setValue(float(export_cfg.get("render_fps", 30)))
    window.render_fps_spin.setToolTip(
        "FPS оверлея. 0 = использовать FPS исходного видео.\n"
        "Для экономии размера обычно 1-30 FPS."
    )
    window.render_fps_spin.valueChanged.connect(lambda v: window._update_export_config("render_fps", float(v)))
    layout.addRow("FPS оверлея:", window.render_fps_spin)

    return group


def build_performance_group(window) -> QGroupBox:
    """Группа настроек производительности (актуально для 4K/120fps)."""
    group = QGroupBox("Производительность (4K / 120fps)")
    layout = QFormLayout(group)
    layout.setSpacing(6)

    perf = window.config_manager.config.get("performance", {})

    # Аппаратное ускорение
    window.hw_accel_combo = QComboBox()
    window.hw_accel_combo.addItem("Авто (определить автоматически)", "auto")
    window.hw_accel_combo.addItem("Только CPU", "none")
    hw_accel_val = str(perf.get("hw_accel", "auto")).lower()
    idx = window.hw_accel_combo.findData(hw_accel_val)
    window.hw_accel_combo.setCurrentIndex(idx if idx >= 0 else 0)
    window.hw_accel_combo.setToolTip(
        "Аппаратное ускорение кодирования FFmpeg.\n"
        "Авто — использует VideoToolbox (macOS) если доступен.\n"
        "Только CPU — всегда использует программный кодировщик."
    )
    window.hw_accel_combo.currentIndexChanged.connect(
        lambda i: window._update_perf_config("hw_accel", window.hw_accel_combo.itemData(i))
    )
    layout.addRow("Аппаратное ускорение:", window.hw_accel_combo)

    # Потоки рендеринга
    window.render_workers_spin = QSpinBox()
    window.render_workers_spin.setRange(0, 32)
    window.render_workers_spin.setValue(int(perf.get("render_workers", 0)))
    window.render_workers_spin.setToolTip(
        "Количество потоков для параллельного рендеринга кадров.\n"
        "0 — автоматически (по числу ядер CPU).\n"
        "1 — однопоточный режим (для отладки)."
    )
    window.render_workers_spin.valueChanged.connect(
        lambda v: window._update_perf_config("render_workers", v)
    )
    layout.addRow("Потоки рендеринга (0=авто):", window.render_workers_spin)

    # Таймаут ffprobe
    window.ffprobe_timeout_spin = QSpinBox()
    window.ffprobe_timeout_spin.setRange(10, 600)
    window.ffprobe_timeout_spin.setValue(int(perf.get("ffprobe_timeout", 30)))
    window.ffprobe_timeout_spin.setSuffix(" с")
    window.ffprobe_timeout_spin.setToolTip(
        "Максимальное время ожидания при анализе видеофайла (ffprobe).\n"
        "Для файлов 8+ ГБ рекомендуется увеличить до 120–300 с."
    )
    window.ffprobe_timeout_spin.valueChanged.connect(
        lambda v: window._update_perf_config("ffprobe_timeout", v)
    )
    layout.addRow("Таймаут ffprobe:", window.ffprobe_timeout_spin)

    # Таймаут ffmpeg
    window.ffmpeg_timeout_spin = QSpinBox()
    window.ffmpeg_timeout_spin.setRange(10, 600)
    window.ffmpeg_timeout_spin.setValue(int(perf.get("ffmpeg_timeout", 60)))
    window.ffmpeg_timeout_spin.setSuffix(" с")
    window.ffmpeg_timeout_spin.setToolTip(
        "Максимальное время ожидания при извлечении потока данных (ffmpeg).\n"
        "Для длинных видео рекомендуется увеличить до 120–300 с."
    )
    window.ffmpeg_timeout_spin.valueChanged.connect(
        lambda v: window._update_perf_config("ffmpeg_timeout", v)
    )
    layout.addRow("Таймаут ffmpeg:", window.ffmpeg_timeout_spin)

    # Уровень сжатия PNG (для PNG sequence)
    window.png_compress_spin = QSpinBox()
    window.png_compress_spin.setRange(0, 9)
    window.png_compress_spin.setValue(int(perf.get("png_compress_level", 1)))
    window.png_compress_spin.setToolTip(
        "Уровень сжатия PNG при экспорте в PNG sequence.\n"
        "0 — без сжатия (быстрее, больше размер).\n"
        "1 — быстрое сжатие (рекомендуется).\n"
        "9 — максимальное сжатие (медленнее).\n"
        "Не используется при рендере в видео (MOV/WebM)."
    )
    window.png_compress_spin.valueChanged.connect(
        lambda v: window._update_perf_config("png_compress_level", v)
    )
    layout.addRow("Сжатие PNG (0–9):", window.png_compress_spin)

    window.prores_qscale_spin = QSpinBox()
    window.prores_qscale_spin.setRange(1, 31)
    window.prores_qscale_spin.setValue(int(perf.get("prores_qscale", 11)))
    window.prores_qscale_spin.setToolTip("Качество ProRes: меньше значение = выше качество и больше размер.")
    window.prores_qscale_spin.valueChanged.connect(
        lambda v: window._update_perf_config("prores_qscale", v)
    )
    layout.addRow("ProRes qscale (1-31):", window.prores_qscale_spin)

    window.vp9_crf_spin = QSpinBox()
    window.vp9_crf_spin.setRange(0, 63)
    window.vp9_crf_spin.setValue(int(perf.get("vp9_crf", 34)))
    window.vp9_crf_spin.setToolTip("Качество VP9: меньше значение = выше качество и больше размер.")
    window.vp9_crf_spin.valueChanged.connect(
        lambda v: window._update_perf_config("vp9_crf", v)
    )
    layout.addRow("VP9 CRF (0-63):", window.vp9_crf_spin)

    window.vp9_cpu_spin = QSpinBox()
    window.vp9_cpu_spin.setRange(0, 8)
    window.vp9_cpu_spin.setValue(int(perf.get("vp9_cpu_used", 2)))
    window.vp9_cpu_spin.setToolTip("Скорость кодирования VP9: больше значение = быстрее, но хуже сжатие.")
    window.vp9_cpu_spin.valueChanged.connect(
        lambda v: window._update_perf_config("vp9_cpu_used", v)
    )
    layout.addRow("VP9 cpu-used (0-8):", window.vp9_cpu_spin)

    hint = QLabel(
        "⚠ Для видео 4K/120fps рекомендуется: таймауты 120–300 с, потоки рендеринга = 0 (авто)."
    )
    hint.setWordWrap(True)
    hint.setStyleSheet("color: #aaa; font-size: 11px;")
    layout.addRow(hint)

    return group


def build_preview_group(window) -> QGroupBox:
    """Правая панель предпросмотра телеметрии."""
    group = QGroupBox("Предпросмотр телеметрии")
    layout = QVBoxLayout(group)

    # Метаданные
    window.meta_label = QLabel("Нет данных телеметрии")
    window.meta_label.setStyleSheet("color: #aaa; font-size: 12px;")
    layout.addWidget(window.meta_label)

    # Текстовая область с телеметрией
    window.telemetry_text = QTextEdit()
    window.telemetry_text.setReadOnly(True)
    window.telemetry_text.setFont(QFont("Monospace", 10))
    window.telemetry_text.setPlaceholderText(
        "Здесь будет отображаться извлечённая телеметрия в формате JSON...\n\n"
        "Выберите видеофайл и нажмите «Извлечь телеметрию»."
    )
    layout.addWidget(window.telemetry_text)

    return group


def build_batch_tab(window) -> QWidget:
    """Вкладка «Пакетная обработка»: очередь файлов + запуск одной кнопкой."""
    from ui.file_queue_widget import FileQueueWidget

    widget = QWidget()
    main_layout = QVBoxLayout(widget)
    main_layout.setSpacing(10)
    main_layout.setContentsMargins(12, 12, 12, 12)

    # ── Заголовок-подсказка ──────────────────────────────────────────────────
    hint = QLabel(
        "Добавьте несколько видеофайлов DJI и нажмите «Запустить обработку».\n"
        "Для добавления файлов можно также перетащить их мышью в список ниже."
    )
    hint.setStyleSheet("color: #aaa; font-size: 11px;")
    hint.setWordWrap(True)
    main_layout.addWidget(hint)

    # ── Виджет очереди ───────────────────────────────────────────────────────
    window.batch_queue_widget = FileQueueWidget()
    main_layout.addWidget(window.batch_queue_widget, 1)

    # ── Прогресс текущего файла ──────────────────────────────────────────────
    window.batch_progress_bar = QProgressBar()
    window.batch_progress_bar.setVisible(False)
    window.batch_progress_bar.setTextVisible(True)
    main_layout.addWidget(window.batch_progress_bar)

    window.batch_status_label = QLabel("")
    window.batch_status_label.setStyleSheet("color: #aaa; font-size: 11px;")
    window.batch_status_label.setWordWrap(True)
    main_layout.addWidget(window.batch_status_label)

    # ── Кнопки управления ────────────────────────────────────────────────────
    btn_row = QWidget()
    btn_layout = QHBoxLayout(btn_row)
    btn_layout.setContentsMargins(0, 0, 0, 0)
    btn_layout.setSpacing(8)

    window.batch_run_btn = QPushButton("▶  Запустить обработку")
    window.batch_run_btn.setMinimumHeight(42)
    window.batch_run_btn.setStyleSheet(
        "QPushButton { background-color: #1a5a8a; color: white; font-weight: bold; border-radius: 4px; }"
        "QPushButton:hover { background-color: #2070aa; }"
        "QPushButton:disabled { background-color: #555; color: #888; }"
    )
    window.batch_run_btn.clicked.connect(window._batch_run)

    window.batch_stop_btn = QPushButton("■  Остановить")
    window.batch_stop_btn.setMinimumHeight(42)
    window.batch_stop_btn.setEnabled(False)
    window.batch_stop_btn.setStyleSheet(
        "QPushButton { background-color: #7a2d2d; color: white; font-weight: bold; border-radius: 4px; }"
        "QPushButton:hover { background-color: #a03030; }"
        "QPushButton:disabled { background-color: #555; color: #888; }"
    )
    window.batch_stop_btn.clicked.connect(window._batch_stop)

    btn_layout.addWidget(window.batch_run_btn, 1)
    btn_layout.addWidget(window.batch_stop_btn)
    main_layout.addWidget(btn_row)

    return widget
