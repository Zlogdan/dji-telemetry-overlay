# -*- coding: utf-8 -*-
"""Менеджер конфигурации приложения."""

import json
import os
from pathlib import Path
from typing import Optional, List


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
            print(f"Файл конфигурации не найден: {self.config_path}. Используется конфигурация по умолчанию.")
            return self._default_config()
        except json.JSONDecodeError as e:
            print(f"Ошибка разбора конфигурации: {e}. Используется конфигурация по умолчанию.")
            return self._default_config()

    def _default_config(self) -> dict:
        """Возвращает конфигурацию по умолчанию."""
        return {
            "width": 1920,
            "height": 1080,
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
