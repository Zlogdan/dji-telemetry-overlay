# -*- coding: utf-8 -*-
"""
Модуль компаса. Отображает текущий курс в виде компасной розы.
"""

import math
from PIL import Image, ImageDraw
from modules.base import OverlayModule
from modules.utils import load_font
from core.parser import TelemetryPoint


# Стороны света на русском языке
CARDINAL_POINTS = {
    0: "С",    # Север
    90: "В",   # Восток
    180: "Ю",  # Юг
    270: "З",  # Запад
}


class HeadingModule(OverlayModule):
    """Компас с вращающейся стрелкой и подписями сторон света."""

    def __init__(self, config: dict):
        super().__init__(config)

    def render(self, point: TelemetryPoint, all_points: list) -> Image.Image:
        """Рендерит компас для заданного курса."""
        img = self.create_canvas()
        draw = ImageDraw.Draw(img)

        cx = self.width // 2
        cy = self.height // 2
        r = min(cx, cy) - 10

        # Фон
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(20, 20, 20, 200)
        )

        # Внешняя граница
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=(100, 100, 100, 255),
            width=2
        )

        heading = point.heading

        # Деления компаса
        for deg in range(0, 360, 10):
            angle_rad = math.radians(deg - heading - 90)
            if deg % 90 == 0:
                tick_len = 15
                tick_color = (255, 255, 255, 255)
                tick_width = 2
            elif deg % 30 == 0:
                tick_len = 10
                tick_color = (200, 200, 200, 200)
                tick_width = 1
            else:
                tick_len = 5
                tick_color = (130, 130, 130, 160)
                tick_width = 1

            x1 = cx + (r - 8) * math.cos(angle_rad)
            y1 = cy + (r - 8) * math.sin(angle_rad)
            x2 = cx + (r - 8 - tick_len) * math.cos(angle_rad)
            y2 = cy + (r - 8 - tick_len) * math.sin(angle_rad)

            draw.line([x1, y1, x2, y2], fill=tick_color, width=tick_width)

        # Буквы сторон света (вращаются вместе с розой)
        font_cardinal = load_font(max(12, self.width // 12))
        for deg, label in CARDINAL_POINTS.items():
            angle_rad = math.radians(deg - heading - 90)
            lx = cx + (r - 30) * math.cos(angle_rad)
            ly = cy + (r - 30) * math.sin(angle_rad)

            color = (255, 80, 80, 255) if label == "С" else (220, 220, 220, 255)
            draw.text((lx, ly), label, font=font_cardinal, fill=color, anchor="mm")

        # Стрелка компаса (всегда указывает вверх = на север)
        needle_len = r - 40

        # Красная часть (север — вверх)
        draw.polygon(
            [
                (cx, cy - needle_len),
                (cx - 6, cy),
                (cx + 6, cy),
            ],
            fill=(220, 50, 50, 230)
        )

        # Белая часть (юг — вниз)
        draw.polygon(
            [
                (cx, cy + needle_len),
                (cx - 6, cy),
                (cx + 6, cy),
            ],
            fill=(220, 220, 220, 200)
        )

        # Центральный круг
        dot_r = 6
        draw.ellipse(
            [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
            fill=(200, 200, 200, 255)
        )

        # Значение курса
        font_deg = load_font(max(10, self.width // 14))
        heading_text = f"{heading:.0f}°"

        # Фон для текста курса
        try:
            tbbox = font_deg.getbbox(heading_text)
            tw = tbbox[2] - tbbox[0]
            th = tbbox[3] - tbbox[1]
        except AttributeError:
            tw, th = font_deg.getsize(heading_text)

        tx = cx - tw // 2 - 4
        ty = cy + dot_r + 6
        draw.rectangle([tx, ty, tx + tw + 8, ty + th + 4], fill=(0, 0, 0, 160))
        draw.text(
            (cx, ty + 2),
            heading_text,
            font=font_deg,
            fill=(255, 255, 200, 255),
            anchor="mt"
        )

        return img
