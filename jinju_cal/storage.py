"""이 PC에만 저장. 다른 PC·웹과는 공유하지 않음.

저장 위치
  윈도우: %APPDATA%\\JinjuCal\\
  맥:     ~/Library/Application Support/JinjuCal/
파일
  settings.json  기준값·마지막 시세·창 크기 등
  products.json  저장한 상품 목록
  backups/       가져오기 직전 상품 목록 (최근 30개)
"""
from __future__ import annotations

import json
import os
import sys
import time

DIR_NAME = "JinjuCal"
KEEP_BACKUPS = 30


def data_dir() -> str:
    override = os.environ.get("JINJU_CAL_DATA")
    if override:
        d = override
    elif sys.platform == "win32":
        d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), DIR_NAME)
    elif sys.platform == "darwin":
        d = os.path.join(os.path.expanduser("~/Library/Application Support"), DIR_NAME)
    else:
        d = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), DIR_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def _read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        # 깨진 파일은 옆에 남겨 두고 기본값으로 시작
        try:
            os.replace(path, path + ".broken-" + time.strftime("%Y%m%d%H%M%S"))
        except OSError:
            pass
        return default


def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)  # 중간에 꺼져도 파일이 반쯤 써지지 않게


class Store:
    def __init__(self, root: str | None = None):
        self.root = root or data_dir()
        self.p_settings = os.path.join(self.root, "settings.json")
        self.p_products = os.path.join(self.root, "products.json")
        self.p_backups = os.path.join(self.root, "backups")

    # ---- 설정
    def settings(self) -> dict:
        s = _read(self.p_settings, {})
        return s if isinstance(s, dict) else {}

    def save_settings(self, s: dict):
        _write(self.p_settings, s)

    # ---- 상품
    def products(self) -> list[dict]:
        d = _read(self.p_products, [])
        if isinstance(d, dict):
            d = d.get("products", [])
        return [p for p in d if isinstance(p, dict) and p.get("kind") in ("k", "p") and p.get("code")] if isinstance(d, list) else []

    def save_products(self, lst: list[dict]):
        _write(self.p_products, {"format": 1, "products": lst})

    # 바꾸기 직전에 다시 읽어서 고침
    def upsert_product(self, np: dict) -> list[dict]:
        lst = self.products()
        for i, p in enumerate(lst):
            if p["kind"] == np["kind"] and p["code"] == np["code"]:
                lst[i] = np
                break
        else:
            lst.append(np)
        self.save_products(lst)
        return lst

    def remove_product(self, kind: str, code: str) -> list[dict]:
        lst = [p for p in self.products() if not (p["kind"] == kind and p["code"] == code)]
        self.save_products(lst)
        return lst

    # ---- 백업 (가져오기 전)
    def backup(self, label: str) -> str:
        os.makedirs(self.p_backups, exist_ok=True)
        name = time.strftime("%Y%m%d_%H%M%S") + "_" + label + ".json"
        path = os.path.join(self.p_backups, name)
        _write(path, {"label": label, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "products": self.products()})
        files = sorted(f for f in os.listdir(self.p_backups) if f.endswith(".json"))
        for f in files[:-KEEP_BACKUPS]:
            try:
                os.remove(os.path.join(self.p_backups, f))
            except OSError:
                pass
        return path

    def last_backup(self):
        try:
            files = sorted(f for f in os.listdir(self.p_backups) if f.endswith(".json"))
        except FileNotFoundError:
            return None
        if not files:
            return None
        path = os.path.join(self.p_backups, files[-1])
        d = _read(path, None)
        if not isinstance(d, dict) or not isinstance(d.get("products"), list):
            return None
        return path, d

    def restore_backup(self, path: str, d: dict):
        self.save_products(d["products"])
        os.replace(path, path[:-5] + ".restored")
