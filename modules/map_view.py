# -*- coding: utf-8 -*-
"""
Модуль карты. Отображает GPS-трек на выбранной карте (OSM, Яндекс, Google).
"""

import math
import logging
import os
import hashlib
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from modules.base import OverlayModule
from core.parser import TelemetryPoint

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Кеш-директория для тайлов
TILE_CACHE_DIR = Path.home() / ".cache" / "telemetry-overlay" / "tiles"

# Заголовки запроса тайлов
TILE_HEADERS = {"User-Agent": "DJI-Telemetry-Overlay/1.0"}

# Максимальное количество тайлов в памяти
MAX_TILE_CACHE_SIZE = 256

# Провайдеры карт: шаблоны URL тайлов (параметры {z}, {x}, {y})
MAP_PROVIDERS = {
    "osm":        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "yandex_map": "https://core-renderer-tiles.maps.yandex.net/tiles?l=map&x={x}&y={y}&z={z}&scale=1&lang=ru_RU",
    "yandex_sat": "https://core-sat.maps.yandex.net/tiles?l=sat&x={x}&y={y}&z={z}&scale=1&lang=ru_RU",
    "google_sat": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
}

# Человекочитаемые названия провайдеров
MAP_PROVIDER_LABELS = {
    "osm":        "OpenStreetMap",
    "yandex_map": "Яндекс Карты",
    "yandex_sat": "Яндекс Спутник",
    "google_sat": "Google Спутник",
}


def lat_lon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    """Конвертирует координаты в номер тайла Web Mercator."""
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y


