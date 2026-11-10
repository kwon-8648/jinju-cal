"""설정 저장 — 이 PC에만 저장 (온라인 공유 없음).

Windows: %APPDATA%\\JinjuCal\\settings.json
macOS:   ~/Library/Application Support/JinjuCal/settings.json
(1.0.0 과 같은 폴더·같은 이름이라 예전 기준값과 마지막 시세를 그대로 이어 씀)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULTS = {
    "vat": "10", "p10": "41.7", "p14": "58.5", "p18": "75",
    "m10": "30", "m14": "30", "m18": "30",
    "ag": "3.75", "al": "50000", "dia": "", "set": "",
    "pg": "3.75", "pl": "50000", "ring": "", "white": "20000", "pm": "2",
}
FIELDS = list(DEFAULTS.keys())


def data_dir() -> Path:
    override = os.environ.get("JINJU_CAL_DATA")
    if override:
        return Path(override)
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "JinjuCal"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "JinjuCal"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "JinjuCal"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def load() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(d: dict) -> bool:
    p = settings_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)  # 저장 중 꺼져도 이전 파일이 깨지지 않게
        return True
    except Exception:
        return False
