"""웹판 원본 계산 코드(tests/web_reference.js)와 결과를 대조.

    python tests/test_core.py        (node 가 있어야 함)
"""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from jinju_cal import core  # noqa: E402

NODE = r"""
const w = require(process.argv[1]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(c => {
  try {
    if (c.f === 'parseNum') return w.parseNum(c.a[0], c.a[1]);
    if (c.f === 'parseAPI') { try { return w.parseAPI(c.a[0]); } catch (e) { return { err: e.message }; } }
    return w[c.f](...c.a);
  } catch (e) { return { thrown: e.message }; }
});
process.stdout.write(JSON.stringify(out));
"""


def run_js(cases):
    r = subprocess.run(["node", "-e", NODE, os.path.join(HERE, "web_reference.js")],
                       input=json.dumps(cases), capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def py_call(c):
    f, a = c["f"], c["a"]
    if f == "parseNum":
        v, ok = core.parse_num(a[0], a[1])
        return [v, ok]
    if f == "ceilUnit":
        return core.ceil_unit(*a)
    if f == "karat":
        r = core.karat(*a)
        return None if r is None else {"gold": r["gold"], "costIncl": r["cost_incl"], "final": r["final"]}
    if f == "pure":
        return core.pure(*a)
    if f == "commas":
        return core.commas(*a)
    if f == "fixed2":
        return core.fixed2(*a)
    if f == "parseAPI":
        try:
            return core.parse_api(a[0])
        except core.PriceError as e:
            return {"err": str(e)}
    raise ValueError(f)


def same(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return a == b  # 완전히 같아야 함 (1원, 소수점까지)
    return a == b


def gen(rnd, n):
    cases = []
    prices = [612000, 598000, 600000, 455000, 1, 999999, 650500]
    for _ in range(n):
        P = rnd.choice(prices + [rnd.randint(1, 2_000_000), rnd.uniform(1, 2e6)])
        vat = rnd.choice([10, 0, 10, 5.5, 100, rnd.uniform(0, 100)])
        g = rnd.choice([3.75, 1, 0.01, 2.5, 11.25, rnd.uniform(0.01, 200), round(rnd.uniform(0.1, 50), 2), 0, 1.3333333])
        labor = rnd.choice([50000, 0, 30000, rnd.randint(0, 500000), rnd.uniform(0, 1e5)])
        dia = rnd.choice([0, 0, 120000, rnd.randint(0, 1_000_000)])
        st = rnd.choice([0, 0, 15000, rnd.randint(0, 100000)])
        pct = rnd.choice([41.7, 58.5, 75, 100, rnd.uniform(0.1, 100)])
        m = rnd.choice([30, 0, 25, 99.99, rnd.uniform(0, 99.9)])
        unit = rnd.choice(core.UNITS)
        cases.append({"f": "karat", "a": [P, vat, g, labor, dia, st, pct, m, unit]})
        cases.append({"f": "pure", "a": [P, vat, g, rnd.choice([0, 0, 20000, rnd.randint(0, 99999)]), labor, unit]})
        x = rnd.choice([rnd.uniform(-1e7, 1e7), rnd.randint(0, 10**9) + 0.5, rnd.randint(0, 10**7) / 100, -2.5, 0.5, 1.5])
        cases.append({"f": "commas", "a": [x]})
        cases.append({"f": "fixed2", "a": [rnd.uniform(0, 100)]})
        cases.append({"f": "ceilUnit", "a": [rnd.uniform(0, 1e8), unit]})
    for s in ["", "12,345", "1.2.3", ".", "5.", ".5", "abc", "3.75g", "  612,000원 ", "１２", "0", "1e5", "-30", None, "00012"]:
        for ab in (True, False):
            cases.append({"f": "parseNum", "a": [s, ab]})
    apis = [
        {"data": {"officialPrice4": {"s_pure": "612,000", "p_pure": 530000, "date": "2026-11-03"}}},
        {"officialPrice4": [{"s_pure": 612000, "p_pure": "530,000", "regDate": 20261103}]},
        {"data": {"officialPrice4": {"a": {"s_pure": 600000}, "b": {"s_pure": 600000}}}, "date": "x"},
        {"data": {"officialPrice4": {"a": {"s_pure": 600000}, "b": {"s_pure": 610000}}}},
        {"data": {"officialPrice4": {"s_pure": 500000, "p_pure": 600000}}},
        {"data": {"other": 1}},
        {"data": {"officialPrice4": {"s_pure": "abc"}}},
        {"data": {"officialPrice4": {"p_pure": 1}}},
    ]
    for a in apis:
        cases.append({"f": "parseAPI", "a": [json.dumps(a, ensure_ascii=False)]})
    cases.append({"f": "parseAPI", "a": ["not json"]})
    return cases


def main():
    rnd = random.Random(20261103)
    cases = gen(rnd, 4000)
    js = run_js(cases)
    bad = 0
    for c, j in zip(cases, js):
        p = py_call(c)
        if not same(p, j):
            bad += 1
            if bad <= 15:
                print("DIFF", c, "\n  py:", p, "\n  js:", j)
    print(f"{len(cases)}건 대조, 다른 결과 {bad}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
