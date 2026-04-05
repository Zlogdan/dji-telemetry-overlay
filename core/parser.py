# -*- coding: utf-8 -*-
"""
Модуль разбора данных телеметрии.
Поддерживает NMEA-предложения GPRMC и GPGGA.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import math


@dataclass
class TelemetryPoint:
    """Точка телеметрии с геоданными."""
    t: float = 0.0        # время от начала видео (секунды)
    lat: float = 0.0      # широта (десятичные градусы)
    lon: float = 0.0      # долгота (десятичные градусы)
    speed: float = 0.0    # скорость (м/с)
    alt: float = 0.0      # высота над уровнем моря (м)
    heading: float = 0.0  # курс (градусы 0-360)


def nmea_to_decimal(value: str, direction: str) -> float:
    """
    Конвертирует координату из формата NMEA (DDDMM.MMMM) в десятичные градусы.

    Аргументы:
        value: строка координаты в формате NMEA
        direction: направление ('N', 'S', 'E', 'W')

    Возвращает:
        Координату в десятичных градусах
    """
    if not value or not direction:
        return 0.0
    try:
        value = value.strip()
        # Определяем количество знаков для градусов
        dot_pos = value.index(".")
        # Минуты занимают 2 знака перед точкой
        deg_end = dot_pos - 2
        degrees = float(value[:deg_end])
        minutes = float(value[deg_end:])
        decimal = degrees + minutes / 60.0
        if direction in ("S", "W"):
            decimal = -decimal
        return decimal
    except (ValueError, IndexError):
        return 0.0


def _validate_checksum(sentence: str) -> bool:
    """Проверяет контрольную сумму NMEA-предложения."""
    try:
        if "*" not in sentence:
            return True  # Нет контрольной суммы — пропускаем проверку
        data, checksum = sentence[1:].rsplit("*", 1)
        calculated = 0
        for char in data:
            calculated ^= ord(char)
        return calculated == int(checksum[:2], 16)
    except (ValueError, IndexError):
        return False


def parse_gprmc(parts: list) -> Optional[dict]:
    """
    Разбирает предложение GPRMC (рекомендуемые минимальные данные GPS).

    Формат: $GPRMC,time,status,lat,N/S,lon,E/W,speed,course,date,magvar,E/W*checksum
    """
    try:
        if len(parts) < 10:
            return None
        status = parts[2]
        if status != "A":  # A = активный, V = недействительный
            return None

        lat = nmea_to_decimal(parts[3], parts[4])
        lon = nmea_to_decimal(parts[5], parts[6])

        # Скорость в узлах → м/с
        speed_knots = float(parts[7]) if parts[7] else 0.0
        speed_ms = speed_knots * 0.514444

        # Курс
        heading = float(parts[8]) if parts[8] else 0.0

        return {
            "lat": lat,
            "lon": lon,
            "speed": speed_ms,
            "heading": heading
        }
    except (ValueError, IndexError):
        return None


def parse_gpgga(parts: list) -> Optional[dict]:
    """
    Разбирает предложение GPGGA (глобальное положение).

    Формат: $GPGGA,time,lat,N/S,lon,E/W,quality,numSV,HDOP,alt,M,sep,M,diffAge,diffStation*checksum
    """
    try:
        if len(parts) < 10:
            return None

        quality = int(parts[6]) if parts[6] else 0
        if quality == 0:
            return None  # Нет фиксации

        lat = nmea_to_decimal(parts[2], parts[3])
        lon = nmea_to_decimal(parts[4], parts[5])
        alt = float(parts[9]) if parts[9] else 0.0

        return {
            "lat": lat,
            "lon": lon,
            "alt": alt
        }
    except (ValueError, IndexError):
        return None


def parse_nmea_sentence(sentence: str) -> Optional[TelemetryPoint]:
    """
    Разбирает NMEA-предложение и возвращает точку телеметрии.

    Поддерживаемые типы: GPRMC, GPGGA, GNRMC, GNGGA.
    """
    sentence = sentence.strip()
    if not sentence.startswith("$"):
        return None

    if not _validate_checksum(sentence):
        return None

    # Убираем контрольную сумму
    if "*" in sentence:
        sentence = sentence[:sentence.rfind("*")]

    parts = sentence.split(",")
    if not parts:
        return None

    sentence_type = parts[0][1:]  # Убираем $

    point = TelemetryPoint()

    if sentence_type in ("GPRMC", "GNRMC"):
        data = parse_gprmc(parts)
        if data:
            point.lat = data["lat"]
            point.lon = data["lon"]
            point.speed = data["speed"]
            point.heading = data["heading"]
            return point

    elif sentence_type in ("GPGGA", "GNGGA"):
        data = parse_gpgga(parts)
        if data:
            point.lat = data["lat"]
            point.lon = data["lon"]
            point.alt = data["alt"]
            return point

    return None


def merge_points(points: List[TelemetryPoint]) -> List[TelemetryPoint]:
    """
    Объединяет точки из GPRMC и GPGGA, дополняя данными высоты.
    Сортирует точки по времени.
    """
    if not points:
        return []

    # Удаляем точки с нулевыми координатами
    valid = [p for p in points if p.lat != 0.0 or p.lon != 0.0]

    if not valid:
        return []

    # Сортируем по времени
    valid.sort(key=lambda p: p.t)

    # Объединяем соседние точки с одинаковым временем
    merged = []
    i = 0
    while i < len(valid):
        current = valid[i]
        j = i + 1
        while j < len(valid) and abs(valid[j].t - current.t) < 0.001:
            # Дополняем данными из следующей точки
            if valid[j].alt != 0.0 and current.alt == 0.0:
                current.alt = valid[j].alt
            if valid[j].speed != 0.0 and current.speed == 0.0:
                current.speed = valid[j].speed
            if valid[j].heading != 0.0 and current.heading == 0.0:
                current.heading = valid[j].heading
            j += 1
        merged.append(current)
        i = j

    return merged
