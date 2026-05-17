"""pytest 공통 fixture / sys.path 설정."""
from __future__ import annotations

import sys
from pathlib import Path

# scripts/ 를 sys.path 에 추가 (F3 §2.7 SIG 정합)
_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
