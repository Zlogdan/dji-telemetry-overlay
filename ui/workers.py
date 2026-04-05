# -*- coding: utf-8 -*-
"""Рабочие классы UI для фоновых операций."""

from PyQt5.QtCore import QObject, pyqtSignal


class TelemetryWorker(QObject):
    """Рабочий поток для извлечения телеметрии."""

    # Сигналы
    finished = pyqtSignal(dict)          # телеметрия успешно извлечена
    error = pyqtSignal(str)              # произошла ошибка
    progress = pyqtSignal(str)           # сообщение о прогрессе

    def __init__(self, video_path: str, perf_config: dict = None, extract_config: dict = None):
        super().__init__()
        self.video_path = video_path
        self.perf_config = perf_config or {}
        self.extract_config = extract_config or {}

    def run(self):
        """Выполняет извлечение телеметрии."""
        try:
            self.progress.emit("Анализ видеофайла...")
            from core.extractor import extract_telemetry
            telemetry = extract_telemetry(
                self.video_path,
                perf_config=self.perf_config,
                extract_config=self.extract_config,
            )
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
            mode = str(self.config.get("export", {}).get("mode", "video"))
            if mode == "png_sequence":
                engine.render_to_png_sequence(
                    self.telemetry,
                    self.output_path,
                    progress_callback=self.progress.emit
                )
            else:
                engine.render_to_video(
                    self.telemetry,
                    self.output_path,
                    progress_callback=self.progress.emit
                )
            self.finished.emit(self.output_path)
        except Exception as e:
            self.error.emit(f"Ошибка рендеринга: {str(e)}")
