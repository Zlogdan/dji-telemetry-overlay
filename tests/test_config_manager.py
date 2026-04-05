# -*- coding: utf-8 -*-
"""Тесты для модуля config/config_manager.py."""

import json
import pytest
import tempfile
import os
from pathlib import Path
from config.config_manager import ConfigManager


class TestConfigManagerDefaults:
    def test_default_config_has_width(self):
        cm = ConfigManager.__new__(ConfigManager)
        cfg = cm._default_config()
        assert cfg["width"] == 1920

    def test_default_config_has_height(self):
        cm = ConfigManager.__new__(ConfigManager)
        cfg = cm._default_config()
        assert cfg["height"] == 1080

    def test_default_config_has_modules_list(self):
        cm = ConfigManager.__new__(ConfigManager)
        cfg = cm._default_config()
        assert "modules" in cfg
        assert isinstance(cfg["modules"], list)


class TestConfigManagerLoad:
    def test_loads_valid_json(self, tmp_path):
        config_data = {"width": 1280, "height": 720, "modules": []}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        cm = ConfigManager(str(config_file))
        assert cm.get("width") == 1280
        assert cm.get("height") == 720

    def test_missing_file_uses_defaults(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        cm = ConfigManager(str(missing))
        assert cm.get("width") == 1920
        assert cm.get("height") == 1080

    def test_invalid_json_uses_defaults(self, tmp_path):
        config_file = tmp_path / "bad.json"
        config_file.write_text("{ this is not json }", encoding="utf-8")
        cm = ConfigManager(str(config_file))
        assert cm.get("width") == 1920

    def test_get_with_default(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"width": 800}', encoding="utf-8")
        cm = ConfigManager(str(config_file))
        assert cm.get("nonexistent_key", "fallback") == "fallback"


class TestConfigManagerSave:
    def test_save_creates_file(self, tmp_path):
        config_data = {"width": 1920, "height": 1080, "modules": []}
        source = tmp_path / "source.json"
        source.write_text(json.dumps(config_data), encoding="utf-8")

        cm = ConfigManager(str(source))
        save_path = tmp_path / "saved.json"
        cm.save(str(save_path))

        assert save_path.exists()

    def test_save_and_reload_roundtrip(self, tmp_path):
        config_data = {"width": 1280, "height": 720, "modules": [{"type": "speedometer"}]}
        source = tmp_path / "source.json"
        source.write_text(json.dumps(config_data), encoding="utf-8")

        cm = ConfigManager(str(source))
        save_path = tmp_path / "roundtrip.json"
        cm.save(str(save_path))

        cm2 = ConfigManager(str(save_path))
        assert cm2.get("width") == 1280
        assert cm2.get("height") == 720

    def test_save_creates_parent_dirs(self, tmp_path):
        config_data = {"width": 1920, "height": 1080, "modules": []}
        source = tmp_path / "source.json"
        source.write_text(json.dumps(config_data), encoding="utf-8")

        cm = ConfigManager(str(source))
        nested_path = tmp_path / "a" / "b" / "c" / "config.json"
        cm.save(str(nested_path))
        assert nested_path.exists()


class TestConfigManagerGetModuleConfig:
    def test_returns_modules_of_given_type(self, tmp_path):
        config_data = {
            "width": 1920, "height": 1080,
            "modules": [
                {"type": "speedometer", "x": 0},
                {"type": "map", "x": 100},
                {"type": "speedometer", "x": 200},
            ]
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        cm = ConfigManager(str(config_file))
        speedometers = cm.get_module_config("speedometer")
        assert len(speedometers) == 2

    def test_returns_empty_list_for_unknown_type(self, tmp_path):
        config_data = {"width": 1920, "height": 1080, "modules": []}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        cm = ConfigManager(str(config_file))
        result = cm.get_module_config("unknown_module")
        assert result == []
