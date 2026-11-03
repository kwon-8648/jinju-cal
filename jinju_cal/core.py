"""계산 규칙 — 매장관리 웹(index.html)의 계산 부분을 그대로 옮김.

웹판은 자바스크립트라서 반올림(Math.round)과 숫자 해석(parseNum)이 파이썬 기본 동작과 다릅니다.
같은 입력이면 1원까지 같은 결과가 나오도록 자바스크립트 동작을 그대로 흉내 냅니다.
(tests/test_core.py 가 웹판 원본 코드와 무작위 입력 수천 개로 결과를 대조합니다.)
"""
from __future__ import annotations

import json
import math
import re

GPD = 3.75            # 1돈 = 3.75g
MAX_AMOUNT = 1e13
UNITS = [100, 1000, 10000]
KARAT_KEYS = ["10", "14", "18"]
COLORS = ["핑크", "옐로우", "화이트", "무도금"]
CATS = ["반지", "목걸이", "팔찌", "귀걸이", "펜던트", "발찌", "골드바", "기타"]

DEFAULTS = {
    "vat": "10", "p10": "41.7", "p14": "58.5", "p18": "75",
    "m10": "30", "m14": "30", "m18": "30",
    "ag": "3.75", "al": "50000", "dia": "", "set": "",
    "pg": "3.75", "pl": "50000", "ring": "", "white": "20000",
}


# ---------------------------------------------------------------- 자바스크립트 숫자 동작
def js_round(x: float) -> float:
    """자바스크립트 Math.round: 가장 가까운 정수, .5 는 +무한대 쪽으로."""
    if not math.isfinite(x):
        return x
    f = math.floor(x)
    return float(f + 1) if x - f >= 0.5 else float(f)


def parse_num(s, allow_blank: bool = False) -> tuple[float, bool]:
    """숫자와 '.'만 남김 (원본의 "0123456789." 필터). 빈칸은 allow_blank 일 때만 0."""
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


def ceil_unit(x: float, unit: float) -> float:
    """1e-6원 단위로 반올림해 부동소수점 잡음을 없앤 뒤 올림 단위로 올림."""
    if not unit > 0:
        unit = 100
    v = js_round(x * 1e6) / 1e6
    return math.ceil(v / unit) * unit


def base(price_incl: float, vat_pct: float) -> float:
    return price_incl / (1 + vat_pct / 100)


def karat(price_incl, vat_pct, grams, labor, dia, setting, purity_pct, margin_pct, unit):
    """금 원가 = 1돈(별도) × 중량/3.75 × 함량
    원가 = (금 + 공임 + 알값 + 셋팅비) × (1 + 부가세)
    판매가 = 올림(원가 ÷ (1 − 마진))"""
    if (not price_incl > 0 or not grams > 0 or labor < 0 or dia < 0 or setting < 0
            or not purity_pct > 0 or purity_pct > 100 or margin_pct < 0 or margin_pct >= 100
            or vat_pct < 0 or vat_pct > 100):
        return None
    v = vat_pct / 100
    gold = price_incl / (1 + v) * (grams / GPD) * (purity_pct / 100)
    cost = (gold + labor + dia + setting) * (1 + v)
    raw = cost / (1 - margin_pct / 100)
    if raw > MAX_AMOUNT:
        return None
    return {"gold": gold, "cost_incl": cost, "final": ceil_unit(raw, unit)}


def pure(price_incl, vat_pct, grams, ring, labor, unit):
    """G = 1돈(별도) × g/3.75 + 고리; 1배 = G + 2×공임; 2배 = G + 3×공임.
    부가세 포함가는 올림 전 별도가에서 계산."""
    if not price_incl > 0 or not grams > 0 or ring < 0 or labor < 0 or vat_pct < 0 or vat_pct > 100:
        return None
    v = vat_pct / 100
    g = price_incl / (1 + v) * grams / GPD + ring
    t1, t2 = g + 2 * labor, g + 3 * labor
    if t2 * (1 + v) > MAX_AMOUNT:
        return None
    return {"x1": ceil_unit(t1, unit), "i1": ceil_unit(t1 * (1 + v), unit),
            "x2": ceil_unit(t2, unit), "i2": ceil_unit(t2 * (1 + v), unit)}


def white_extra(color: str, white_text: str) -> int:
    """화이트골드 추가금 (색상이 화이트일 때만)."""
    if color != "화이트":
        return 0
    v, ok = parse_num(white_text, True)
    return int(js_round(v)) if ok and v > 0 else 0


def commas(x: float) -> str:
    n = int(js_round(x))
    neg = n < 0
    s = f"{abs(n):,}"
    return "-" + s if neg else s


def won(x: float) -> str:
    return commas(x) + " 원"


def fixed2(x: float) -> str:
    return f"{js_round(x * 100) / 100:.2f}"


# ---------------------------------------------------------------- 한국금거래소 응답 읽기
# /api/main 응답에서 officialPrice4 의 s_pure(내가 살 때)를 읽음
DATE_KEYS = ["date", "created_at", "createdAt", "reg_date", "regDate", "price_date", "dt"]
PRICE_URL = "https://www.koreagoldx.co.kr/api/main"
# 직접 조회가 막힐 때 쓰는 매장관리 웹의 서울 중계 (같은 응답을 그대로 전달)
PRICE_URLS = [PRICE_URL, "https://gold-cal.web.app/api/price"]
PRICE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.koreagoldx.co.kr/",
}


