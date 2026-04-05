# -*- coding: utf-8 -*-
"""
Модуль извлечения телеметрии из видеофайлов DJI.
Использует ffprobe и ffmpeg для получения данных GPS.
"""

import subprocess
import json
import logging
import os
import math
import random
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_ffprobe(video_path: str, timeout: int = 30) -> Optional[dict]:
    """Запускает ffprobe для получения информации о потоках видео."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except FileNotFoundError:
        logger.error("ffprobe не найден. Убедитесь, что FFmpeg установлен и доступен в PATH.")
        return None
    except subprocess.TimeoutExpired:
        logger.error("ffprobe завис при анализе видео.")
        return None
    except json.JSONDecodeError:
        logger.error("Не удалось разобрать вывод ffprobe.")
        return None


def _extract_data_stream(video_path: str, timeout: int = 60) -> bytes:
    """Извлекает поток данных (телеметрию) из видеофайла."""
    try:
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-map", "0:d:0",
            "-c", "copy",
            "-f", "data",
            "pipe:1"
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout
        return b""
    except FileNotFoundError:
        logger.error("ffmpeg не найден.")
        return b""
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg завис при извлечении данных.")
        return b""


def _parse_nmea_from_bytes(data: bytes) -> list:
    """Разбирает NMEA-предложения из байтовых данных."""
    from core.parser import parse_nmea_sentence
    points = []
    try:
        text = data.decode("ascii", errors="ignore")
    except Exception:
        return points

    lines = text.replace("\r", "\n").split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("$GP") or line.startswith("$GN"):
            point = parse_nmea_sentence(line)
            if point:
                points.append(point)
    return points


def _get_video_info(probe_data: dict) -> tuple:
    """Извлекает FPS и длительность из данных ffprobe."""
    fps = 30.0
    duration = 0.0

    # Получаем длительность из формата
    fmt = probe_data.get("format", {})
    try:
        duration = float(fmt.get("duration", 0))
    except (ValueError, TypeError):
        pass

    # Ищем видеопоток для FPS
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            # Пробуем r_frame_rate
            r_frame_rate = stream.get("r_frame_rate", "30/1")
            try:
                num, den = r_frame_rate.split("/")
                fps = float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass
            # Длительность потока, если не было в формате
            if duration == 0:
                try:
                    duration = float(stream.get("duration", 0))
                except (ValueError, TypeError):
                    pass
            break

    return fps, duration


def generate_demo_telemetry(duration: float = 60.0, fps: float = 30.0) -> dict:
    """
    Генерирует демонстрационную телеметрию для тестирования без реального видео.
    Создаёт круговой маршрут вокруг центральной точки.
    """
    # Центральная точка демо-маршрута (Москва, Россия)
    center_lat = 55.7558
    center_lon = 37.6173
    radius_deg = 0.005  # примерно 500 метров

    points = []
    num_points = int(duration)  # одна точка в секунду

    for i in range(num_points):
        t = float(i)
        angle = (2 * math.pi * i / num_points)

        lat = center_lat + radius_deg * math.sin(angle)
        lon = center_lon + radius_deg * math.cos(angle)

        # Скорость: синусоидальная от 10 до 40 км/ч → м/с
        speed_kmh = 25 + 15 * math.sin(angle * 2)
        speed_ms = speed_kmh / 3.6

        # Высота: небольшие изменения
        alt = 100.0 + 10 * math.sin(angle * 3)

        # Курс: по кругу
        heading = (math.degrees(angle) + 90) % 360

        points.append({
            "t": t,
            "lat": lat,
            "lon": lon,
            "speed": speed_ms,
            "alt": alt,
            "heading": heading
        })

    return {
        "fps": fps,
        "duration": duration,
        "points": points,
        "source": "demo"
    }


def extract_telemetry(video_path: str, perf_config: dict = None) -> dict:
    """
    Извлекает телеметрию из видеофайла DJI.

    Аргументы:
        video_path: путь к видеофайлу MP4/MOV
        perf_config: словарь с настройками производительности
                     (ffprobe_timeout, ffmpeg_timeout)

    Возвращает:
        Словарь с ключами fps, duration, points
    """
    perf = perf_config or {}
    ffprobe_timeout = int(perf.get("ffprobe_timeout", 30))
    ffmpeg_timeout = int(perf.get("ffmpeg_timeout", 60))

    video_path = str(video_path)

    if not os.path.exists(video_path):
        logger.error("Файл не найден: %s", video_path)
        return generate_demo_telemetry()

    # Получаем информацию о видео
    probe_data = _run_ffprobe(video_path, timeout=ffprobe_timeout)
    if probe_data is None:
        logger.warning("Не удалось получить информацию о видео. Используется демонстрационная телеметрия.")
        return generate_demo_telemetry()

    fps, duration = _get_video_info(probe_data)

    if duration <= 0:
        logger.warning("Длительность видео не определена. Используется 60 секунд.")
        duration = 60.0

    logger.info("Видео: FPS=%s, длительность=%.1fс", fps, duration)

    # Пробуем извлечь поток данных
    raw_data = _extract_data_stream(video_path, timeout=ffmpeg_timeout)
    points = []

    if raw_data:
        points = _parse_nmea_from_bytes(raw_data)
        logger.info("Найдено NMEA-точек: %d", len(points))

    # Если NMEA не найдено, пробуем метаданные MP4
    if not points:
        points = _try_extract_mp4_metadata(video_path, probe_data, timeout=ffmpeg_timeout)

    # Если всё равно пусто — используем демо
    if not points:
        logger.warning("Телеметрия не найдена в видео. Используется демонстрационная телеметрия.")
        return generate_demo_telemetry(duration, fps)

    # Назначаем временные метки
    if len(points) > 1:
        for i, p in enumerate(points):
            if p.t == 0.0 and i > 0:
                p.t = duration * i / (len(points) - 1)

    # Преобразуем в словари
    points_dicts = [
        {
            "t": p.t,
            "lat": p.lat,
            "lon": p.lon,
            "speed": p.speed,
            "alt": p.alt,
            "heading": p.heading
        }
        for p in points
    ]

    return {
        "fps": fps,
        "duration": duration,
        "points": points_dicts,
        "source": "video"
    }


def _try_extract_mp4_metadata(video_path: str, probe_data: dict, timeout: int = 30) -> list:
    """
    Пробует извлечь GPS из метаданных MP4/MOV.
    Для DJI видео данные могут быть в потоке с codec_tag 'gpmd' или 'tmcd'.
    """
    from core.parser import TelemetryPoint

    points = []
    streams = probe_data.get("streams", [])

    # Ищем потоки с тегами GPS
    for i, stream in enumerate(streams):
        codec_tag = stream.get("codec_tag_string", "")
        codec_type = stream.get("codec_type", "")

        if codec_tag in ("gpmd", "tmcd", "meta") or codec_type == "data":
            try:
                cmd = [
                    "ffmpeg",
                    "-i", video_path,
                    "-map", f"0:{i}",
                    "-c", "copy",
                    "-f", "data",
                    "pipe:1"
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=timeout)
                if result.returncode == 0 and result.stdout:
                    # Пробуем разобрать как NMEA
                    extracted = _parse_nmea_from_bytes(result.stdout)
                    if extracted:
                        points.extend(extracted)
                        break
            except Exception:
                logger.debug("Не удалось извлечь данные из потока %d", i, exc_info=True)
                continue

    return points
