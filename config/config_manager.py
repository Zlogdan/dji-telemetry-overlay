# -*- coding: utf-8 -*-
"""Менеджер конфигурации приложения."""

import json
import logging
import os
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class ConfigManager:
    """Управляет загрузкой и сохранением конфигурации."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent / "default.json"
        self.config_path = Path(config_path)
        self.config = self._load()

    def _load(self) -> dict:
        """Загружает конфигурацию из файла."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("Файл конфигурации не найден: %s. Используется конфигурация по умолчанию.", self.config_path)
            return self._default_config()
        except json.JSONDecodeError as e:
            logger.error("Ошибка разбора конфигурации: %s. Используется конфигурация по умолчанию.", e)
            return self._default_config()

    def _default_config(self) -> dict:
        """Возвращает конфигурацию по умолчанию."""
        return {
            "width": 1920,
            "height": 1080,
            "export": {
                "mode": "video",
                "output_format": "mov",
                "render_fps": 30,
            },
            "performance": {
                "ffprobe_timeout": 30,
                "ffmpeg_timeout": 60,
                "png_compress_level": 1,
                "prores_qscale": 11,
                "vp9_crf": 34,
                "vp9_cpu_used": 2,
            },
            "extraction": {
                "pyosmogps_frequency": 1,
                "pyosmogps_resampling_method": "lpf",
                "pyosmogps_timezone_offset": 3,
            },
            "modules": []
        }

    def save(self, path: str = None):
        """Сохраняет конфигурацию в файл."""
        save_path = Path(path) if path else self.config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get_module_config(self, module_type: str) -> List[dict]:
        """Возвращает конфигурацию модулей заданного типа."""
        return [m for m in self.config.get("modules", []) if m.get("type") == module_type]

    def get(self, key: str, default=None):
        """Возвращает значение из конфигурации."""
        return self.config.get(key, default)
