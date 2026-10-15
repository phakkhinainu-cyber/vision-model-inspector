"""Application entry point."""
from __future__ import annotations

import logging
import os
import sys


def create_app(argv=None):
    os.environ.setdefault("YOLO_OFFLINE", "True")
    os.environ.setdefault("YOLO_AUTOINSTALL", "False")
    os.environ.setdefault("YOLO_VERBOSE", "False")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from . import APP_NAME, __version__
    from .ui import theme

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("VisionModelInspector")
    family = theme.load_fonts()
    theme.FONT_FAMILY_ACTIVE = family
    app.setFont(theme.app_font(family))
    app.setStyle("Fusion")
    from .config import user_data_dir
    try:
        img_dir = theme.make_indicator_images(os.path.join(user_data_dir(), "ui"))
    except Exception:
        img_dir = ""
    app.setStyleSheet(theme.stylesheet(family, img_dir))
    return app


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from .selftest import run
        return run(args)
    from .config import setup_logging
    log_path = setup_logging()
    logging.getLogger(__name__).info("log file: %s", log_path)
    app = create_app(argv)
    from .ui.main_window import MainWindow
    from .ui.icons import icon
    w = MainWindow()
    w.setWindowIcon(icon("eye", "#5B3FD9", 64))
    app.setWindowIcon(icon("eye", "#5B3FD9", 64))
    w.resize(1600, 1000)
    screen = app.primaryScreen()
    if screen is not None:
        geo = screen.availableGeometry()
        if geo.width() < 1600 or geo.height() < 1000:
            w.showMaximized()
        else:
            w.show()
    else:
        w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
