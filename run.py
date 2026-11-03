"""PyInstaller 打包入口（exe）。"""
import sys

from app.ui.main_window import main

if __name__ == "__main__":
    sys.exit(main())