class QuoteError(Exception):
    pass


def _is_obj(v) -> bool:
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
        for k in list(n.keys()):
            if k == "data":
                continue
            v, p = _find_key(n[k], key, n, depth + 1)
            if v is not None:
                return v, p
    elif isinstance(n, list):
        for v in n:
            r, p = _find_key(v, key, n, depth + 1)
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


def _js_str(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (dict,)):
        return "[object Object]"
    if isinstance(v, list):
        return ",".join(_js_str(x) for x in v)
    return str(v)


def _first_date(m: dict) -> str:
    for k in DATE_KEYS:
        if k in m and m[k] is not None:
            v = m[k]
            if isinstance(v, str):
                if v.strip():
                    return v.strip()
            else:
                return _js_str(v)
    return ""


def parse_api(text: str) -> dict:
    """반환: {"buy": 살 때 시세(부가세 포함, 원/돈), "sell": 팔 때, "date": 제공일}"""
    try:
        root = json.loads(text)
    except Exception:
        raise QuoteError("응답을 읽을 수 없습니다")
    node, parent = _find_key(root, "officialPrice4", None, 0)
    if node is None:
        raise QuoteError("officialPrice4 항목이 없습니다")
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
            raise QuoteError("시세 값 형식이 올바르지 않습니다")
        if found and buy != q["buy"]:
            raise QuoteError("서로 다른 시세가 여러 개라 확인이 필요합니다")
        if not found:
            q["buy"] = buy
            s, sok = _price_value(r.get("p_pure"))
            if sok:
                q["sell"] = s
            q["date"] = _first_date(r)
        found = True
    if not found:
        raise QuoteError("살 때 시세(s_pure)가 없습니다")
    if q["sell"] > 0 and q["buy"] < q["sell"]:
        raise QuoteError("살 때/팔 때 시세 관계 확인이 필요합니다")
    if not q["date"] and _is_obj(parent):
        q["date"] = _first_date(parent)
    if not q["date"] and _is_obj(root):
        q["date"] = _first_date(root)
    return q


# ---------------------------------------------------------------- 검색 (초성 포함)
CHOSEONG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")


def initials(s: str) -> str:
    out = []
    for ch in s:
        c = ord(ch)
        out.append(CHOSEONG[(c - 0xAC00) // 588] if 0xAC00 <= c <= 0xD7A3 else ch)
    return "".join(out)


def match_product(query: str, code: str, name: str) -> bool:
    """대소문자·띄어쓰기 무시, 코드·이름·상호와 초성("ㄱㄹ" → 고리) 일치."""
    def norm(s):
        return "".join(s.lower().split())
    q = norm(query)
    if q == "":
        return True
    if q in norm(code + " " + name):
        return True
    return q in norm(initials(code + " " + name))


def product_label(p: dict) -> str:
    s = p["code"]
    if p.get("name"):
        s += "  ·  " + p["name"]
    if p.get("maker"):
        s += "  ·  " + p["maker"]
    return s + "  (" + p.get("weight", "") + "g)"


# ---------------------------------------------------------------- 상품 파일 (PC 프로그램·웹판과 호환)
PROD_HEADER = "#v2\tkind\tcode\tname\tweight\tlabor\tring\tdia\tset\tmaker"
PROD_FIELDS = ["kind", "code", "name", "weight", "labor", "ring", "dia", "set", "maker"]


def clean(s) -> str:
    return re.sub(r"[\t\r\n]", " ", "" if s is None else str(s)).strip()


def make_product(d: dict) -> dict:
    p = {k: clean(d.get(k, "")) for k in PROD_FIELDS}
    if d.get("cat") in CATS:
        p["cat"] = d["cat"]
    return p


def parse_products_tsv(text: str) -> list[dict]:
    out, v2 = [], False
    for line in text.lstrip("﻿").split("\n"):
        line = line.rstrip("\r")
        if line.startswith("#v2"):
            v2 = True
            continue
        p = line.split("\t")
        p += [""] * (10 - len(p))
        if p[0] not in ("k", "p"):
            continue
        if v2:
            pr = dict(kind=p[0], code=p[1], name=p[2], weight=p[3], labor=p[4], ring=p[5], dia=p[6], set=p[7], maker=p[8])
        else:  # 1.6 첫 형식
            pr = dict(kind=p[0], code=p[1], name=p[1], weight=p[2], labor=p[3], ring=p[4], dia="", set="", maker="")
        pr = {k: clean(v) for k, v in pr.items()}
        if not pr["code"]:
            continue
        out.append(pr)
    return out


def products_tsv(products: list[dict]) -> str:
    s = "﻿" + PROD_HEADER + "\n"
    for p in products:
        s += "\t".join(clean(p.get(k, "")) for k in PROD_FIELDS) + "\n"
    return s


def products_from_any(text: str) -> list[dict]:
    """상품목록 TSV, 매장관리 웹 전체 백업(JSON), 이 프로그램의 products.json 을 모두 받음."""
    head = text.lstrip("﻿").lstrip()
    if head.startswith("{") or head.startswith("["):
        try:
            d = json.loads(head)
        except Exception:
            return []
        lst = d.get("products") if isinstance(d, dict) else d
        if not isinstance(lst, list):
            return []
        out = []
        for x in lst:
            if isinstance(x, dict) and x.get("kind") in ("k", "p") and clean(x.get("code")):
                out.append(make_product(x))
        return out
    return parse_products_tsv(text)
