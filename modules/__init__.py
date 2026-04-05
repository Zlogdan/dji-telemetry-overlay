# -*- coding: utf-8 -*-
"""
Пакет модулей визуализации телеметрии.
Предоставляет реестр доступных модулей.
"""

import logging

from modules.speedometer import SpeedometerModule
from modules.map_view import MapModule
from modules.text_field import TextFieldModule
from modules.heading import HeadingModule

logger = logging.getLogger(__name__)

# Реестр модулей по имени типа
MODULE_REGISTRY = {
    "speedometer": SpeedometerModule,
    "map": MapModule,
    "text": TextFieldModule,
    "heading": HeadingModule,
}


def create_module(config: dict):
    """
    Создаёт модуль по конфигурации.

    Аргументы:
        config: словарь конфигурации с ключом 'type'

    Возвращает:
        Экземпляр модуля или None если тип неизвестен
    """
    module_type = config.get("type")
    cls = MODULE_REGISTRY.get(module_type)
    if cls is None:
        logger.warning("Неизвестный тип модуля '%s'", module_type)
        return None
    return cls(config)
