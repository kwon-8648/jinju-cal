"""계산 규칙 — 매장관리 웹(상품가격계산기 2.6) 계산기 탭의 계산식을 그대로 옮김.

웹판(JavaScript)과 같은 IEEE 754 배정밀도 실수로, 같은 순서로 계산해 1원까지 같은 결과를 냄.
JavaScript Math.round 는 0.5 를 위쪽(+무한대 쪽)으로 올리므로 js_round 로 맞춤.
"""
from __future__ import annotations

import json
import math
import re

GPD = 3.75  # 1돈 = 3.75g
MAX_AMOUNT = 1e13
UNITS = [100, 1000, 10000]  # 판매가 올림 단위


def js_round(x: float) -> float:
    """JavaScript Math.round 와 같음 (0.5 는 위로)."""
    return math.floor(x + 0.5)


def parse_num(s, allow_blank: bool = False):
    """숫자와 '.'만 남김 (원본의 "0123456789." 필터). 빈칸은 allow_blank 일 때만 0.
    돌려주는 값: (값, 올바른지)"""
    t = re.sub(r"[^0-9.]", "", "" if s is None else str(s))
    if t == "":
        return 0.0, bool(allow_blank)
    if t.count(".") > 1 or t == ".":
        return 0.0, False
    try:
        v = float(t)
    except ValueError:
        return 0.0, False
    if not math.isfinite(v):
        return 0.0, False
    return v, True


def ceil_unit(x: float, unit: int) -> float:
    """1e-6원 단위로 반올림해 부동소수점 잡음을 없앤 뒤 올림 단위로 올림."""
    if not unit > 0:
        unit = 100
    v = js_round(x * 1e6) / 1e6
    return math.ceil(v / unit) * unit


def base(price_incl: float, vat_pct: float) -> float:
    """부가세 별도 1돈 가격."""
    return price_incl / (1 + vat_pct / 100)


def karat(price_incl, vat_pct, grams, labor, dia, setting, purity_pct, margin_pct, unit):
    """10K·14K·18K.
    금 원가 = 1돈(별도) × 중량/3.75 × 함량
    원가 = (금 + 공임 + 알값 + 셋팅비) × (1 + 부가세)
    판매가 = 올림(원가 ÷ (1 − 마진))
    계산할 수 없으면 None."""
    if (not price_incl > 0 or not grams > 0 or labor < 0 or dia < 0 or setting < 0
            or not purity_pct > 0 or purity_pct > 100
            or margin_pct < 0 or margin_pct >= 100 or vat_pct < 0 or vat_pct > 100):
        return None
    v = vat_pct / 100
    gold = price_incl / (1 + v) * (grams / GPD) * (purity_pct / 100)
    cost = (gold + labor + dia + setting) * (1 + v)
    raw = cost / (1 - margin_pct / 100)
    if raw > MAX_AMOUNT:
        return None
    return {"gold": gold, "cost_incl": cost, "final": ceil_unit(raw, unit)}


def karat_excl(price_incl, vat_pct, grams, labor, dia, setting, purity_pct, margin_pct, unit, white=0):
    """10K·14K·18K 판매가 · 부가세 별도.
    판매가 = 올림((금 + 공임 + 알값 + 셋팅비) ÷ (1 − 마진)) + 화이트 추가금
    화이트 추가금은 부가세와 상관없이 최종 판매가에 그대로 더함 (포함 판매가에도 같은 금액). 계산할 수 없으면 None."""
    r = karat(price_incl, vat_pct, grams, labor, dia, setting, purity_pct, margin_pct, unit)
    if r is None or white < 0:
        return None
    v = vat_pct / 100
    gold = price_incl / (1 + v) * (grams / GPD) * (purity_pct / 100)
    return ceil_unit((gold + labor + dia + setting) / (1 - margin_pct / 100), unit) + white


