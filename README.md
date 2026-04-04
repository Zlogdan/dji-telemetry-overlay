# DJI Telemetry Overlay

Приложение для создания прозрачного видеооверлея с телеметрическими данными из видеозаписей DJI.

## Описание

**DJI Telemetry Overlay** автоматически извлекает GPS-телеметрию из видеофайлов DJI (MP4/MOV) и генерирует прозрачный видеооверлей с визуализацией данных полёта. Полученный оверлей можно совместить с исходным видео в любом видеоредакторе.

Поддерживаемые элементы визуализации:
- 🎯 **Спидометр** — круговой индикатор скорости с дугой и стрелкой
- 🗺️ **Карта** — GPS-трек на карте OpenStreetMap с маркером текущей позиции
- 🧭 **Компас** — компасная роза с указателем курса
- 📊 **Текстовые поля** — цифровое отображение скорости, высоты, координат

## Требования

### Системные
- Python 3.8 или выше
- FFmpeg (с поддержкой ProRes и VP9)

### Python-пакеты
```
PyQt5>=5.15.0
Pillow>=9.0.0
numpy>=1.21.0
requests>=2.26.0
```

### Установка FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Windows:**
Скачайте с [ffmpeg.org](https://ffmpeg.org/download.html) и добавьте в PATH.

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/your-org/dji-telemetry-overlay.git
cd dji-telemetry-overlay

# Установить зависимости
pip install -r requirements.txt
```

## Использование

### Запуск GUI

```bash
python main.py
```

### Интерфейс

1. **Выбор файлов** — укажите исходный видеофайл DJI и путь для сохранения оверлея
2. **Извлечь телеметрию** — анализирует видео и извлекает GPS-данные
3. **Демо-телеметрия** — генерирует тестовую телеметрию (круговой маршрут над Москвой)
4. **Настройка модулей** — включите/отключите нужные элементы визуализации
5. **Параметры** — настройте масштаб карты, максимальную скорость, размер кадра
6. **Создать оверлей** — рендерит финальный видеофайл

### Программное использование

```python
from core.extractor import extract_telemetry, generate_demo_telemetry
from renderer.engine import RenderEngine
from config.config_manager import ConfigManager

# Загружаем конфигурацию
config = ConfigManager()

# Извлекаем телеметрию из видео
telemetry = extract_telemetry("path/to/DJI_video.MP4")

# Или генерируем демо
telemetry = generate_demo_telemetry(duration=60.0, fps=30.0)

# Рендерим оверлей
engine = RenderEngine(config.config)
engine.render_to_video(telemetry, "overlay_output.mov")
```

## Конфигурация

Конфигурация хранится в `config/default.json`. Можно загружать/сохранять через меню.

### Формат конфигурации

```json
{
  "width": 1920,
  "height": 1080,
  "modules": [
    {
      "type": "speedometer",
      "x": 100,
      "y": 820,
      "width": 200,
      "height": 200,
      "max_speed": 150,
      "unit": "kmh",
      "enabled": true
    },
    {
      "type": "map",
      "x": 1580,
      "y": 50,
      "width": 300,
      "height": 300,
      "zoom": 14,
      "enabled": true
    },
    {
      "type": "text",
      "x": 50,
      "y": 50,
      "field": "speed",
      "label": "Скорость",
      "unit": "км/ч",
      "font_size": 36,
      "enabled": true
    },
    {
      "type": "heading",
      "x": 350,
      "y": 820,
      "width": 180,
      "height": 180,
      "enabled": true
    }
  ]
}
```

### Параметры модулей

| Параметр | Описание |
|----------|----------|
| `type` | Тип модуля: `speedometer`, `map`, `text`, `heading` |
| `x`, `y` | Позиция на кадре (пиксели) |
| `width`, `height` | Размер модуля (пиксели) |
| `enabled` | Включён ли модуль |

**Speedometer:**
- `max_speed` — максимум шкалы (км/ч)
- `unit` — единицы: `kmh` или `ms`

**Map:**
- `zoom` — уровень масштаба (1–19)

**Text:**
- `field` — поле телеметрии: `speed`, `alt`, `lat`, `lon`, `heading`
- `label` — подпись поля
- `unit` — единица измерения
- `font_size` — размер шрифта

## Архитектура

```
dji-telemetry-overlay/
├── main.py                  # Точка входа
├── requirements.txt
├── config/
│   ├── config_manager.py    # Загрузка/сохранение конфигурации
│   └── default.json         # Конфигурация по умолчанию
├── core/
│   ├── extractor.py         # Извлечение телеметрии из видео
│   ├── parser.py            # Разбор NMEA-данных GPS
│   └── interpolator.py      # Интерполяция телеметрии до FPS
├── modules/
│   ├── base.py              # Базовый класс модуля
│   ├── speedometer.py       # Круговой спидометр
│   ├── map_view.py          # Карта с GPS-треком
│   ├── text_field.py        # Текстовое поле
│   └── heading.py           # Компас
├── renderer/
│   └── engine.py            # Движок рендеринга (FFmpeg)
└── ui/
    └── main_window.py       # Главное окно PyQt5
```

### Поток данных

```
Видеофайл DJI
    ↓
core/extractor.py  →  ffprobe + ffmpeg  →  NMEA-данные
    ↓
core/parser.py     →  TelemetryPoint[]
    ↓
core/interpolator.py  →  интерполяция до FPS
    ↓
renderer/engine.py    →  render_frame() для каждого кадра
    ↓
modules/*.py          →  PIL-изображения RGBA
    ↓
FFmpeg stdin          →  ProRes 4444 / VP9 с альфа-каналом
```

## Описание модулей

### `core/extractor.py`
Извлекает телеметрию из видеофайлов DJI. Использует `ffprobe` для анализа потоков и `ffmpeg` для извлечения данных. Поддерживает NMEA-данные в потоке данных и метаданных MP4. При отсутствии реальной телеметрии генерирует демонстрационную.

### `core/parser.py`
Разбирает NMEA-предложения (`GPRMC`, `GPGGA`, `GNRMC`, `GNGGA`). Конвертирует координаты из формата NMEA в десятичные градусы. Проверяет контрольные суммы.

### `core/interpolator.py`
Интерполирует разреженные точки телеметрии (1 Гц) до частоты кадров видео (30+ FPS). Использует бинарный поиск для эффективной интерполяции. Поддерживает сглаживание скользящим средним и корректную интерполяцию углов.

### `modules/speedometer.py`
Рисует круговой спидометр с дугой (0–300°), делениями шкалы, стрелкой и цифровым значением. Цвет дуги меняется от зелёного к красному по мере роста скорости.

### `modules/map_view.py`
Загружает тайлы OpenStreetMap (с кешированием на диске), собирает карту и рисует GPS-трек с маркером текущей позиции и стрелкой курса.

### `modules/heading.py`
Отображает компасную розу с вращающимися делениями и подписями сторон света. Стрелка всегда указывает вверх (на север), а роза вращается согласно курсу.

### `renderer/engine.py`
Основной движок рендеринга. Для каждого кадра вызывает все активные модули, компонует RGBA-изображение и передаёт в `stdin` процесса FFmpeg для кодирования в ProRes 4444 (MOV) или VP9 (WebM) с альфа-каналом.

## Выходные форматы

| Расширение | Кодек | Описание |
|------------|-------|----------|
| `.mov` | ProRes 4444 | Максимальное качество, большой файл, для NLE-редакторов |
| `.webm` | VP9 | Меньший размер, поддержка браузерами |

## Лицензия

MIT License

Copyright (c) 2024 DJI Telemetry Overlay Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.