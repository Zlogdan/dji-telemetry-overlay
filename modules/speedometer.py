# -*- coding: utf-8 -*-
"""
Модуль спидометра. Отображает скорость в виде круглого индикатора.
"""

import math
import threading
from typing import Optional
from PIL import Image, ImageDraw
from modules.base import OverlayModule
from modules.utils import load_font
from core.parser import TelemetryPoint


class SpeedometerModule(OverlayModule):
    """Круговой спидометр с дугой и цифровым отображением скорости."""

    # Параметры дуги: от 210° до 330° (300° диапазон)
    _START_ANGLE = 210
    _ARC_RANGE = 300

    def __init__(self, config: dict):
        super().__init__(config)
        self.max_speed = config.get("max_speed", 150)  # максимум в км/ч
        self.unit = config.get("unit", "kmh")  # kmh или ms
        self.unit_label = "км/ч" if self.unit == "kmh" else "м/с"
        # Кэш статического фона (не зависит от скорости)
        self._bg_cache: Optional[Image.Image] = None
        self._bg_cache_key: Optional[tuple] = None
        self._bg_lock = threading.Lock()

    def _get_static_background(self, cx: int, cy: int, r: int, max_val: float) -> Image.Image:
        """Возвращает кэшированный статический фон (круг, шкала, метки)."""
        cache_key = (cx, cy, r, max_val, self.unit_label)
        with self._bg_lock:
            if self._bg_cache_key != cache_key:
                self._bg_cache = self._render_static_background(cx, cy, r, max_val)
                self._bg_cache_key = cache_key
            return self._bg_cache.copy()

    def _render_static_background(self, cx: int, cy: int, r: int, max_val: float) -> Image.Image:
        """Рисует статические элементы: фоновый круг, шкалу, метки единиц."""
        img = self.create_canvas()
        draw = ImageDraw.Draw(img)

        # Тёмный фон круга
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(20, 20, 20, 200)
        )

        start_angle = self._START_ANGLE
        arc_range = self._ARC_RANGE

        # Внешняя граница
        draw.arc(
            [cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5],
            start=start_angle,
            end=start_angle + arc_range,
            fill=(60, 60, 60, 255),
            width=8
        )

        # Деления шкалы
        num_ticks = 10
        for i in range(num_ticks + 1):
            tick_angle = math.radians(start_angle + arc_range * i / num_ticks)
            tick_r_outer = r - 15
            tick_r_inner = r - 28 if i % 2 == 0 else r - 22

            x1 = cx + tick_r_outer * math.cos(tick_angle)
            y1 = cy + tick_r_outer * math.sin(tick_angle)
            x2 = cx + tick_r_inner * math.cos(tick_angle)
            y2 = cy + tick_r_inner * math.sin(tick_angle)

            tick_color = (200, 200, 200, 255) if i % 2 == 0 else (120, 120, 120, 255)
            draw.line([x1, y1, x2, y2], fill=tick_color, width=2)

            # Числа у делений
            if i % 2 == 0:
                label_val = int(max_val * i / num_ticks)
                font_small = load_font(max(10, self.width // 20))
                lx = cx + (tick_r_inner - 12) * math.cos(tick_angle)
                ly = cy + (tick_r_inner - 12) * math.sin(tick_angle)
                draw.text(
                    (lx, ly),
                    str(label_val),
                    font=font_small,
                    fill=(180, 180, 180, 255),
                    anchor="mm"
                )

        # Единица измерения (статична, её рисуем здесь)
        font_unit = load_font(max(10, self.width // 15))
        draw.text(
            (cx, cy + 20),
            self.unit_label,
            font=font_unit,
            fill=(180, 180, 180, 255),
            anchor="mm"
        )

        return img

    def render(self, point: TelemetryPoint, all_points: list) -> Image.Image:
        """Рендерит спидометр для заданной точки телеметрии."""
        cx = self.width // 2
        cy = self.height // 2
        r = min(cx, cy) - 10  # внешний радиус

        # Конвертируем скорость
        if self.unit == "kmh":
            speed_value = point.speed * 3.6  # м/с → км/ч
            max_val = self.max_speed
        else:
            speed_value = point.speed
            max_val = self.max_speed / 3.6

        speed_value = max(0.0, min(speed_value, max_val))

        # Берём статический фон из кэша
        img = self._get_static_background(cx, cy, r, max_val)
        draw = ImageDraw.Draw(img)

        start_angle = self._START_ANGLE
        arc_range = self._ARC_RANGE

        # Заполненная дуга скорости (динамическая)
        speed_ratio = speed_value / max_val if max_val > 0 else 0
        fill_angle = start_angle + arc_range * speed_ratio

        if speed_ratio < 0.5:
            arc_color = (0, 200, 100, 255)
        elif speed_ratio < 0.8:
            arc_color = (255, 165, 0, 255)
        else:
            arc_color = (220, 50, 50, 255)

        if speed_ratio > 0.01:
            draw.arc(
                [cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5],
                start=start_angle,
                end=fill_angle,
                fill=arc_color,
                width=8
            )

        # Стрелка-указатель (динамическая)
        needle_angle = math.radians(start_angle + arc_range * speed_ratio)
        needle_len = r - 30
        nx = cx + needle_len * math.cos(needle_angle)
        ny = cy + needle_len * math.sin(needle_angle)
        draw.line([cx, cy, nx, ny], fill=(255, 255, 255, 230), width=3)

        # Центральная точка
        dot_r = 8
        draw.ellipse(
            [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
            fill=(200, 200, 200, 255)
        )

        # Значение скорости (динамическое)
        font_big = load_font(max(20, self.width // 7))
        speed_text = f"{speed_value:.0f}"
        draw.text(
            (cx, cy - 15),
            speed_text,
            font=font_big,
            fill=(255, 255, 255, 255),
            anchor="mm"
        )

        return img
