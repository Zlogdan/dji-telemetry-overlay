# -*- coding: utf-8 -*-
"""Базовый класс для всех модулей визуализации."""

from abc import ABC, abstractmethod
from PIL import Image, ImageDraw
from core.parser import TelemetryPoint


class OverlayModule(ABC):
    """Абстрактный базовый класс модуля наложения."""

    def __init__(self, config: dict):
        self.config = config
        self.position = (config.get("x", 0), config.get("y", 0))
        self.width = config.get("width", 200)
        self.height = config.get("height", 200)
        self.enabled = config.get("enabled", True)

    @abstractmethod
    def render(self, point: TelemetryPoint, all_points: list) -> Image.Image:
        """
        Рендерит модуль и возвращает изображение с альфа-каналом (RGBA).

        Аргументы:
            point: текущая точка телеметрии
            all_points: все точки маршрута (для карты)

        Возвращает:
            PIL.Image в режиме RGBA
        """
        pass

    def get_position(self) -> tuple:
        """Возвращает позицию модуля на холсте."""
        return self.position

    def create_canvas(self) -> Image.Image:
        """Создаёт прозрачный холст нужного размера."""
        return Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
