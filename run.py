"""PyInstaller 打包入口（exe）。"""
import sys

from app.main_gui import main

if __name__ == "__main__":
    sys.exit(main())