def lat_lon_to_pixel(lat: float, lon: float, zoom: int, tile_size: int = 256) -> Tuple[float, float]:
    """Конвертирует координаты в пиксельные координаты Web Mercator."""
    n = 2 ** zoom
    px = (lon + 180) / 360 * n * tile_size
    lat_rad = math.radians(lat)
    py = (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n * tile_size
    return px, py


def _get_tile_cache_path(provider: str, zoom: int, x: int, y: int) -> Path:
    """Возвращает путь к кешированному тайлу."""
    return TILE_CACHE_DIR / provider / str(zoom) / str(x) / f"{y}.png"


def _build_tile_url(provider: str, zoom: int, x: int, y: int) -> str:
    """Формирует URL тайла для указанного провайдера."""
    template = MAP_PROVIDERS.get(provider, MAP_PROVIDERS["osm"])
    return template.format(z=zoom, x=x, y=y)


def _download_tile(provider: str, zoom: int, x: int, y: int) -> Optional[Image.Image]:
    """Скачивает тайл у указанного провайдера или берёт из кеша."""
    cache_path = _get_tile_cache_path(provider, zoom, x, y)

    # Проверяем кеш
    if cache_path.exists():
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception:
            logger.debug("Не удалось открыть кешированный тайл: %s", cache_path, exc_info=True)

    if not REQUESTS_AVAILABLE:
        return None

    # Скачиваем тайл
    url = _build_tile_url(provider, zoom, x, y)
    try:
        response = requests.get(url, headers=TILE_HEADERS, timeout=5)
        if response.status_code == 200:
            # Сохраняем в кеш
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(response.content)
            import io
            return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except requests.RequestException as exc:
        logger.debug("Ошибка загрузки тайла %s: %s", url, exc)

    return None


def _make_fallback_map(width: int, height: int) -> Image.Image:
    """Создаёт резервный фон карты с координатной сеткой."""
    img = Image.new("RGBA", (width, height), (30, 35, 45, 220))
    draw = ImageDraw.Draw(img)

    # Рисуем сетку
    step = 40
    for x in range(0, width, step):
        draw.line([(x, 0), (x, height)], fill=(50, 55, 65, 255), width=1)
    for y in range(0, height, step):
        draw.line([(0, y), (width, y)], fill=(50, 55, 65, 255), width=1)

    return img


class MapModule(OverlayModule):
    """Модуль отображения карты с GPS-треком."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.zoom = config.get("zoom", 14)
        self.map_provider = config.get("map_provider", "osm")
        self._tile_cache = {}  # кеш загруженных тайлов в памяти

    def _get_tile(self, zoom: int, x: int, y: int) -> Optional[Image.Image]:
        """Получает тайл из памяти или скачивает."""
        key = (self.map_provider, zoom, x, y)
        if key not in self._tile_cache:
            # Ограничиваем размер кеша: удаляем первый элемент при переполнении
            if len(self._tile_cache) >= MAX_TILE_CACHE_SIZE:
                self._tile_cache.pop(next(iter(self._tile_cache)))
            self._tile_cache[key] = _download_tile(self.map_provider, zoom, x, y)
        return self._tile_cache[key]

    def _build_map_image(self, center_lat: float, center_lon: float) -> Tuple[Image.Image, float, float]:
        """
        Собирает изображение карты из тайлов.

        Возвращает:
            (изображение карты, pixel_x центра, pixel_y центра)
        """
        zoom = self.zoom
        tile_size = 256

        # Центральный тайл
        cx_tile, cy_tile = lat_lon_to_tile(center_lat, center_lon, zoom)

        # Сколько тайлов нужно в каждую сторону
        tiles_x = math.ceil(self.width / tile_size) + 2
        tiles_y = math.ceil(self.height / tile_size) + 2

        # Диапазон тайлов
        x_start = cx_tile - tiles_x // 2
        y_start = cy_tile - tiles_y // 2
        x_end = x_start + tiles_x
        y_end = y_start + tiles_y

        map_width = (x_end - x_start) * tile_size
        map_height = (y_end - y_start) * tile_size

        map_img = Image.new("RGBA", (map_width, map_height), (40, 44, 52, 255))

        # Наклеиваем тайлы
        for tx in range(x_start, x_end):
            for ty in range(y_start, y_end):
                tile = self._get_tile(zoom, tx, ty)
                if tile:
                    px = (tx - x_start) * tile_size
                    py = (ty - y_start) * tile_size
                    # Затемняем тайл для лучшего контраста
                    darkened = Image.new("RGBA", tile.size, (0, 0, 0, 80))
                    tile_copy = tile.copy()
                    tile_copy.paste(darkened, mask=darkened)
                    map_img.paste(tile_copy, (px, py))

        # Пиксельные координаты центра
        center_px, center_py = lat_lon_to_pixel(center_lat, center_lon, zoom, tile_size)
        origin_px = x_start * tile_size
        origin_py = y_start * tile_size

        rel_cx = center_px - origin_px
        rel_cy = center_py - origin_py

        return map_img, rel_cx, rel_cy

    def render(self, point: TelemetryPoint, all_points: list) -> Image.Image:
        """Рендерит карту с треком и текущей позицией."""
        img = self.create_canvas()

        # Нет данных
        if not all_points or (point.lat == 0.0 and point.lon == 0.0):
            fallback = _make_fallback_map(self.width, self.height)
            img.paste(fallback, (0, 0))
            return img

        center_lat = point.lat
        center_lon = point.lon

        # Строим карту
        try:
            map_img, rel_cx, rel_cy = self._build_map_image(center_lat, center_lon)
        except Exception:
            fallback = _make_fallback_map(self.width, self.height)
            img.paste(fallback, (0, 0))
            return img

        # Вырезаем нужный фрагмент (центрируем на позиции)
        crop_x = int(rel_cx - self.width // 2)
        crop_y = int(rel_cy - self.height // 2)

        crop_box = (
            max(0, crop_x),
            max(0, crop_y),
            min(map_img.width, crop_x + self.width),
            min(map_img.height, crop_y + self.height)
        )
        cropped = map_img.crop(crop_box)

        # Позиционируем на холсте
        paste_x = max(0, -crop_x)
        paste_y = max(0, -crop_y)
        img.paste(cropped, (paste_x, paste_y))

        draw = ImageDraw.Draw(img)

        zoom = self.zoom
        tile_size = 256

        # Смещение для перевода геокоординат в координаты холста
        center_px_ref, center_py_ref = lat_lon_to_pixel(center_lat, center_lon, zoom, tile_size)

        def geo_to_canvas(lat: float, lon: float) -> Tuple[float, float]:
            px, py = lat_lon_to_pixel(lat, lon, zoom, tile_size)
            cx_canvas = px - center_px_ref + self.width // 2
            cy_canvas = py - center_py_ref + self.height // 2
            return cx_canvas, cy_canvas

        # Рисуем трек
        track_points = []
        for p in all_points:
            if isinstance(p, dict):
                lat, lon = p.get("lat", 0), p.get("lon", 0)
            else:
                lat, lon = p.lat, p.lon
            if lat != 0 or lon != 0:
                track_points.append(geo_to_canvas(lat, lon))

        if len(track_points) >= 2:
            draw.line(track_points, fill=(100, 180, 255, 180), width=3)

        # Текущая позиция
        pos_x, pos_y = geo_to_canvas(point.lat, point.lon)

        # Внешний круг
        r = 8
        draw.ellipse(
            [pos_x - r - 3, pos_y - r - 3, pos_x + r + 3, pos_y + r + 3],
            fill=(255, 255, 255, 180)
        )
        draw.ellipse(
            [pos_x - r, pos_y - r, pos_x + r, pos_y + r],
            fill=(255, 80, 80, 255)
        )

        # Стрелка направления
        heading_rad = math.radians(point.heading - 90)
        arrow_len = 20
        ax = pos_x + arrow_len * math.cos(heading_rad)
        ay = pos_y + arrow_len * math.sin(heading_rad)
        draw.line([pos_x, pos_y, ax, ay], fill=(255, 255, 100, 230), width=3)

        # Рамка карты
        draw.rectangle([0, 0, self.width - 1, self.height - 1], outline=(100, 100, 100, 200), width=2)

        # Полупрозрачный оверлей по краям
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        edge = 15
        ov_draw.rectangle([0, 0, self.width, edge], fill=(0, 0, 0, 100))
        ov_draw.rectangle([0, self.height - edge, self.width, self.height], fill=(0, 0, 0, 100))
        ov_draw.rectangle([0, 0, edge, self.height], fill=(0, 0, 0, 100))
        ov_draw.rectangle([self.width - edge, 0, self.width, self.height], fill=(0, 0, 0, 100))
        img = Image.alpha_composite(img, overlay)

        return img
