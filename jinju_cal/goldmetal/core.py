from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

APP_NAME = "OldTownMetalCalculator"
API_URLS = ("https://www.koreagoldx.co.kr/api/main",)  # kept for compatibility


@dataclass(frozen=True)
class RateItem:
    metal_type: str
    item_name: str
    multiplier: Decimal
    sort_order: int


# HAR의 /s1/api/metal_config 응답 기준
DIVISORS: Dict[str, Decimal] = {
    "GOLD": Decimal("3.7500"),
    "SILVER": Decimal("4.0300"),
    "PLATINUM": Decimal("1.0000"),
}

# HAR의 /s1/api/metal_rate_config 응답 기준 (19개)
RATE_ITEMS: List[RateItem] = [
    RateItem("GOLD", "24k골드바", Decimal("1.0000"), 1),
    RateItem("GOLD", "24k반지, 돌제품, 홀마크없는 메달, 주물메달, 무인검덩어리", Decimal("0.9940"), 2),
    RateItem("GOLD", "24열쇠, 동물, 목걸이, 팔찌 등 체인류, 뱃지", Decimal("0.9930"), 3),
    RateItem("GOLD", "24k무검제품/마고자/칠보류/단추", Decimal("0.9790"), 4),
    RateItem("GOLD", "통팔찌, 할로", Decimal("0.9600"), 5),
    RateItem("GOLD", "망사,칠보떨잠", Decimal("0.9500"), 6),
    RateItem("GOLD", "태국금", Decimal("0.9000"), 7),
    RateItem("GOLD", "18k", Decimal("0.7000"), 8),
    RateItem("GOLD", "14k", Decimal("0.5100"), 9),
    RateItem("GOLD", "12k", Decimal("0.4300"), 10),
    RateItem("GOLD", "10k/치금", Decimal("0.3500"), 11),
    RateItem("GOLD", "22k이글코인91.66%", Decimal("0.9100"), 12),
    RateItem("SILVER", "실버바", Decimal("1.0000"), 1),
    RateItem("SILVER", "99은수저", Decimal("0.9650"), 2),
    RateItem("SILVER", "90은수저", Decimal("0.9000"), 3),
    RateItem("SILVER", "80은수저", Decimal("0.7500"), 4),
    RateItem("SILVER", "70은수저", Decimal("0.6400"), 5),
    RateItem("SILVER", "실버제품, 실버주얼리, 기타실버92.5 제품", Decimal("0.8850"), 6),
    RateItem("SILVER", "50% 기타은제품", Decimal("0.4300"), 7),
]

METAL_DISPLAY = {
    "GOLD": "금 (1돈)",
    "SILVER": "고은",
    "PLATINUM": "백금",
}

# 이전 EXE 분석에서 확인된 한국금거래소 officialPrice4 키 체계.
# p_* = 거래소 매입(고객 '내가 팔 때') 값으로 우선 해석하며,
# s_*와 동시에 존재할 때 가격 관계를 교차검증해 방향 변경 가능.
API_ALIASES = {
    "GOLD": ("pure", "gold", "gold24k", "24k"),
    "SILVER": ("silver", "sil"),
    "PLATINUM": ("white", "platinum", "pt"),
}


def app_data_dir() -> Path:
    # Windows: %APPDATA%\OldTownMetalCalculator (the self-test also overrides APPDATA).
    # macOS:   ~/Library/Application Support/OldTownMetalCalculator
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path.home() / ".oldtown_metal_calculator"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return app_data_dir() / "last_state.json"


def record_path() -> Path:
    return app_data_dir() / "purchase_records.csv"


def log_path() -> Path:
    return app_data_dir() / "oldtown_metal.log"


def log(message: str) -> None:
    try:
        with log_path().open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")
    except Exception:
        pass


def parse_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip()
    if not text:
        return default
    text = text.replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return default
    try:
        return Decimal(m.group(0))
    except InvalidOperation:
        return default


def js_round(value: Any) -> int:
    """양수 금액에 대해 JavaScript Math.round()와 동일한 0자리 반올림."""
    d = parse_decimal(value)
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_unit_price(price_per_reference: Any, metal_type: str, multiplier: Any) -> int:
    price = parse_decimal(price_per_reference)
    divisor = DIVISORS[metal_type]
    mult = parse_decimal(multiplier)
    if divisor == 0:
        return 0
    return js_round(price / divisor * mult)


def calculate_row(unit_price: Any, input_weight: Any, deduction_weight: Any) -> Tuple[int, int]:
    unit = parse_decimal(unit_price)
    gross = max(parse_decimal(input_weight), Decimal("0"))
    deduct = max(parse_decimal(deduction_weight), Decimal("0"))
    deduction_price = js_round(unit * deduct)
    customer_price = js_round(max(Decimal("0"), unit * gross - unit * deduct))
    return deduction_price, customer_price


