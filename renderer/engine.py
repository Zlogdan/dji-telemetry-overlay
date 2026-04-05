# -*- coding: utf-8 -*-
"""
Движок рендеринга оверлея телеметрии.
Создаёт прозрачный видеоверлей с телеметрическими данными.
"""

import subprocess
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Callable

from PIL import Image

from core.parser import TelemetryPoint
from core.interpolator import interpolate_to_fps, smooth_points
from modules import create_module

logger = logging.getLogger(__name__)

# Псевдоним для удобства использования в методах класса
TP = TelemetryPoint


def detect_hw_encoders() -> list:
    """Обнаруживает доступные аппаратные видеокодировщики FFmpeg.

    Возвращает:
        Список доступных HW-кодировщиков из числа известных.
    """
    known_hw = [
        "prores_videotoolbox",
        "h264_videotoolbox", "hevc_videotoolbox",
        "h264_nvenc", "hevc_nvenc",
        "h264_qsv", "hevc_qsv",
        "h264_amf", "hevc_amf",
    ]
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
        return [enc for enc in known_hw if enc in output]
    except Exception as exc:
        logger.debug("Не удалось определить аппаратные кодировщики: %s", exc)
        return []


class RenderEngine:
    """Основной движок рендеринга оверлея."""

    def __init__(self, config: dict):
        self.config = config
        self.width = config.get("width", 1920)
        self.height = config.get("height", 1080)
        self.modules = []
        self._load_modules()

    def _load_modules(self, skip_types: set = None):
        """Загружает и инициализирует модули из конфигурации.
        
        Аргументы:
            skip_types: набор типов модулей для пропуска (например, {'map'})
        """
        if skip_types is None:
            skip_types = set()
        
        module_configs = self.config.get("modules", [])
        for mod_config in module_configs:
            module_type = mod_config.get("type")
            if module_type in skip_types:
                logger.debug("Пропуск модуля типа '%s' для превью", module_type)
                continue
            if not mod_config.get("enabled", True):
                continue
            module = create_module(mod_config)
            if module is not None:
                self.modules.append(module)
        logger.info("Загружено модулей: %d", len(self.modules))

    def render_frame(
        self,
        frame_index: int,
        point: TelemetryPoint,
        all_points: List[TelemetryPoint]
    ) -> Image.Image:
        """
        Рендерит один кадр наложения.

        Аргументы:
            frame_index: индекс кадра
            point: точка телеметрии для данного кадра
            all_points: все точки маршрута

        Возвращает:
            PIL.Image RGBA-изображение кадра
        """
        canvas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        for module in self.modules:
            if not module.enabled:
                continue
            try:
                overlay = module.render(point, all_points)
                x, y = module.get_position()
                canvas.paste(overlay, (x, y), overlay)
            except Exception as e:
                logger.error("Ошибка рендеринга модуля %s: %s", type(module).__name__, e, exc_info=True)

        return canvas

    def render_to_video(
        self,
        telemetry: dict,
        output_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        """
        Рендерит все кадры и кодирует в видеофайл через FFmpeg.

        Аргументы:
            telemetry: словарь с телеметрией (fps, duration, points)
            output_path: путь выходного файла
            progress_callback: функция обратного вызова (текущий_кадр, всего_кадров)
        """
        logger.info("Начат рендеринг видео: %s", output_path)
        export_cfg = self.config.get("export", {})
        forced_fps = float(export_cfg.get("render_fps", 0) or 0)
        source_fps = float(telemetry.get("fps", 30.0))
        fps = forced_fps if forced_fps > 0 else source_fps
        duration = float(telemetry.get("duration", 60.0))
        raw_points_data = telemetry.get("points", [])

        # Преобразуем словари в TelemetryPoint
        raw_points = []
        for p in raw_points_data:
            if isinstance(p, dict):
                raw_points.append(TP(
                    t=p.get("t", 0.0),
                    lat=p.get("lat", 0.0),
                    lon=p.get("lon", 0.0),
                    speed=p.get("speed", 0.0),
                    alt=p.get("alt", 0.0),
                    heading=p.get("heading", 0.0),
                ))
            else:
                raw_points.append(p)

        # Интерполяция до FPS
        logger.info("Интерполяция %d точек до %s кадров/с...", len(raw_points), fps)
        frame_points = interpolate_to_fps(raw_points, fps, duration)
        frame_points = smooth_points(frame_points, window=5)

        total_frames = len(frame_points)
        logger.info("Всего кадров для рендеринга: %d", total_frames)

        # Создаём директорию для выходного файла
        output_path = str(output_path)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        perf_cfg = self.config.get("performance", {})
        prores_qscale = max(1, min(31, int(perf_cfg.get("prores_qscale", 11))))
        vp9_crf = max(0, min(63, int(perf_cfg.get("vp9_crf", 34))))
        vp9_cpu_used = max(0, min(8, int(perf_cfg.get("vp9_cpu_used", 2))))

        # Количество потоков рендеринга (0 = автоматически по числу ядер)
        configured_workers = int(perf_cfg.get("render_workers", 0))
        num_workers = configured_workers if configured_workers > 0 else max(1, os.cpu_count() or 4)
        logger.info("Потоков рендеринга: %d", num_workers)

        # Аппаратное ускорение
        hw_accel = str(perf_cfg.get("hw_accel", "auto")).lower()

        # Определяем формат кодека по настройке или расширению
        configured_format = str(export_cfg.get("output_format", "")).strip().lower()
        ext = Path(output_path).suffix.lower()
        target_format = configured_format if configured_format in ("mov", "webm") else ext.lstrip(".")
        if target_format not in ("mov", "webm"):
            target_format = "mov"
        output_path = str(Path(output_path).with_suffix(f".{target_format}"))

        # Общие аргументы входного потока (rawvideo — без накладных расходов PNG)
        input_args = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{self.width}x{self.height}",
            "-r", str(fps),
            "-i", "pipe:0",
        ]

        if target_format == "mov":
            # Выбираем кодировщик с учётом аппаратного ускорения
            encoder = "prores_ks"
            if hw_accel == "auto":
                available = detect_hw_encoders()
                if "prores_videotoolbox" in available:
                    encoder = "prores_videotoolbox"
                    logger.info("Используется аппаратный кодировщик: %s", encoder)

            if encoder == "prores_videotoolbox":
                ffmpeg_cmd = input_args + [
                    "-vcodec", "prores_videotoolbox",
                    "-profile:v", "4444",
                    "-pix_fmt", "yuva444p10le",
                    output_path,
                ]
            else:
                ffmpeg_cmd = input_args + [
                    "-vcodec", "prores_ks",
                    "-profile:v", "4444",
                    "-qscale:v", str(prores_qscale),
                    "-pix_fmt", "yuva444p10le",
                    output_path,
                ]
        else:
            # VP9 WebM: аппаратных кодировщиков с поддержкой alpha нет —
            # используем CPU, но добавляем многопоточность FFmpeg
            ffmpeg_threads = min(num_workers, 8)
            ffmpeg_cmd = input_args + [
                "-vcodec", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-b:v", "0",
                "-crf", str(vp9_crf),
                "-deadline", "good",
                "-cpu-used", str(vp9_cpu_used),
                "-row-mt", "1",
                "-tile-columns", "2",
                "-threads", str(ffmpeg_threads),
                "-auto-alt-ref", "0",
                output_path,
            ]

        logger.debug("Запуск FFmpeg: %s", " ".join(ffmpeg_cmd))

        try:
            proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg не найден. Установите FFmpeg и добавьте в PATH."
            )

        # Рендерим и передаём кадры в FFmpeg.
        # Кадры рендерятся параллельно блоками (chunk), затем стримятся в порядке.
        # Размер блока ограничивает пиковое потребление памяти.
        chunk_size = max(1, num_workers * 4)
        try:
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                for chunk_start in range(0, total_frames, chunk_size):
                    chunk_end = min(chunk_start + chunk_size, total_frames)
                    # executor.map гарантирует порядок, соответствующий входным индексам
                    frame_bytes_iter = executor.map(
                        lambda idx: self.render_frame(idx, frame_points[idx], frame_points).tobytes(),
                        range(chunk_start, chunk_end),
                    )
                    for local_j, frame_bytes in enumerate(frame_bytes_iter):
                        global_i = chunk_start + local_j
                        proc.stdin.write(frame_bytes)
                        if progress_callback and (global_i % 10 == 0 or global_i == total_frames - 1):
                            progress_callback(global_i + 1, total_frames)

            proc.stdin.close()
        except BrokenPipeError:
            stderr = proc.stderr.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"FFmpeg завершился с ошибкой:\n{stderr}")
        except Exception:
            # Гарантируем завершение процесса при любой ошибке рендеринга
            proc.terminate()
            proc.wait()
            raise

        # Ждём завершения FFmpeg
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"FFmpeg вернул код {proc.returncode}:\n{error_msg}")

        logger.info("Рендеринг завершён: %s", output_path)

    def render_to_png_sequence(
        self,
        telemetry: dict,
        output_dir: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        """Рендерит оверлей в последовательность PNG-кадров."""
        logger.info("Начат рендеринг PNG последовательности: %s", output_dir)
        export_cfg = self.config.get("export", {})
        forced_fps = float(export_cfg.get("render_fps", 0) or 0)
        source_fps = float(telemetry.get("fps", 30.0))
        fps = forced_fps if forced_fps > 0 else source_fps
        duration = float(telemetry.get("duration", 60.0))
        raw_points_data = telemetry.get("points", [])

        raw_points = []
        for p in raw_points_data:
            if isinstance(p, dict):
                raw_points.append(TP(
                    t=p.get("t", 0.0),
                    lat=p.get("lat", 0.0),
                    lon=p.get("lon", 0.0),
                    speed=p.get("speed", 0.0),
                    alt=p.get("alt", 0.0),
                    heading=p.get("heading", 0.0),
                ))
            else:
                raw_points.append(p)

        logger.info("Интерполяция %d точек до %s кадров/с для PNG sequence...", len(raw_points), fps)
        frame_points = interpolate_to_fps(raw_points, fps, duration)
        frame_points = smooth_points(frame_points, window=5)

        output_root = Path(output_dir)
        output_root.mkdir(parents=True, exist_ok=True)

        total_frames = len(frame_points)
        perf_cfg = self.config.get("performance", {})
        png_compress_level = int(perf_cfg.get("png_compress_level", 1))
        configured_workers = int(perf_cfg.get("render_workers", 0))
        num_workers = configured_workers if configured_workers > 0 else max(1, os.cpu_count() or 4)

        def _render_and_save(i: int):
            frame = self.render_frame(i, frame_points[i], frame_points)
            frame_path = output_root / f"overlay_{i + 1:06d}.png"
            frame.save(frame_path, format="PNG", compress_level=png_compress_level)
            return i

        chunk_size = max(1, num_workers * 4)
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            for chunk_start in range(0, total_frames, chunk_size):
                chunk_end = min(chunk_start + chunk_size, total_frames)
                for i in executor.map(_render_and_save, range(chunk_start, chunk_end)):
                    if progress_callback and (i % 10 == 0 or i == total_frames - 1):
                        progress_callback(i + 1, total_frames)

        logger.info("PNG sequence сохранена: %s (%d кадров)", output_root, total_frames)

    def get_preview_frame(self, telemetry: dict, frame_index: int = 0, skip_map: bool = True) -> Image.Image:
        """
        Возвращает кадр предпросмотра для заданного индекса.

        Аргументы:
            telemetry: данные телеметрии
            frame_index: индекс кадра для предпросмотра
            skip_map: пропустить модуль карты для более быстрого рендеринга (по умолчанию True)
        """
        points_data = telemetry.get("points", [])

        if not points_data:
            return Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        # Если нужно пропустить карту, создаём временное окружение
        if skip_map and any(m.get("type") == "map" for m in self.config.get("modules", [])):
            logger.debug("Рендеринг превью без карты для быстрого отображения")
            # Сохраняем оригинальные модули
            original_modules = self.modules
            # Создаём новый список модулей без карты
            self.modules = []
            for module in original_modules:
                if type(module).__name__ != "MapModule":
                    self.modules.append(module)
            
            try:
                result = self._render_preview_frame(telemetry, frame_index)
            finally:
                # Восстанавливаем оригинальные модули
                self.modules = original_modules
            
            return result
        else:
            return self._render_preview_frame(telemetry, frame_index)

    def _render_preview_frame(self, telemetry: dict, frame_index: int = 0) -> Image.Image:
        """Вспомогательный метод для рендеринга превью кадра."""
        points_data = telemetry.get("points", [])

        raw_points = []
        for p in points_data:
            if isinstance(p, dict):
                raw_points.append(TP(
                    t=p.get("t", 0.0),
                    lat=p.get("lat", 0.0),
                    lon=p.get("lon", 0.0),
                    speed=p.get("speed", 0.0),
                    alt=p.get("alt", 0.0),
                    heading=p.get("heading", 0.0),
                ))
            else:
                raw_points.append(p)

        if not raw_points:
            return Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        # Для превью индекс кадра идёт по исходным точкам телеметрии (ползунок UI),
        # поэтому не интерполируем до FPS здесь, иначе индекс и визуал расходятся.
        idx = max(0, min(frame_index, len(raw_points) - 1))
        return self.render_frame(idx, raw_points[idx], raw_points)
