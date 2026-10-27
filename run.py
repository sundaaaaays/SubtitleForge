# -*- coding: utf-8 -*-
"""开发环境启动入口：python run.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from subtitle_forge.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
