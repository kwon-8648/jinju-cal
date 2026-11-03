// 매장관리 웹 index.html 의 계산 부분 원본 (비교 테스트용, 고치지 말 것)
const GPD = 3.75;           // 1돈 = 3.75g
const MAX_AMOUNT = 1e13;
const UNITS = [100, 1000, 10000];

// 숫자와 '.'만 남김 (원본의 "0123456789." 필터). 빈칸은 allowBlank일 때만 0.
function parseNum(s, allowBlank) {
  const t = String(s == null ? "" : s).replace(/[^0-9.]/g, "");
  if (t === "") return [0, !!allowBlank];
  if ((t.match(/\./g) || []).length > 1 || t === ".") return [0, false];
  const v = Number(t);
  if (!isFinite(v)) return [0, false];
  return [v, true];
}
// 1e-6원 단위로 반올림해 부동소수점 잡음을 없앤 뒤 올림 단위로 올림
function ceilUnit(x, unit) {
  if (!(unit > 0)) unit = 100;
  const v = Math.round(x * 1e6) / 1e6;
  return Math.ceil(v / unit) * unit;
}
function base(priceIncl, vatPct) { return priceIncl / (1 + vatPct / 100); }
// 금 원가 = 1돈(별도) × 중량/3.75 × 함량, 원가 = (금+공임+알값+셋팅비)×(1+부가세), 판매가 = 올림(원가 ÷ (1−마진))
function karat(priceIncl, vatPct, grams, labor, dia, set, purityPct, marginPct, unit) {
  if (!(priceIncl > 0) || !(grams > 0) || labor < 0 || dia < 0 || set < 0 || !(purityPct > 0) || purityPct > 100 ||
      marginPct < 0 || marginPct >= 100 || vatPct < 0 || vatPct > 100) return null;
  const v = vatPct / 100;
  const gold = priceIncl / (1 + v) * (grams / GPD) * (purityPct / 100);
  const cost = (gold + labor + dia + set) * (1 + v);
  const raw = cost / (1 - marginPct / 100);
  if (raw > MAX_AMOUNT) return null;
  return { gold, costIncl: cost, final: ceilUnit(raw, unit) };
}
// G = 1돈(별도) × g/3.75 + 고리; 1배 = G + 2×공임; 2배 = G + 3×공임. 포함가는 올림 전 별도가에서 계산.
function pure(priceIncl, vatPct, grams, ring, labor, unit) {
  if (!(priceIncl > 0) || !(grams > 0) || ring < 0 || labor < 0 || vatPct < 0 || vatPct > 100) return null;
  const v = vatPct / 100;
  const g = priceIncl / (1 + v) * grams / GPD + ring;
  const t1 = g + 2 * labor, t2 = g + 3 * labor;
  if (t2 * (1 + v) > MAX_AMOUNT) return null;
  return { x1: ceilUnit(t1, unit), i1: ceilUnit(t1 * (1 + v), unit), x2: ceilUnit(t2, unit), i2: ceilUnit(t2 * (1 + v), unit) };
}
function commas(x) {
  let n = Math.round(x); const neg = n < 0; if (neg) n = -n;
  const s = String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return neg ? "-" + s : s;
}
const won = x => commas(x) + " 원";
const fixed2 = x => (Math.round(x * 100) / 100).toFixed(2);

// 한국금거래소 /api/main 응답에서 officialPrice4 의 s_pure(살 때)를 읽음
const DATE_KEYS = ["date", "created_at", "createdAt", "reg_date", "regDate", "price_date", "dt"];
function parseAPI(text) {
  let root;
  try { root = JSON.parse(text); } catch (e) { throw new Error("응답을 읽을 수 없습니다"); }
  const [node, parent] = findKey(root, "officialPrice4", null, 0);
  if (node == null) throw new Error("officialPrice4 항목이 없습니다");
  const recs = [];
  if (Array.isArray(node)) node.forEach(e => { if (isObj(e)) recs.push(e); });
  else if (isObj(node)) {
    if ("s_pure" in node) recs.push(node);
    else Object.values(node).forEach(e => { if (isObj(e)) recs.push(e); });
  }
  const q = { buy: 0, sell: 0, date: "" }; let found = false;
  for (const r of recs) {
    if (!("s_pure" in r)) continue;
    const [buy, ok] = priceValue(r.s_pure);
    if (!ok) throw new Error("시세 값 형식이 올바르지 않습니다");
    if (found && buy !== q.buy) throw new Error("서로 다른 시세가 여러 개라 확인이 필요합니다");
    if (!found) { q.buy = buy; const [s, sok] = priceValue(r.p_pure); if (sok) q.sell = s; q.date = firstDate(r); }
    found = true;
  }
  if (!found) throw new Error("살 때 시세(s_pure)가 없습니다");
  if (q.sell > 0 && q.buy < q.sell) throw new Error("살 때/팔 때 시세 관계 확인이 필요합니다");
  if (!q.date && isObj(parent)) q.date = firstDate(parent);
  if (!q.date && isObj(root)) q.date = firstDate(root);
  return q;
}
function isObj(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }
function findKey(n, key, parent, depth) {
  if (depth > 6) return [null, null];
  if (isObj(n)) {
    if (key in n) return [n[key], n];
    if ("data" in n) { const [v, p] = findKey(n.data, key, n, depth + 1); if (v != null) return [v, p]; }
    for (const k of Object.keys(n)) { if (k === "data") continue; const [v, p] = findKey(n[k], key, n, depth + 1); if (v != null) return [v, p]; }
  } else if (Array.isArray(n)) {
    for (const v of n) { const [r, p] = findKey(v, key, n, depth + 1); if (r != null) return [r, p]; }
  }
  return [null, null];
}
function priceValue(v) {
  if (typeof v === "number") return [v, v > 0];
  if (typeof v === "string") { const [f, ok] = parseNum(v, false); return [f, ok && f > 0]; }
  return [0, false];
}
function firstDate(m) {
  for (const k of DATE_KEYS) {
    if (k in m && m[k] != null) {
      const v = m[k];
      if (typeof v === "string") { if (v.trim()) return v.trim(); }
      else return String(v);
    }
  }
  return "";
}

// 검색: 대소문자·띄어쓰기 무시, 코드·이름·상호와 초성("ㄱㄹ" → 고리) 일치
const CHOSEONG = [..."ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"];
function initials(s) {
  let out = "";
  for (const ch of s) { const c = ch.codePointAt(0); out += (c >= 0xAC00 && c <= 0xD7A3) ? CHOSEONG[Math.floor((c - 0xAC00) / 588)] : ch; }
  return out;
}
function matchProduct(query, code, name) {
  const norm = s => s.toLowerCase().split(/\s+/).join("");
  const q = norm(query);
  if (q === "") return true;
  if (norm(code + " " + name).includes(q)) return true;
  return norm(initials(code + " " + name)).includes(q);
}
module.exports = { parseNum, ceilUnit, base, karat, pure, commas, fixed2, parseAPI, initials, matchProduct };