def pure(price_incl, vat_pct, grams, ring, labor, unit):
    """순금. G = 1돈(별도) × g/3.75 + 고리; 1배 = G + 2×공임; 2배 = G + 3×공임.
    부가세 포함가는 올림 전 별도가에서 계산. 계산할 수 없으면 None."""
    if not price_incl > 0 or not grams > 0 or ring < 0 or labor < 0 or vat_pct < 0 or vat_pct > 100:
        return None
    v = vat_pct / 100
    g = price_incl / (1 + v) * grams / GPD + ring
    t1 = g + 2 * labor
    t2 = g + 3 * labor
    if t2 * (1 + v) > MAX_AMOUNT:
        return None
    return {"x1": ceil_unit(t1, unit), "i1": ceil_unit(t1 * (1 + v), unit),
            "x2": ceil_unit(t2, unit), "i2": ceil_unit(t2 * (1 + v), unit)}


def commas(x) -> str:
    n = int(js_round(x))
    neg = n < 0
    s = f"{abs(n):,}"
    return "-" + s if neg else s


def won(x) -> str:
    return commas(x) + " 원"


def fixed2(x) -> str:
    """소수 2자리 표시 (JavaScript (Math.round(x*100)/100).toFixed(2) 와 같게)."""
    return f"{js_round(x * 100) / 100:.2f}"


# ---------------------------------------------------------------------------
# 한국금거래소 /api/main 응답에서 officialPrice4 의 s_pure(내가 살 때)를 읽음
# ---------------------------------------------------------------------------
DATE_KEYS = ["date", "created_at", "createdAt", "reg_date", "regDate", "price_date", "dt"]


class PriceError(Exception):
    pass


def _is_obj(v):
    return isinstance(v, dict)


def _find_key(n, key, parent, depth):
    if depth > 6:
        return None, None
    if _is_obj(n):
        if key in n:
            return n[key], n
        if "data" in n:
            v, p = _find_key(n["data"], key, n, depth + 1)
            if v is not None:
                return v, p
        for k, child in n.items():
            if k == "data":
                continue
            v, p = _find_key(child, key, n, depth + 1)
            if v is not None:
                return v, p
    elif isinstance(n, list):
        for child in n:
            r, p = _find_key(child, key, n, depth + 1)
            if r is not None:
                return r, p
    return None, None


def _price_value(v):
    if isinstance(v, bool):
        return 0.0, False
    if isinstance(v, (int, float)):
        return float(v), v > 0
    if isinstance(v, str):
        f, ok = parse_num(v, False)
        return f, ok and f > 0
    return 0.0, False


def _first_date(m):
    for k in DATE_KEYS:
        if k in m and m[k] is not None:
            v = m[k]
            if isinstance(v, str):
                if v.strip():
                    return v.strip()
            else:
                return str(v)
    return ""


def parse_api(text: str):
    """돌려주는 값: {"buy": 살 때, "sell": 팔 때(없으면 0), "date": 제공일}"""
    try:
        root = json.loads(text)
    except Exception:
        raise PriceError("응답을 읽을 수 없습니다")
    node, parent = _find_key(root, "officialPrice4", None, 0)
    if node is None:
        raise PriceError("officialPrice4 항목이 없습니다")
    recs = []
    if isinstance(node, list):
        recs = [e for e in node if _is_obj(e)]
    elif _is_obj(node):
        if "s_pure" in node:
            recs.append(node)
        else:
            recs = [e for e in node.values() if _is_obj(e)]
    q = {"buy": 0.0, "sell": 0.0, "date": ""}
    found = False
    for r in recs:
        if "s_pure" not in r:
            continue
        buy, ok = _price_value(r["s_pure"])
        if not ok:
            raise PriceError("시세 값 형식이 올바르지 않습니다")
        if found and buy != q["buy"]:
            raise PriceError("서로 다른 시세가 여러 개라 확인이 필요합니다")
        if not found:
            q["buy"] = buy
            s, sok = _price_value(r.get("p_pure"))
            if sok:
                q["sell"] = s
            q["date"] = _first_date(r)
        found = True
    if not found:
        raise PriceError("살 때 시세(s_pure)가 없습니다")
    if q["sell"] > 0 and q["buy"] < q["sell"]:
        raise PriceError("살 때/팔 때 시세 관계 확인이 필요합니다")
    if not q["date"] and _is_obj(parent):
        q["date"] = _first_date(parent)
    if not q["date"] and _is_obj(root):
        q["date"] = _first_date(root)
    return q
