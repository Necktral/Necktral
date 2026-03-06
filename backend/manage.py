#!/usr/bin/env python
"""Wrapper para ejecutar el manage.py real en backend/src.

Esto permite usar `python manage.py <command>` desde la raíz del módulo,
tal como lo documenta el repositorio.
"""

from __future__ import annotations

import runpy
from pathlib import Path
import sys


if __name__ == "__main__":
	root = Path(__file__).resolve().parent
	sys.path.insert(0, str(root / "src"))
	runpy.run_path(str(root / "src" / "manage.py"), run_name="__main__")
