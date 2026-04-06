# -*- coding: utf-8 -*-
"""Виджет очереди файлов для пакетной обработки."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)


# ── Статусы элемента очереди ─────────────────────────────────────────────────

STATUS_WAITING = "waiting"
STATUS_EXTRACTING = "extracting"
STATUS_RENDERING = "rendering"
STATUS_DONE = "done"
STATUS_ERROR = "error"

_STATUS_LABELS = {
    STATUS_WAITING: "Ожидание",
    STATUS_EXTRACTING: "Извлечение...",
    STATUS_RENDERING: "Рендеринг...",
    STATUS_DONE: "✓ Готово",
    STATUS_ERROR: "✗ Ошибка",
}

_STATUS_COLORS = {
    STATUS_WAITING: "#aaaaaa",
    STATUS_EXTRACTING: "#f0a000",
    STATUS_RENDERING: "#4499dd",
    STATUS_DONE: "#44bb44",
    STATUS_ERROR: "#dd4444",
}

# Поддерживаемые расширения видеофайлов (строчные)
SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".mov")

# Пользовательская роль для хранения индекса элемента
_ROLE_INDEX = Qt.UserRole


@dataclass
class QueueItem:
    """Элемент очереди пакетной обработки."""

    video_path: str
    output_path: str
    status: str = STATUS_WAITING
    progress: int = 0          # 0–100
    stage_label: str = ""      # «Кадр 12/300»
    telemetry: Optional[dict] = field(default=None, repr=False)
    error: str = ""

    @property
    def filename(self) -> str:
        return Path(self.video_path).name

    def status_text(self) -> str:
        base = _STATUS_LABELS.get(self.status, self.status)
        if self.stage_label and self.status not in (STATUS_DONE, STATUS_ERROR, STATUS_WAITING):
            return f"{base}  {self.stage_label}"
        if self.status == STATUS_ERROR and self.error:
            # Показываем усечённое сообщение об ошибке прямо в тексте
            short = self.error[:60] + ("…" if len(self.error) > 60 else "")
            return f"✗ {short}"
        return base

    def status_color(self) -> str:
        return _STATUS_COLORS.get(self.status, "#aaaaaa")


# ── Делегат для рисования прогресс-бара внутри строки ───────────────────────

class _QueueItemDelegate(QStyledItemDelegate):
    """Рисует полосу прогресса поверх стандартного текста элемента."""

    def paint(self, painter, option: QStyleOptionViewItem, index):
        super().paint(painter, option, index)

        progress = index.data(Qt.UserRole + 1)
        if progress is None or progress <= 0:
            return

        rect = option.rect
        bar_height = 4
        bar_y = rect.bottom() - bar_height - 1
        bar_w = int(rect.width() * progress / 100)

        painter.save()
        painter.setRenderHint(painter.Antialiasing, False)
        # Фон полосы
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#333333"))
        painter.drawRect(rect.left(), bar_y, rect.width(), bar_height)
        # Заполненная часть
        painter.setBrush(QColor("#4499dd"))
        painter.drawRect(rect.left(), bar_y, bar_w, bar_height)
        painter.restore()


# ── Основной виджет ──────────────────────────────────────────────────────────

class FileQueueWidget(QWidget):
    """
    Виджет очереди файлов для пакетной обработки.

    Позволяет добавлять несколько видеофайлов, отображает их статус
    и прогресс выполнения.  Поддерживает перетаскивание файлов (drag-and-drop).
    """

    # Сигнал: пользователь нажал «Добавить файлы»
    files_added = pyqtSignal(list)   # list[str] – добавленные пути

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[QueueItem] = []
        self._build_ui()

    # ── Построение интерфейса ────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        # Список файлов
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setSpacing(2)
        self.list_widget.setMinimumHeight(160)
        self.list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Включаем drag-and-drop из файлового менеджера
        self.list_widget.setAcceptDrops(True)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDrop)
        self.list_widget.viewport().installEventFilter(self)

        delegate = _QueueItemDelegate(self.list_widget)
        self.list_widget.setItemDelegate(delegate)

        layout.addWidget(self.list_widget, 1)

        # Кнопки управления списком
        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        self.add_btn = QPushButton("Добавить файлы…")
        self.add_btn.clicked.connect(self._on_add_files)

        self.remove_btn = QPushButton("Удалить выбранный")
        self.remove_btn.clicked.connect(self._on_remove_selected)

        self.clear_btn = QPushButton("Очистить список")
        self.clear_btn.clicked.connect(self._on_clear)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.clear_btn)

        layout.addWidget(btn_row)

    # ── Drag-and-drop ────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if local_path and Path(local_path).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                    paths.append(local_path)
            if paths:
                self.add_files(paths)
                self.files_added.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def eventFilter(self, obj, event):
        """Перенаправляем drag-and-drop от viewport к виджету."""
        from PyQt5.QtCore import QEvent
        if obj is self.list_widget.viewport():
            if event.type() == QEvent.DragEnter:
                self.dragEnterEvent(event)
                return True
            if event.type() == QEvent.DragMove:
                self.dragMoveEvent(event)
                return True
            if event.type() == QEvent.Drop:
                self.dropEvent(event)
                return True
        return super().eventFilter(obj, event)

    # ── Публичный API ────────────────────────────────────────────────────────

    def add_files(self, paths: List[str], output_ext: str = "mov",
                  output_mode: str = "video"):
        """Добавляет пути в очередь, пропуская дубли."""
        existing = {item.video_path for item in self._items}
        added = []
        for path in paths:
            if path in existing:
                continue
            output_path = self._suggest_output(path, output_ext, output_mode)
            item = QueueItem(video_path=path, output_path=output_path)
            self._items.append(item)
            existing.add(path)
            added.append(path)
            self._add_list_row(len(self._items) - 1)
        return added

    def remove_selected(self):
        """Удаляет выбранные элементы из очереди."""
        selected_rows = sorted(
            {self.list_widget.row(item) for item in self.list_widget.selectedItems()},
            reverse=True
        )
        for row in selected_rows:
            if 0 <= row < len(self._items):
                self._items.pop(row)
                self.list_widget.takeItem(row)
        # Обновляем индексы в оставшихся элементах
        self._rebuild_list()

    def clear(self):
        """Очищает всю очередь."""
        self._items.clear()
        self.list_widget.clear()

    def get_queue(self) -> List[QueueItem]:
        """Возвращает копию текущей очереди."""
        return list(self._items)

    def update_item_status(self, index: int, status: str,
                           progress: int = 0, stage_label: str = "",
                           error: str = ""):
        """Обновляет статус элемента и перерисовывает строку."""
        if index < 0 or index >= len(self._items):
            return
        item = self._items[index]
        item.status = status
        item.progress = progress
        item.stage_label = stage_label
        if error:
            item.error = error
        self._refresh_list_row(index)

    def set_output_ext(self, ext: str, mode: str = "video"):
        """Обновляет расширение выходных файлов у ещё не начатых элементов."""
        for item in self._items:
            if item.status == STATUS_WAITING:
                item.output_path = self._suggest_output(item.video_path, ext, mode)

    def count(self) -> int:
        return len(self._items)

    def set_buttons_enabled(self, enabled: bool):
        """Блокирует/разблокирует кнопки управления очередью."""
        self.add_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)

    # ── Внутренние методы ────────────────────────────────────────────────────

    @staticmethod
    def _suggest_output(video_path: str, ext: str = "mov",
                        mode: str = "video") -> str:
        p = Path(video_path)
        if mode == "png_sequence":
            return str(p.parent / f"{p.stem}_overlay_png")
        return str(p.parent / f"{p.stem}_overlay.{ext}")

    def _make_item_text(self, index: int) -> str:
        item = self._items[index]
        return f"{item.filename}    —    {item.status_text()}"

    def _add_list_row(self, index: int):
        item = self._items[index]
        list_item = QListWidgetItem(self._make_item_text(index))
        list_item.setForeground(QColor(item.status_color()))
        list_item.setData(Qt.UserRole, index)
        list_item.setData(Qt.UserRole + 1, item.progress)
        list_item.setToolTip(item.video_path)
        self.list_widget.addItem(list_item)

    def _refresh_list_row(self, index: int):
        if index < 0 or index >= self.list_widget.count():
            return
        item_data = self._items[index]
        list_item = self.list_widget.item(index)
        if list_item is None:
            return
        list_item.setText(self._make_item_text(index))
        list_item.setForeground(QColor(item_data.status_color()))
        list_item.setData(Qt.UserRole + 1, item_data.progress)
        if item_data.error:
            list_item.setToolTip(f"{item_data.video_path}\n\nОшибка: {item_data.error}")
        else:
            list_item.setToolTip(item_data.video_path)

    def _rebuild_list(self):
        """Перестраивает список после удаления элементов."""
        self.list_widget.clear()
        for i in range(len(self._items)):
            self._add_list_row(i)

    # ── Слоты кнопок ────────────────────────────────────────────────────────

    def _on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите видеофайлы DJI",
            str(Path.home()),
            "Видео (*.mp4 *.mov *.MP4 *.MOV);;Все файлы (*)"
        )
        if paths:
            self.add_files(paths)
            self.files_added.emit(paths)

    def _on_remove_selected(self):
        self.remove_selected()

    def _on_clear(self):
        self.clear()