def build_rows(prices: Dict[str, Any], weights: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    weights = weights or {}
    rows: List[Dict[str, Any]] = []
    for idx, item in enumerate(RATE_ITEMS):
        price_ref = prices.get(item.metal_type, 0)
        unit_price = calculate_unit_price(price_ref, item.metal_type, item.multiplier)
        key = row_key(idx, item)
        w = weights.get(key, {})
        input_weight = w.get("input_weight", 0)
        deduction_weight = w.get("deduction_weight", 0)
        deduction_price, customer_price = calculate_row(unit_price, input_weight, deduction_weight)
        rows.append(
            {
                "key": key,
                "metal_type": item.metal_type,
                "item_name": item.item_name,
                "multiplier": str(item.multiplier),
                "divisor": str(DIVISORS[item.metal_type]),
                "unit_price": unit_price,
                "input_weight": str(input_weight or ""),
                "deduction_weight": str(deduction_weight or ""),
                "deduction_price": deduction_price,
                "customer_price": customer_price,
            }
        )
    return rows


def row_key(index: int, item: RateItem) -> str:
    return f"{index:02d}:{item.metal_type}:{item.item_name}"


def _walk(obj: Any) -> Iterable[Any]:
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _find_key_value(obj: Any, target_keys: Iterable[str]) -> Tuple[Optional[Any], Optional[str]]:
    targets = {k.lower() for k in target_keys}
    for node in _walk(obj):
        if not isinstance(node, dict):
            continue
        for k, v in node.items():
            if str(k).lower() in targets:
                return v, str(k)
    return None, None


def _find_named_block(obj: Any, name: str) -> Any:
    lname = name.lower()
    for node in _walk(obj):
        if not isinstance(node, dict):
            continue
        for k, v in node.items():
            if str(k).lower() == lname:
                return v
    return None


def _extract_pair(scope: Any, aliases: Iterable[str]) -> Tuple[Optional[Decimal], Optional[Decimal], Dict[str, Optional[str]]]:
    for alias in aliases:
        p_val, p_key = _find_key_value(scope, (f"p_{alias}", f"p{alias}", f"purchase_{alias}"))
        s_val, s_key = _find_key_value(scope, (f"s_{alias}", f"s{alias}", f"sell_{alias}"))
        p_num = parse_decimal(p_val) if p_val is not None else None
        s_num = parse_decimal(s_val) if s_val is not None else None
        if p_num is not None or s_num is not None:
            return p_num, s_num, {"p_key": p_key, "s_key": s_key, "alias": alias}

        # 일부 API는 품목 객체 안에 p/s 키로 제공할 수 있어 추가 대응.
        item_obj, item_key = _find_key_value(scope, (alias,))
        if isinstance(item_obj, dict):
            p_val2, p_key2 = _find_key_value(item_obj, ("p", "purchase", "buy", "customer_sell"))
            s_val2, s_key2 = _find_key_value(item_obj, ("s", "sell", "sale", "customer_buy"))
            p_num2 = parse_decimal(p_val2) if p_val2 is not None else None
            s_num2 = parse_decimal(s_val2) if s_val2 is not None else None
            if p_num2 is not None or s_num2 is not None:
                return p_num2, s_num2, {"p_key": p_key2, "s_key": s_key2, "alias": str(item_key)}
    return None, None, {"p_key": None, "s_key": None, "alias": None}


def _select_customer_sell_price(p_value: Optional[Decimal], s_value: Optional[Decimal]) -> Tuple[Optional[int], str]:
    """
    이전 코드 의미상 p_*를 고객 '내가 팔 때'로 우선 사용한다.
    단, p와 s가 모두 있고 p > s이면 '내가 살 때(VAT포함)'가 보통 더 높다는
    가격 관계에 따라 낮은 값을 고객 매도가로 자동 선택해 키 방향 변경에도 대응한다.
    """
    positives = [v for v in (p_value, s_value) if v is not None and v > 0]
    if not positives:
        return None, "missing"
    if p_value is not None and p_value > 0 and s_value is not None and s_value > 0:
        if p_value <= s_value:
            return js_round(p_value), "p"
        return js_round(s_value), "s(auto-swap)"
    if p_value is not None and p_value > 0:
        return js_round(p_value), "p-only"
    return js_round(s_value), "s-only"


def parse_koreagoldx_prices(payload: Any) -> Tuple[Dict[str, int], Dict[str, Any]]:
    block = _find_named_block(payload, "officialPrice4")
    scopes = [block, payload] if block is not None else [payload]

    prices: Dict[str, int] = {}
    details: Dict[str, Any] = {"officialPrice4_found": block is not None, "metals": {}}

    for metal, aliases in API_ALIASES.items():
        p_val = s_val = None
        keys: Dict[str, Optional[str]] = {"p_key": None, "s_key": None, "alias": None}
        for scope in scopes:
            p_val, s_val, keys = _extract_pair(scope, aliases)
            if p_val is not None or s_val is not None:
                break
        chosen, direction = _select_customer_sell_price(p_val, s_val)
        details["metals"][metal] = {
            "p": str(p_val) if p_val is not None else None,
            "s": str(s_val) if s_val is not None else None,
            "chosen_direction": direction,
            **keys,
        }
        if chosen is not None:
            prices[metal] = chosen

    # 날짜/시각 필드가 있으면 최대한 추출 (없으면 호출 시각 사용)
    date_val, date_key = _find_key_value(payload, ("date", "price_date", "regdate", "wdate", "updated_at", "update_date"))
    details["source_date"] = str(date_val) if date_val is not None else None
    details["source_date_key"] = date_key
    return prices, details


HOME_URL = "https://www.koreagoldx.co.kr/"
MAIN_API = "https://www.koreagoldx.co.kr/api/main"


def _csrf_token(session: "requests.Session", timeout: int) -> Optional[str]:
    """홈페이지의 <meta name="csrf-token"> 값을 읽는다 (POST가 403일 때만 사용)."""
    response = session.get(HOME_URL, timeout=timeout, headers={"Accept": "text/html,*/*"})
    match = re.search(r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)', response.text)
    if not match:
        match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']csrf-token', response.text)
    return match.group(1) if match else None


