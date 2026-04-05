#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главный модуль приложения telemetry-overlay-engine.
"""

import logging
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    app = QApplication(sys.argv)
    app.setApplicationName("DJI Telemetry Overlay")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
