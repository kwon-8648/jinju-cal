"""화면 동작 확인 (화면 없이 실행): python tests/test_ui.py"""
import json
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from jinju_cal import core, ui  # noqa: E402
from jinju_cal.storage import Store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        fails.append(name)


answers = []  # yes_no 에 돌려줄 답
msgs = []
ui.MainWindow.yes_no = lambda self, t, m: (msgs.append(("q", t, m)), answers.pop(0) if answers else True)[1]
ui.MainWindow.info = lambda self, t, m: msgs.append(("i", t, m))


def new_window(root):
    st = Store(root)
    w = ui.MainWindow(st)
    w.show()
    return w


def typed(w, key, text):
    w.f[key].setText(text)
    w.f[key].textEdited.emit(text)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    root = tempfile.mkdtemp()
    Store(root).save_settings({"auto": "0"})
    w = new_window(root)
    app.setStyleSheet(ui.stylesheet(w.zoom))

    check("시세 없으면 '-'", w.o_p["p2i"].text() == "-" and w.k_rows["14"]["f"].text() == "-")
    w.i_price.setText("612,000")
    w.apply_manual()
    check("수동 시세", w.has_price and w.price == 612000 and w.o_incl.text() == "612,000 원")
    check("14K 기본값 판매가", w.k_rows["14"]["f"].text() == "590,100 원", w.k_rows["14"]["f"].text())
    check("순금 2배 포함", w.o_p["p2i"].text() == "777,000 원")

    typed(w, "ad", "2")
    check("돈→g 환산 표시", w.f["ag"].text() == "7.50" and w.ag_exact == 7.5)
    r = core.karat(612000, 10, 7.5, 50000, 0, 0, 58.5, 30, 100)
    check("돈 입력 계산", w.k_rows["14"]["f"].text() == core.won(r["final"]))
    typed(w, "ad", "1.333")
    exact = 1.333 * 3.75
    r = core.karat(612000, 10, exact, 50000, 0, 0, 58.5, 30, 100)
    check("돈 입력은 원래 값으로 계산", w.k_rows["14"]["f"].text() == core.won(r["final"]) and w.f["ag"].text() == "5.00")
    typed(w, "ag", "3.75")
    check("g→돈", w.f["ad"].text() == "1.00" and w.ag_exact is None)

    typed(w, "m14", "100")
    check("마진 100 → 빨간 칸", bool(w.f["m14"].property("invalid")) and w.k_rows["14"]["f"].text() == "입력 확인")
    typed(w, "m14", "30")
    check("고치면 빨간 칸 사라짐", not w.f["m14"].property("invalid"))

    w.k_color.setCurrentIndex(w.k_color.findData("화이트"))
    check("화이트 +20,000", w.k_rows["14"]["f"].text() == "610,100 원" and "화이트" in w.k_rows["14"]["s"].text())
    w.k_color.setCurrentIndex(0)

    w.unit.setCurrentIndex(1)
    check("1,000원 올림", w.k_rows["14"]["f"].text() == "591,000 원")
    w.unit.setCurrentIndex(0)

    w.showk["10"].setChecked(False)
    check("10K 숨김", not w.k_rows["10"]["f"].isVisibleTo(w) and w.k_rows["14"]["f"].isVisibleTo(w))
    w.showk["10"].setChecked(True)

    # 상품 저장 · 검색 · 불러오기 · 삭제
    w.k_prod.code.setText("R-101")
    w.k_prod.name.setText("고리 반지")
    w.k_prod.maker.setText("진주공방")
    typed(w, "al", "70000")
    typed(w, "dia", "120000")
    w.save_product("k")
    saved = Store(root).products()
    check("상품 저장 → 파일", len(saved) == 1 and saved[0]["labor"] == "70000" and saved[0]["dia"] == "120000")
    answers.append(False)
    w.save_product("k")
    check("같은 코드 다시 저장 → 확인 물음", msgs[-1][0] == "q" and "이미 있습니다" in msgs[-1][2])

    w.clear_section("k")
    check("초기화", w.f["ag"].text() == "" and w.k_prod.code.text() == "" and w.k_rows["14"]["f"].text() == "입력 확인")
    w.k_prod.q.setText("ㄱㄹ")
    w.k_prod.show_hits()
    check("초성 검색", list(w.k_prod.hits) == [core.product_label(saved[0])], list(w.k_prod.hits))
    w.k_prod._on_pick(list(w.k_prod.hits)[0])
    app.processEvents()
    check("검색 결과 불러오기", w.k_prod.code.text() == "R-101" and w.f["al"].text() == "70000" and w.f["ad"].text() == "1.00")
    r = core.karat(612000, 10, 3.75, 70000, 120000, 0, 58.5, 30, 100)
    check("불러온 값으로 계산", w.k_rows["14"]["f"].text() == core.won(r["final"]))
    w.k_prod.q.setText("없는말")
    w.k_prod.show_hits()
    check("없는 검색어", w.k_prod.model.stringList() == [])

    # 순금 상품
    w.p_prod.code.setText("G-1")
    typed(w, "pg", "")
    w.save_product("p")
    check("중량 없으면 저장 막음", msgs[-1][0] == "i" and "중량" in msgs[-1][2] and len(Store(root).products()) == 1)
    typed(w, "pg", "11.25")
    typed(w, "ring", "20000")
    w.save_product("p")
    check("순금 저장", len(Store(root).products()) == 2)

    # 설정 유지 (다시 열기)
    w.save_settings()
    w.close()
    w2 = new_window(root)
    check("다시 열어도 시세·입력 유지", w2.has_price and w2.price == 612000 and w2.f["pg"].text() == "11.25" and w2.f["pd"].text() == "3.00")
    check("다시 열어도 같은 계산", w2.o_p["p2i"].text() == w.o_p["p2i"].text())

    # 내보내기 · 가져오기 · 되돌리기
    out = os.path.join(root, "out.tsv")
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
    w2.export_products()
    txt = open(out, encoding="utf-8").read()
    check("내보내기 형식 (#v2, PC 프로그램 호환)", txt.startswith("﻿#v2\tkind") and "R-101\t고리 반지" in txt)
    web_backup = {"app": "매장관리 웹", "format": 2, "products": [
        {"kind": "k", "code": "R-101", "name": "고리 반지(웹)", "weight": "4", "labor": "60000", "ring": "", "dia": "", "set": "", "maker": "", "cat": "반지"},
        {"kind": "k", "code": "N-7", "name": "체인 목걸이", "weight": "5.2", "labor": "40000", "ring": "", "dia": "", "set": "", "maker": "A"}],
        "items": [], "records": []}
    bp = os.path.join(root, "web.json")
    json.dump(web_backup, open(bp, "w", encoding="utf-8"), ensure_ascii=False)
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (bp, ""))
    orig_exec = QMessageBox.exec
    QMessageBox.exec = lambda self: [b for b in self.buttons() if b.text() == "합치기"][0].click()
    w2.import_products()
    QMessageBox.exec = orig_exec
    pl = Store(root).products()
    check("웹 백업 가져오기 (합치기)", len(pl) == 3 and [p for p in pl if p["code"] == "R-101"][0]["name"] == "고리 반지(웹)", pl)
    check("가져오기 전 자동 백업", Store(root).last_backup() is not None)
    w2.undo_import()
    pl = Store(root).products()
    check("되돌리기", len(pl) == 2 and [p for p in pl if p["code"] == "R-101"][0]["name"] == "고리 반지")

    # 삭제
    w2.k_prod.code.setText("R-101")
    w2.delete_product("k")
    check("삭제", [p["code"] for p in Store(root).products()] == ["G-1"])

    # 시세 조회 실패 (이 테스트 환경은 인터넷이 막혀 있을 수 있음 → 실패 문구 확인 또는 성공)
    w2._fetched(None, "인터넷 연결 또는 서버 접속 실패")
    check("조회 실패 시 이전 시세 유지", w2.price == 612000 and "이전 시세 유지" in w2.o_status.text() and w2.o_status.property("bad"))
    w2._fetched({"buy": 630000.0, "sell": 0, "date": "2026.11.03"}, "")
    check("조회 성공 반영", w2.price == 630000 and "제공일 2026.11.03" in w2.o_status.text() and not w2.o_status.property("bad"))

    w2.set_zoom(+1)
    check("글자 크게", w2.zoom == 1.1)
    w2.set_zoom(-1)

    print(f"\n실패 {len(fails)}건" + (": " + ", ".join(fails) if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
