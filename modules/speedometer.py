# -*- coding: utf-8 -*-
"""
Модуль спидометра. Отображает скорость в виде круглого индикатора.
"""

import math
from PIL import Image, ImageDraw, ImageFont
from modules.base import OverlayModule
from core.parser import TelemetryPoint


def _load_font(size: int) -> ImageFont.ImageFont:
    """Загружает шрифт заданного размера, используя резервный при ошибке."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except (IOError, OSError):
        try:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        except (IOError, OSError):
            return ImageFont.load_default()


class SpeedometerModule(OverlayModule):
    """Круговой спидометр с дугой и цифровым отображением скорости."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.max_speed = config.get("max_speed", 150)  # максимум в км/ч
        self.unit = config.get("unit", "kmh")  # kmh или ms
        self.unit_label = "км/ч" if self.unit == "kmh" else "м/с"

    def render(self, point: TelemetryPoint, all_points: list) -> Image.Image:
        """Рендерит спидометр для заданной точки телеметрии."""
        img = self.create_canvas()
        draw = ImageDraw.Draw(img)

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

        # Рисуем тёмный фон круга
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(20, 20, 20, 200)
        )

        # Параметры дуги: от 210° до 330° (300° диапазон)
        start_angle = 210
        end_angle = 330
        arc_range = 300  # градусов

        # Внешняя граница
        draw.arc(
            [cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5],
            start=start_angle,
            end=end_angle,
            fill=(60, 60, 60, 255),
            width=8
        )

        # Заполненная дуга скорости
        speed_ratio = speed_value / max_val if max_val > 0 else 0
        fill_angle = start_angle + arc_range * speed_ratio

        # Цвет дуги зависит от скорости
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
                font_small = _load_font(max(10, self.width // 20))
                lx = cx + (tick_r_inner - 12) * math.cos(tick_angle)
                ly = cy + (tick_r_inner - 12) * math.sin(tick_angle)
                draw.text(
                    (lx, ly),
                    str(label_val),
                    font=font_small,
                    fill=(180, 180, 180, 255),
                    anchor="mm"
                )

        # Стрелка-указатель
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

        # Значение скорости
        font_big = _load_font(max(20, self.width // 7))
        speed_text = f"{speed_value:.0f}"
        draw.text(
            (cx, cy - 15),
            speed_text,
            font=font_big,
            fill=(255, 255, 255, 255),
            anchor="mm"
        )

        # Единица измерения
        font_unit = _load_font(max(10, self.width // 15))
        draw.text(
            (cx, cy + 20),
            self.unit_label,
            font=font_unit,
            fill=(180, 180, 180, 255),
            anchor="mm"
        )

        return img
