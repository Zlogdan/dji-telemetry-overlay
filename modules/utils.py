# -*- coding: utf-8 -*-
"""
Вспомогательные утилиты для модулей оверлея.
Общие функции, используемые несколькими модулями.
"""

from PIL import ImageFont


def load_font(size: int) -> ImageFont.ImageFont:
    """
    Загружает шрифт заданного размера с автоматическим выбором из доступных.

    Пробует несколько путей (Linux, macOS, Windows), при неудаче
    возвращает встроенный шрифт Pillow.

    Аргументы:
        size: размер шрифта в пунктах

    Возвращает:
        Объект ImageFont
    """
    # Пути к шрифтам для разных ОС
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",         # Ubuntu/Debian
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", # Linux
        "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",          # Fedora/RHEL
        "/System/Library/Fonts/Helvetica.ttc",                          # macOS
        "/System/Library/Fonts/Arial.ttf",                              # macOS alt
        "C:/Windows/Fonts/arialbd.ttf",                                 # Windows
        "C:/Windows/Fonts/arial.ttf",                                   # Windows fallback
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    # Резервный встроенный шрифт
    return ImageFont.load_default()


def get_text_size(font: ImageFont.ImageFont, text: str) -> tuple:
    """
    Возвращает (ширину, высоту) текста с учётом версии Pillow.

    Поддерживает как старый API (getsize), так и новый (getbbox).

    Аргументы:
        font: объект ImageFont
        text: строка для измерения

    Возвращает:
        Кортеж (width, height)
    """
    try:
        # Новый API Pillow >= 8.0
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        # Старый API Pillow < 8.0
        return font.getsize(text)