def fetch_koreagoldx_prices(timeout: int = 10) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """한국금거래소 시세 조회.

    2026-10 사이트 변경: /api/main 은 GET이면 405, X-Requested-With 없는 POST는 403.
    홈페이지(jQuery $.ajax type:'post')와 같은 방식으로 요청한다. 응답 형식(officialPrice4)은 동일.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": HOME_URL,
        "Origin": "https://www.koreagoldx.co.kr",
        "X-Requested-With": "XMLHttpRequest",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    errors: List[str] = []
    session = requests.Session()
    session.headers.update(headers)

    def attempt(label: str, send) -> Tuple[Dict[str, int], Dict[str, Any]]:
        response = send()
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}")
        payload = response.json()
        prices, details = parse_koreagoldx_prices(payload)
        details.update({
            "url": response.url,
            "method": label,
            "http_status": response.status_code,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        })
        if not prices:
            raise RuntimeError("응답에서 시세 필드를 찾지 못했습니다.")
        log(f"API success {details}; prices={prices}")
        return prices, details

    form = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
    steps = [
        ("POST", lambda: session.post(MAIN_API, timeout=timeout, headers=form, data="")),
        ("POST+CSRF", lambda: session.post(MAIN_API, timeout=timeout, data="",
            headers={**form, "X-CSRF-Token": _csrf_token(session, timeout) or ""})),
        ("GET(legacy)", lambda: session.get(MAIN_API, timeout=timeout, params={"_": int(time.time())})),
    ]
    for label, send in steps:
        try:
            return attempt(label, send)
        except Exception as exc:
            msg = f"{label} {MAIN_API}: {exc}"
            errors.append(msg)
            log(f"API failure {msg}")

    raise RuntimeError(" / ".join(errors))


def default_state() -> Dict[str, Any]:
    return {
        "prices": {"GOLD": 0, "SILVER": 0, "PLATINUM": 0},
        "price_source": "미조회",
        "price_updated_at": None,
        "multipliers": {},
        "weights": {},
        "window_geometry": None,
    }


def load_state() -> Dict[str, Any]:
    path = state_path()
    state = default_state()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state.update(loaded)
                state["prices"] = {**default_state()["prices"], **(loaded.get("prices") or {})}
    except Exception as exc:
        log(f"state load failure: {exc}")
    return state


def save_state(state: Dict[str, Any]) -> None:
    path = state_path()
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        log(f"state save failure: {exc}")
        raise


def append_purchase_record(rows: List[Dict[str, Any]], prices: Dict[str, Any], source: str, total: int) -> Path:
    path = record_path()
    new_file = not path.exists()
    timestamp = datetime.now().isoformat(timespec="seconds")
    fieldnames = [
        "timestamp", "source", "gold_price", "silver_price", "platinum_price",
        "metal_type", "item_name", "unit_price", "input_weight", "deduction_weight",
        "deduction_price", "customer_price", "total_customer_price",
    ]
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            writer.writeheader()
        saved_any = False
        for row in rows:
            gross = parse_decimal(row.get("input_weight"))
            deduct = parse_decimal(row.get("deduction_weight"))
            if gross == 0 and deduct == 0:
                continue
            saved_any = True
            writer.writerow({
                "timestamp": timestamp,
                "source": source,
                "gold_price": prices.get("GOLD", 0),
                "silver_price": prices.get("SILVER", 0),
                "platinum_price": prices.get("PLATINUM", 0),
                "metal_type": row["metal_type"],
                "item_name": row["item_name"],
                "unit_price": row["unit_price"],
                "input_weight": row.get("input_weight", ""),
                "deduction_weight": row.get("deduction_weight", ""),
                "deduction_price": row["deduction_price"],
                "customer_price": row["customer_price"],
                "total_customer_price": total,
            })
        if not saved_any:
            writer.writerow({
                "timestamp": timestamp,
                "source": source,
                "gold_price": prices.get("GOLD", 0),
                "silver_price": prices.get("SILVER", 0),
                "platinum_price": prices.get("PLATINUM", 0),
                "metal_type": "",
                "item_name": "(중량 입력 없음)",
                "unit_price": "",
                "input_weight": "",
                "deduction_weight": "",
                "deduction_price": 0,
                "customer_price": 0,
                "total_customer_price": total,
            })
    return path
