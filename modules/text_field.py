# -*- coding: utf-8 -*-
"""
Модуль текстового поля телеметрии.
Отображает одно значение (скорость, высота, координаты, курс).
"""

from PIL import Image, ImageDraw, ImageFont
from modules.base import OverlayModule
from core.parser import TelemetryPoint


def _load_font(size: int) -> ImageFont.ImageFont:
    """Загружает шрифт заданного размера."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Windows/Fonts/arial.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# Метки полей телеметрии по умолчанию
DEFAULT_LABELS = {
    "speed": "Скорость",
    "alt": "Высота",
    "lat": "Широта",
    "lon": "Долгота",
    "heading": "Курс",
}

# Единицы измерения по умолчанию
DEFAULT_UNITS = {
    "speed": "км/ч",
    "alt": "м",
    "lat": "°",
    "lon": "°",
    "heading": "°",
}


class TextFieldModule(OverlayModule):
    """Текстовое поле с меткой и значением телеметрии."""

    def __init__(self, config: dict):
        # Размер по умолчанию для текстового поля
        if "width" not in config:
            config["width"] = 250
        if "height" not in config:
            config["height"] = 60
        super().__init__(config)

        self.field = config.get("field", "speed")
        self.label = config.get("label", DEFAULT_LABELS.get(self.field, self.field))
        self.unit = config.get("unit", DEFAULT_UNITS.get(self.field, ""))
        self.font_size = config.get("font_size", 36)
        self.bg_alpha = config.get("bg_alpha", 160)

    def _get_value(self, point: TelemetryPoint) -> str:
        """Извлекает значение из точки телеметрии."""
        field = self.field
        if field == "speed":
            val = point.speed * 3.6  # м/с → км/ч
            return f"{val:.1f}"
        elif field == "alt":
            return f"{point.alt:.1f}"
        elif field == "lat":
            return f"{point.lat:.5f}"
        elif field == "lon":
            return f"{point.lon:.5f}"
        elif field == "heading":
            return f"{point.heading:.1f}"
        return "—"

    def render(self, point: TelemetryPoint, all_points: list) -> Image.Image:
        """Рендерит текстовое поле телеметрии."""
        font = _load_font(self.font_size)
        label_font = _load_font(max(12, self.font_size // 2))

        value_str = self._get_value(point)
        display_text = f"{value_str} {self.unit}".strip()

        # Определяем размер текста
        try:
            bbox = font.getbbox(display_text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except AttributeError:
            text_w, text_h = font.getsize(display_text)

        try:
            lbbox = label_font.getbbox(self.label)
            label_w = lbbox[2] - lbbox[0]
            label_h = lbbox[3] - lbbox[1]
        except AttributeError:
            label_w, label_h = label_font.getsize(self.label)

        # Размер холста
        pad = 8
        total_w = max(text_w, label_w) + pad * 2
        total_h = label_h + text_h + pad * 3

        self.width = max(self.width, total_w)
        self.height = max(self.height, total_h)

        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Фон с закруглёнными углами (прямоугольник)
        draw.rectangle(
            [0, 0, self.width - 1, self.height - 1],
            fill=(10, 10, 10, self.bg_alpha)
        )

        # Метка (меньший шрифт, серый цвет)
        draw.text(
            (pad, pad),
            self.label,
            font=label_font,
            fill=(180, 180, 180, 255)
        )

        # Тень значения
        value_y = pad + label_h + pad // 2
        draw.text(
            (pad + 1, value_y + 1),
            display_text,
            font=font,
            fill=(0, 0, 0, 180)
        )

        # Значение
        draw.text(
            (pad, value_y),
            display_text,
            font=font,
            fill=(255, 255, 255, 255)
        )

        return img
