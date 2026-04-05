# -*- coding: utf-8 -*-
"""
Движок рендеринга оверлея телеметрии.
Создаёт прозрачный видеоверлей с телеметрическими данными.
"""

import subprocess
import io
import logging
import os
from pathlib import Path
from typing import List, Optional, Callable

from PIL import Image

from core.parser import TelemetryPoint
from core.interpolator import interpolate_to_fps, smooth_points
from modules import create_module

logger = logging.getLogger(__name__)

# Псевдоним для удобства использования в методах класса
TP = TelemetryPoint


class RenderEngine:
    """Основной движок рендеринга оверлея."""

    def __init__(self, config: dict):
        self.config = config
        self.width = config.get("width", 1920)
        self.height = config.get("height", 1080)
        self.modules = []
        self._load_modules()

    def _load_modules(self):
        """Загружает и инициализирует модули из конфигурации."""
        module_configs = self.config.get("modules", [])
        for mod_config in module_configs:
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
        fps = float(telemetry.get("fps", 30.0))
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

        # Определяем формат кодека по расширению
        ext = Path(output_path).suffix.lower()
        if ext == ".mov":
            # ProRes 4444 с альфа-каналом
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "image2pipe",
                "-vcodec", "png",
                "-r", str(fps),
                "-i", "pipe:0",
                "-vcodec", "prores_ks",
                "-profile:v", "4444",
                "-pix_fmt", "yuva444p10le",
                output_path
            ]
        else:
            # VP9 с альфа-каналом в WebM
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "image2pipe",
                "-vcodec", "png",
                "-r", str(fps),
                "-i", "pipe:0",
                "-vcodec", "libvpx-vp9",
                "-pix_fmt", "yuva420p",
                "-b:v", "0",
                "-crf", "30",
                output_path
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

        # Рендерим и передаём кадры
        try:
            for i, point in enumerate(frame_points):
                frame = self.render_frame(i, point, frame_points)
                # Конвертируем в PNG и пишем в stdin FFmpeg
                buf = io.BytesIO()
                frame.save(buf, format="PNG")
                proc.stdin.write(buf.getvalue())

                if progress_callback and (i % 10 == 0 or i == total_frames - 1):
                    progress_callback(i + 1, total_frames)

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

    def get_preview_frame(self, telemetry: dict, frame_index: int = 0) -> Image.Image:
        """
        Возвращает кадр предпросмотра для заданного индекса.

        Аргументы:
            telemetry: данные телеметрии
            frame_index: индекс кадра для предпросмотра
        """
        points_data = telemetry.get("points", [])

        if not points_data:
            return Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

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

        fps = float(telemetry.get("fps", 30.0))
        duration = float(telemetry.get("duration", 60.0))
        frame_points = interpolate_to_fps(raw_points, fps, duration)

        idx = min(frame_index, len(frame_points) - 1)
        return self.render_frame(idx, frame_points[idx], frame_points)
