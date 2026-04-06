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


class BatchWorker(QObject):
    """Рабочий поток для последовательной пакетной обработки нескольких файлов."""

    # Сигналы
    file_started = pyqtSignal(int, str)          # index, video_path
    file_progress = pyqtSignal(int, str, int, int)  # index, stage, current, total
    file_finished = pyqtSignal(int, str)         # index, output_path
    file_error = pyqtSignal(int, str)            # index, error_message
    all_finished = pyqtSignal(int, int)          # success_count, error_count

    def __init__(self, queue: list, config: dict):
        """
        Parameters
        ----------
        queue:
            Список словарей с ключами ``video_path``, ``output_path``.
        config:
            Конфигурация приложения (используется для рендеринга).
        """
        super().__init__()
        self._queue = queue
        self._config = config
        self._stop = False

    def stop(self):
        """Запрашивает досрочное прерывание обработки после текущего файла."""
        self._stop = True

    def run(self):
        """Последовательно обрабатывает все файлы из очереди."""
        success_count = 0
        error_count = 0

        for index, job in enumerate(self._queue):
            if self._stop:
                break

            video_path = job["video_path"]
            output_path = job["output_path"]

            self.file_started.emit(index, video_path)

            # ── 1. Извлечение телеметрии ──────────────────────────────────
            try:
                self.file_progress.emit(index, "extracting", 0, 0)
                from core.extractor import extract_telemetry
                telemetry = extract_telemetry(
                    video_path,
                    perf_config=self._config.get("performance", {}),
                    extract_config=self._config.get("extraction", {}),
                )
            except Exception as exc:
                self.file_error.emit(index, f"Ошибка извлечения: {exc}")
                error_count += 1
                continue

            if self._stop:
                break

            # ── 2. Рендеринг оверлея ──────────────────────────────────────
            try:
                from renderer.engine import RenderEngine
                engine = RenderEngine(self._config)
                mode = str(self._config.get("export", {}).get("mode", "video"))

                def _progress(current: int, total: int, _idx=index):
                    self.file_progress.emit(_idx, "rendering", current, total)

                if mode == "png_sequence":
                    engine.render_to_png_sequence(
                        telemetry,
                        output_path,
                        progress_callback=_progress,
                    )
                else:
                    engine.render_to_video(
                        telemetry,
                        output_path,
                        progress_callback=_progress,
                    )
            except Exception as exc:
                self.file_error.emit(index, f"Ошибка рендеринга: {exc}")
                error_count += 1
                continue

            self.file_finished.emit(index, output_path)
            success_count += 1

        self.all_finished.emit(success_count, error_count)
