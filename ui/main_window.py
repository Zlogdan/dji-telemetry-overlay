# -*- coding: utf-8 -*-
"""
Главное окно приложения DJI Telemetry Overlay.
Пользовательский интерфейс на русском языке.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QGroupBox, QFileDialog,
    QAction, QMessageBox, QApplication,
)
from PyQt5.QtCore import Qt, QThread

from config.config_manager import ConfigManager
from ui import main_window_builders as builders
from ui.preview_window import PreviewWindow
from ui.workers import TelemetryWorker, RenderWorker, BatchWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.telemetry_data = None
        self._thread = None
        self._worker = None
        self._batch_thread = None
        self._batch_worker = None

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
        builders.setup_ui(self)

    def _build_main_tab(self) -> QWidget:
        """Вкладка «Основное»: файлы, действия и предпросмотр."""
        return builders.build_main_tab(self)

    def _build_settings_tab(self) -> QWidget:
        """Вкладка «Настройки»: модули, параметры отображения, производительность."""
        return builders.build_settings_tab(self)

    def _build_layout_tab(self) -> QWidget:
        """Вкладка визуального позиционирования модулей."""
        return builders.build_layout_tab(self)

    def _build_files_group(self) -> QGroupBox:
        """Группа выбора файлов."""
        return builders.build_files_group(self)

    def _build_actions_group(self) -> QGroupBox:
        """Группа кнопок действий."""
        return builders.build_actions_group(self)

    def _build_modules_group(self) -> QGroupBox:
        """Группа выбора активных модулей."""
        return builders.build_modules_group(self)

    def _build_params_group(self) -> QGroupBox:
        """Группа настройки параметров."""
        return builders.build_params_group(self)

    def _build_export_group(self) -> QGroupBox:
        """Группа настроек экспорта: режим, формат, FPS."""
        return builders.build_export_group(self)

    def _build_performance_group(self) -> QGroupBox:
        """Группа настроек производительности (актуально для 4K/120fps)."""
        return builders.build_performance_group(self)

    def _build_preview_group(self) -> QGroupBox:
        """Правая панель предпросмотра телеметрии."""
        return builders.build_preview_group(self)

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
        self.hw_accel_combo.blockSignals(True)
        self.render_workers_spin.blockSignals(True)

        self.ffprobe_timeout_spin.setValue(int(perf.get("ffprobe_timeout", 30)))
        self.ffmpeg_timeout_spin.setValue(int(perf.get("ffmpeg_timeout", 60)))
        self.png_compress_spin.setValue(int(perf.get("png_compress_level", 1)))
        self.prores_qscale_spin.setValue(int(perf.get("prores_qscale", 11)))
        self.vp9_crf_spin.setValue(int(perf.get("vp9_crf", 34)))
        self.vp9_cpu_spin.setValue(int(perf.get("vp9_cpu_used", 2)))
        hw_accel_val = str(perf.get("hw_accel", "auto")).lower()
        hw_idx = self.hw_accel_combo.findData(hw_accel_val)
        self.hw_accel_combo.setCurrentIndex(hw_idx if hw_idx >= 0 else 0)
        self.render_workers_spin.setValue(int(perf.get("render_workers", 0)))

        self.ffprobe_timeout_spin.blockSignals(False)
        self.ffmpeg_timeout_spin.blockSignals(False)
        self.png_compress_spin.blockSignals(False)
        self.prores_qscale_spin.blockSignals(False)
        self.vp9_crf_spin.blockSignals(False)
        self.vp9_cpu_spin.blockSignals(False)
        self.hw_accel_combo.blockSignals(False)
        self.render_workers_spin.blockSignals(False)

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

        cached = self._load_cached_telemetry(video_path)
        if cached is not None:
            self.status_label.setText("Телеметрия загружена из файла рядом с видео")
            self._on_telemetry_extracted(cached)
            cache_path = self._get_telemetry_cache_path(video_path)
            self.statusBar().showMessage(f"Загружен кэш телеметрии: {cache_path}")
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

        video_path = self.video_path_edit.text().strip()
        if video_path:
            self._save_cached_telemetry(video_path, telemetry)

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
            # Обновляем превью при загрузке новой телеметрии
            self._refresh_layout_preview()
        else:
            self.render_btn.setEnabled(False)
            self.status_label.setText("Телеметрия не найдена в файле")
            self.statusBar().showMessage("Телеметрия не найдена")
            self.layout_canvas.set_preview_image(None)
            self.layout_status_label.setText("Телеметрия не найдена")

    def _get_telemetry_cache_path(self, video_path: str) -> Path:
        """Возвращает путь до кэша телеметрии рядом с видеофайлом."""
        p = Path(video_path)
        return p.with_suffix(f"{p.suffix}.telemetry.json")

    def _load_cached_telemetry(self, video_path: str) -> Optional[dict]:
        """Загружает кэш телеметрии, если он существует и валиден."""
        cache_path = self._get_telemetry_cache_path(video_path)
        if not cache_path.exists():
            return None

        try:
            with cache_path.open("r", encoding="utf-8") as f:
                telemetry = json.load(f)
            if not isinstance(telemetry, dict):
                return None
            if not isinstance(telemetry.get("points", []), list):
                return None
            return telemetry
        except Exception as e:
            logger.warning("Не удалось загрузить кэш телеметрии %s: %s", cache_path, e)
            return None

    def _save_cached_telemetry(self, video_path: str, telemetry: dict):
        """Сохраняет телеметрию в кэш рядом с видеофайлом."""
        cache_path = self._get_telemetry_cache_path(video_path)
        try:
            with cache_path.open("w", encoding="utf-8") as f:
                json.dump(telemetry, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Не удалось сохранить кэш телеметрии %s: %s", cache_path, e)

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
        elif index == 3:  # Вкладка "Пакетная обработка"
            # Синхронизируем расширение выходных файлов с текущим форматом
            mode = self.export_mode_combo.currentData() if hasattr(self, "export_mode_combo") else "video"
            ext = self.output_format_combo.currentData() if hasattr(self, "output_format_combo") else "mov"
            if hasattr(self, "batch_queue_widget"):
                self.batch_queue_widget.set_output_ext(ext, mode)

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

    def _build_batch_tab(self) -> QWidget:
        """Вкладка «Пакетная обработка»."""
        return builders.build_batch_tab(self)

    # ── Пакетная обработка ───────────────────────────────────────────────────

    def _batch_run(self):
        """Запускает последовательную обработку всех файлов из очереди."""
        queue = self.batch_queue_widget.get_queue()
        if not queue:
            QMessageBox.warning(self, "Очередь пуста",
                                "Добавьте видеофайлы в список перед запуском.")
            return

        jobs = [{"video_path": item.video_path, "output_path": item.output_path}
                for item in queue]

        self.batch_run_btn.setEnabled(False)
        self.batch_stop_btn.setEnabled(True)
        self.batch_queue_widget.set_buttons_enabled(False)
        self.batch_progress_bar.setVisible(True)
        self.batch_progress_bar.setRange(0, 100)
        self.batch_progress_bar.setValue(0)
        total = len(jobs)
        self.batch_status_label.setText(f"Обработка файлов: 0 из {total}…")

        config = self.config_manager.config.copy()

        self._batch_thread = QThread()
        self._batch_worker = BatchWorker(jobs, config)
        self._batch_worker.moveToThread(self._batch_thread)

        self._batch_thread.started.connect(self._batch_worker.run)
        self._batch_worker.file_started.connect(self._on_batch_file_started)
        self._batch_worker.file_progress.connect(self._on_batch_file_progress)
        self._batch_worker.file_finished.connect(self._on_batch_file_finished)
        self._batch_worker.file_error.connect(self._on_batch_file_error)
        self._batch_worker.all_finished.connect(self._on_batch_all_finished)
        self._batch_worker.all_finished.connect(self._batch_thread.quit)

        self._batch_thread.start()

    def _batch_stop(self):
        """Запрашивает досрочное прерывание пакетной обработки."""
        if self._batch_worker is not None:
            self._batch_worker.stop()
        self.batch_stop_btn.setEnabled(False)
        self.batch_status_label.setText("Ожидание завершения текущего файла…")

    def _on_batch_file_started(self, index: int, video_path: str):
        from pathlib import Path as _Path
        fname = _Path(video_path).name
        queue = self.batch_queue_widget.get_queue()
        total = len(queue)
        self.batch_status_label.setText(
            f"Файл {index + 1} из {total}: {fname}"
        )
        self.batch_queue_widget.update_item_status(index, "extracting", progress=0)
        self.batch_progress_bar.setValue(0)

    def _on_batch_file_progress(self, index: int, stage: str,
                                current: int, total: int):
        from ui.file_queue_widget import STATUS_EXTRACTING, STATUS_RENDERING
        if stage == "extracting":
            status = STATUS_EXTRACTING
            pct = 0
            stage_label = ""
        else:  # rendering
            status = STATUS_RENDERING
            pct = int(100 * current / total) if total > 0 else 0
            stage_label = f"кадр {current}/{total}"

        self.batch_queue_widget.update_item_status(
            index, status, progress=pct, stage_label=stage_label
        )
        self.batch_progress_bar.setValue(pct)

    def _on_batch_file_finished(self, index: int, output_path: str):
        from ui.file_queue_widget import STATUS_DONE
        queue = self.batch_queue_widget.get_queue()
        total = len(queue)
        self.batch_queue_widget.update_item_status(index, STATUS_DONE, progress=100)
        self.batch_status_label.setText(
            f"Завершено {index + 1} из {total}: {output_path}"
        )

    def _on_batch_file_error(self, index: int, error_msg: str):
        from ui.file_queue_widget import STATUS_ERROR
        self.batch_queue_widget.update_item_status(
            index, STATUS_ERROR, error=error_msg
        )
        self.statusBar().showMessage(f"Ошибка файла #{index + 1}: {error_msg}")

    def _on_batch_all_finished(self, success_count: int, error_count: int):
        self.batch_run_btn.setEnabled(True)
        self.batch_stop_btn.setEnabled(False)
        self.batch_queue_widget.set_buttons_enabled(True)
        self.batch_progress_bar.setVisible(False)

        total = success_count + error_count
        msg = f"Обработка завершена: {success_count} из {total} файлов."
        if error_count:
            msg += f"\nОшибок: {error_count}."
        self.batch_status_label.setText(msg)
        self.statusBar().showMessage(msg)
        QMessageBox.information(self, "Пакетная обработка завершена", msg)

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
