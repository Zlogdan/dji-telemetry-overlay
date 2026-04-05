# -*- coding: utf-8 -*-
"""
Модуль интерполяции телеметрии.
Приводит точки телеметрии к частоте кадров видео.
"""

import math
from typing import List
from core.parser import TelemetryPoint


def lerp(a: float, b: float, t: float) -> float:
    """Линейная интерполяция между a и b при параметре t ∈ [0, 1]."""
    return a + (b - a) * t


def lerp_angle(a: float, b: float, t: float) -> float:
    """
    Интерполяция угла с учётом перехода через 360 градусов.
    Выбирает кратчайший путь между углами.
    """
    diff = b - a
    # Нормализуем разницу в диапазон [-180, 180]
    while diff > 180:
        diff -= 360
    while diff < -180:
        diff += 360
    result = a + diff * t
    return result % 360


def interpolate_point(p1: TelemetryPoint, p2: TelemetryPoint, t: float) -> TelemetryPoint:
    """
    Интерполирует между двумя точками телеметрии.

    Аргументы:
        p1: начальная точка
        p2: конечная точка
        t: параметр интерполяции [0, 1]
    """
    return TelemetryPoint(
        t=lerp(p1.t, p2.t, t),
        lat=lerp(p1.lat, p2.lat, t),
        lon=lerp(p1.lon, p2.lon, t),
        speed=lerp(p1.speed, p2.speed, t),
        alt=lerp(p1.alt, p2.alt, t),
        heading=lerp_angle(p1.heading, p2.heading, t),
    )


def interpolate_to_fps(
    points: List[TelemetryPoint],
    fps: float,
    duration: float
) -> List[TelemetryPoint]:
    """
    Интерполирует точки телеметрии для каждого кадра видео.

    Аргументы:
        points: исходные точки телеметрии
        fps: частота кадров видео
        duration: длительность видео в секундах

    Возвращает:
        Список точек — по одной на каждый кадр
    """
    if not points:
        # Возвращаем пустые точки
        n_frames = max(1, int(duration * fps))
        return [TelemetryPoint(t=i / fps) for i in range(n_frames)]

    if len(points) == 1:
        # Одна точка — дублируем на все кадры
        n_frames = max(1, int(duration * fps))
        result = []
        for i in range(n_frames):
            p = TelemetryPoint(
                t=i / fps,
                lat=points[0].lat,
                lon=points[0].lon,
                speed=points[0].speed,
                alt=points[0].alt,
                heading=points[0].heading,
            )
            result.append(p)
        return result

    n_frames = max(1, int(duration * fps))
    result = []

    for frame_idx in range(n_frames):
        frame_time = frame_idx / fps

        # Если до первой точки
        if frame_time <= points[0].t:
            p = TelemetryPoint(
                t=frame_time,
                lat=points[0].lat,
                lon=points[0].lon,
                speed=points[0].speed,
                alt=points[0].alt,
                heading=points[0].heading,
            )
            result.append(p)
            continue

        # Если после последней точки
        if frame_time >= points[-1].t:
            p = TelemetryPoint(
                t=frame_time,
                lat=points[-1].lat,
                lon=points[-1].lon,
                speed=points[-1].speed,
                alt=points[-1].alt,
                heading=points[-1].heading,
            )
            result.append(p)
            continue

        # Бинарный поиск нужного интервала
        lo, hi = 0, len(points) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if points[mid].t <= frame_time:
                lo = mid
            else:
                hi = mid

        p1 = points[lo]
        p2 = points[hi]
        dt = p2.t - p1.t

        if dt < 1e-9:
            t_param = 0.0
        else:
            t_param = (frame_time - p1.t) / dt

        t_param = max(0.0, min(1.0, t_param))
        result.append(interpolate_point(p1, p2, t_param))

    return result


def smooth_points(points: List[TelemetryPoint], window: int = 5) -> List[TelemetryPoint]:
    """
    Сглаживает телеметрию методом скользящего среднего.

    Аргументы:
        points: входные точки
        window: размер окна сглаживания

    Возвращает:
        Сглаженный список точек
    """
    if len(points) <= 1:
        return points

    half = window // 2
    smoothed = []

    for i, pt in enumerate(points):
        start = max(0, i - half)
        end = min(len(points), i + half + 1)
        neighbors = points[start:end]
        n = len(neighbors)

        avg_lat = sum(p.lat for p in neighbors) / n
        avg_lon = sum(p.lon for p in neighbors) / n
        avg_speed = sum(p.speed for p in neighbors) / n
        avg_alt = sum(p.alt for p in neighbors) / n

        # Для курса используем векторное усреднение
        sin_sum = sum(math.sin(math.radians(p.heading)) for p in neighbors)
        cos_sum = sum(math.cos(math.radians(p.heading)) for p in neighbors)
        avg_heading = math.degrees(math.atan2(sin_sum / n, cos_sum / n)) % 360

        smoothed.append(TelemetryPoint(
            t=pt.t,
            lat=avg_lat,
            lon=avg_lon,
            speed=avg_speed,
            alt=avg_alt,
            heading=avg_heading,
        ))

    return smoothed
