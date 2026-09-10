"""Raiz do case para os notebooks (cwd irrelevante)."""

from __future__ import annotations

import sys
from pathlib import Path


def case_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    return root


case_root()
