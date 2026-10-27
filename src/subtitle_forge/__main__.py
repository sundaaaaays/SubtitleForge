# -*- coding: utf-8 -*-
"""支持 python -m subtitle_forge 启动。"""
import sys

from .ui.app import main

if __name__ == "__main__":
    sys.exit(main())
