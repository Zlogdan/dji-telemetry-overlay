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
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _empty_telemetry(fps: float = 30.0, duration: float = 0.0, source: str = "video") -> dict:
    """Возвращает пустой контейнер телеметрии без тестовых данных."""
    return {
        "fps": float(fps),
        "duration": float(duration),
        "points": [],
        "source": source,
    }


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
        # ffprobe возвращает UTF-8 JSON; на Windows системная cp1252 может ломать декодирование.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            if result.stderr:
                logger.debug("ffprobe stderr: %s", result.stderr.strip())
            return None
        if not result.stdout:
            logger.error("ffprobe вернул пустой вывод.")
            return None

        return json.loads(result.stdout)
    except FileNotFoundError:
        logger.error("ffprobe не найден. Убедитесь, что FFmpeg установлен и доступен в PATH.")
        return None
    except subprocess.TimeoutExpired:
        logger.error("ffprobe завис при анализе видео.")
        return None
    except (json.JSONDecodeError, TypeError):
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


def _run_pyosmogps_extract(
    video_path: str,
    gpx_path: str,
    frequency: int,
    method: str,
    timezone: int,
    timeout: int,
) -> bool:
    """Запускает pyosmogps extract и сохраняет GPX во временный файл."""
    try:
        cmd = [
            "pyosmogps",
            "extract",
            video_path,
            gpx_path,
            "--frequency", str(frequency),
            "--resampling-method", str(method),
            "--timezone-offset", str(timezone),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            if result.stderr:
                logger.debug("pyosmogps stderr: %s", result.stderr.strip())
            return False
        return os.path.exists(gpx_path) and os.path.getsize(gpx_path) > 0
    except FileNotFoundError:
        logger.info("pyosmogps не найден в PATH, переключаемся на ffmpeg fallback.")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("pyosmogps превысил таймаут (%ss), переключаемся на fallback.", timeout)
        return False


def _strip_ns(tag: str) -> str:
    """Возвращает имя XML-тега без namespace."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _parse_iso_time(value: str) -> Optional[datetime]:
    """Парсит ISO8601-время из GPX."""
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет расстояние между двумя GPS-точками в метрах."""
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычисляет истинный курс от первой точки ко второй в градусах."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0


def _parse_gpx_points(gpx_path: str, duration: float = 0.0) -> list:
    """Разбирает GPX, возвращает список TelemetryPoint."""
    from core.parser import TelemetryPoint

    points = []
    try:
        tree = ET.parse(gpx_path)
        root = tree.getroot()
    except (ET.ParseError, OSError):
        logger.warning("Не удалось разобрать GPX: %s", gpx_path)
        return points

    for trkpt in root.iter():
        if _strip_ns(trkpt.tag) != "trkpt":
            continue

        try:
            lat = float(trkpt.attrib.get("lat", 0.0))
            lon = float(trkpt.attrib.get("lon", 0.0))
        except (TypeError, ValueError):
            continue

        if lat == 0.0 and lon == 0.0:
            continue

        alt = 0.0
        tm = None
        speed = None
        heading = None

        for child in trkpt.iter():
            name = _strip_ns(child.tag).lower()
            text = (child.text or "").strip()
            if not text:
                continue
            if name == "ele":
                try:
                    alt = float(text)
                except ValueError:
                    pass
            elif name == "time":
                tm = _parse_iso_time(text)
            elif name in ("speed", "velocity"):
                try:
                    speed = float(text)
                except ValueError:
                    pass
            elif name in ("course", "heading", "bearing"):
                try:
                    heading = float(text) % 360.0
                except ValueError:
                    pass

        point = TelemetryPoint(
            t=0.0,
            lat=lat,
            lon=lon,
            speed=float(speed) if speed is not None else 0.0,
            alt=alt,
            heading=float(heading) if heading is not None else 0.0,
        )
        points.append((point, tm, speed is not None, heading is not None))

    if not points:
        return []

    # Привязываем время относительно первой точки, если временные метки есть.
    first_ts = next((ts for _, ts, _, _ in points if ts is not None), None)
    if first_ts is not None:
        for idx, (point, ts, _, _) in enumerate(points):
            if ts is None:
                point.t = float(idx)
            else:
                point.t = max(0.0, (ts - first_ts).total_seconds())
    elif len(points) > 1 and duration > 0:
        for idx, (point, _, _, _) in enumerate(points):
            point.t = duration * idx / (len(points) - 1)
    else:
        for idx, (point, _, _, _) in enumerate(points):
            point.t = float(idx)

    # Заполняем скорость/курс по геометрии, если их нет в GPX.
    for i in range(1, len(points)):
        curr, _, has_speed, has_heading = points[i]
        prev, _, _, _ = points[i - 1]
        dt = max(1e-6, curr.t - prev.t)
        dist = _haversine_meters(prev.lat, prev.lon, curr.lat, curr.lon)
        if not has_speed and curr.speed <= 0.0:
            curr.speed = dist / dt
        if not has_heading:
            curr.heading = _bearing_deg(prev.lat, prev.lon, curr.lat, curr.lon)

    return [p[0] for p in points]


def _try_extract_with_pyosmogps(video_path: str, duration: float, perf: dict, extract_cfg: dict) -> list:
    """Пробует извлечь телеметрию через pyosmogps и вернуть точки."""
    frequency = int(extract_cfg.get("pyosmogps_frequency", extract_cfg.get("frequency", 1)))
    method = str(extract_cfg.get("pyosmogps_resampling_method", extract_cfg.get("method", "lpf")))
    timezone = int(extract_cfg.get("pyosmogps_timezone_offset", extract_cfg.get("timezone", 3)))
    timeout = int(
        perf.get(
            "pyosmogps_timeout",
            max(int(perf.get("ffmpeg_timeout", 60)), 60)
        )
    )

    with tempfile.NamedTemporaryFile(suffix=".gpx", delete=False) as temp_file:
        gpx_path = temp_file.name

    try:
        ok = _run_pyosmogps_extract(
            video_path=video_path,
            gpx_path=gpx_path,
            frequency=frequency,
            method=method,
            timezone=timezone,
            timeout=timeout,
        )
        if not ok:
            return []

        points = _parse_gpx_points(gpx_path, duration=duration)
        if points:
            logger.info(
                "Телеметрия извлечена через pyosmogps: %d точек (freq=%sHz, method=%s, tz=%s)",
                len(points),
                frequency,
                method,
                timezone,
            )
        return points
    finally:
        try:
            if os.path.exists(gpx_path):
                os.remove(gpx_path)
        except OSError:
            pass


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


def extract_telemetry(video_path: str, perf_config: dict = None, extract_config: dict = None) -> dict:
    """
    Извлекает телеметрию из видеофайла DJI.

    Аргументы:
        video_path: путь к видеофайлу MP4/MOV
        perf_config: словарь с настройками производительности
                     (ffprobe_timeout, ffmpeg_timeout)
        extract_config: словарь с настройками извлечения
                (pyosmogps_frequency, pyosmogps_resampling_method,
                 pyosmogps_timezone_offset)

    Возвращает:
        Словарь с ключами fps, duration, points
    """
    perf = perf_config or {}
    extract_cfg = extract_config or {}
    ffprobe_timeout = int(perf.get("ffprobe_timeout", 30))
    ffmpeg_timeout = int(perf.get("ffmpeg_timeout", 60))

    video_path = str(video_path)

    if not os.path.exists(video_path):
        logger.error("Файл не найден: %s", video_path)
        return _empty_telemetry(source="missing")

    # Получаем информацию о видео
    probe_data = _run_ffprobe(video_path, timeout=ffprobe_timeout)
    if probe_data is None:
        logger.warning("Не удалось получить информацию о видео. Телеметрия отсутствует.")
        return _empty_telemetry(source="unavailable")

    fps, duration = _get_video_info(probe_data)

    if duration <= 0:
        logger.warning("Длительность видео не определена.")

    logger.info("Видео: FPS=%s, длительность=%.1fс", fps, duration)

    points = _try_extract_with_pyosmogps(
        video_path,
        duration=duration,
        perf=perf,
        extract_cfg=extract_cfg,
    )

    # Fallback: старый путь через ffmpeg-потоки/NMEA
    raw_data = b""
    if not points:
        raw_data = _extract_data_stream(video_path, timeout=ffmpeg_timeout)

    if raw_data:
        points = _parse_nmea_from_bytes(raw_data)
        logger.info("Найдено NMEA-точек: %d", len(points))

    # Если NMEA не найдено, пробуем метаданные MP4
    if not points:
        points = _try_extract_mp4_metadata(video_path, probe_data, timeout=ffmpeg_timeout)

    # Если всё равно пусто — возвращаем пустой результат без подмены
    if not points:
        logger.warning("Телеметрия не найдена в видео.")
        return _empty_telemetry(fps=fps, duration=duration, source="video")

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
