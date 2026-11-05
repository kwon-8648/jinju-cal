"""업데이트 동작 확인 (가짜 GitHub 서버): python tests/test_update.py"""
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from jinju_cal import update  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        fails.append(name)


BLOB = os.urandom(700_000)
REL = {"tag": "v9.9.9", "digest": "sha256:" + hashlib.sha256(BLOB).hexdigest(), "size": len(BLOB), "cut": False}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        if self.path == "/latest":
            body = json.dumps({"tag_name": REL["tag"], "assets": [
                {"name": f"jinju-cal-{REL['tag'][1:]}-mac.dmg", "size": REL["size"], "digest": REL["digest"], "browser_download_url": base + "/dl/mac"},
                {"name": f"jinju-cal-{REL['tag'][1:]}-windows.exe", "size": REL["size"], "browser_download_url": base + "/dl/win"},
            ]}).encode()
        elif self.path == "/dl/mac" or self.path == "/dl/win":
            self.send_response(302)  # GitHub 처럼 다른 주소로 넘겨줌
            self.send_header("Location", "/files" + self.path[3:])
            self.end_headers()
            return
        elif self.path.startswith("/files/"):
            body = BLOB[: len(BLOB) // 2] if REL["cut"] else BLOB
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
API = f"http://127.0.0.1:{srv.server_port}/latest"

# ---------------------------------------------------------------- 버전 비교·확인
check("버전 비교", update.parse_version("v1.10.0") > update.parse_version("1.9.9") and update.parse_version("v1.1.1") == (1, 1, 1))
info = update.check(API, current="1.1.1", platform="darwin")
check("새 버전 있음 (맥 dmg)", info and info["version"] == "9.9.9" and info["name"].endswith("-mac.dmg"), info)
info_w = update.check(API, current="1.1.1", platform="win32")
check("새 버전 있음 (윈도우 exe)", info_w and info_w["name"].endswith("-windows.exe"), info_w)
check("같은 버전이면 없음", update.check(API, current="9.9.9", platform="darwin") is None)
check("더 새 버전을 쓰면 없음", update.check(API, current="10.0.0", platform="darwin") is None)
try:
    update.check(API, current="1.0.0", platform="linux")
    check("이 컴퓨터용 파일 없음", False)
except update.UpdateError as e:
    check("이 컴퓨터용 파일 없음", "이 컴퓨터용 파일이 없습니다" in str(e), e)
try:
    update.check("http://127.0.0.1:1/x", current="1.0.0", platform="darwin")
    check("접속 실패", False)
except update.UpdateError as e:
    check("접속 실패 문구", bool(str(e)), e)

# ---------------------------------------------------------------- 받기
tmp = Path(tempfile.mkdtemp())
seen = []
f = update.download(info, tmp, progress=lambda g, t: seen.append((g, t)))
check("받기 (넘겨주기 따라감, 크기·sha256 확인)", f.read_bytes() == BLOB and not list(tmp.glob("*.part")), f)
check("진행 표시", seen and seen[-1] == (len(BLOB), len(BLOB)), seen[-1:] if seen else seen)
REL["cut"] = True
try:
    (tmp / "x").mkdir()
    update.download(info, tmp / "x")
    check("덜 받으면 실패", False)
except update.UpdateError as e:
    check("덜 받으면 실패 (반쯤 받은 파일은 지움)", "다 받지 못했습니다" in str(e) and not list((tmp / "x").glob("*")), e)
REL["cut"] = False
bad = dict(info, digest="sha256:" + "0" * 64)
try:
    update.download(bad, tmp)
    check("sha256 다르면 실패", False)
except update.UpdateError as e:
    check("sha256 다르면 실패", "sha256" in str(e), e)
try:
    update.download(info, tmp, cancelled=lambda: True)
    check("취소", False)
except update.UpdateError as e:
    check("취소", str(e) == "취소했습니다", e)

# ---------------------------------------------------------------- 바꿀 대상
t, why = update.current_target()
check("개발 실행에서는 업데이트 안 함", t is None and "만들어진 프로그램" in why)
appdir = tmp / "Applications" / "상품가격계산기.app" / "Contents" / "MacOS"
appdir.mkdir(parents=True)
(appdir / "상품가격계산기").write_text("old")
t, why = update.current_target("darwin", str(appdir / "상품가격계산기"))
check("맥: .app 폴더를 찾음", t == (tmp / "Applications" / "상품가격계산기.app").resolve(), (t, why))
t, why = update.current_target("darwin", "/private/var/folders/x/AppTranslocation/ABC/d/상품가격계산기.app/Contents/MacOS/상품가격계산기")
check("맥: 내려받은 곳에서 열었으면 옮기라고 안내", t is None and "응용 프로그램" in why, why)
t, why = update.current_target("win32", str(tmp / "jinju-cal.exe"))
check("윈도우: exe 파일", t == (tmp / "jinju-cal.exe").resolve(), (t, why))

# ---------------------------------------------------------------- 맥 설치 스크립트 (bash 로 실제 실행)
if shutil.which("bash"):
    apps = tmp / "Apps"
    old = apps / "상품가격계산기.app"
    new = apps / ".상품가격계산기.update.app"
    for d, v in ((old, "1.1.1"), (new, "9.9.9")):
        (d / "Contents").mkdir(parents=True)
        (d / "Contents" / "version").write_text(v)
    sleeper = subprocess.Popen(["sleep", "2"])
    threading.Thread(target=sleeper.wait, daemon=True).start()  # 끝나면 바로 정리 (실제 프로그램처럼 완전히 사라지게)
    os.environ["JINJU_UPDATE_NO_OPEN"] = "1"
    t0 = time.time()
    rc = update.launch_installer(old, new, pids=[sleeper.pid], platform="darwin", wait=True)
    waited = time.time() - t0
    check("맥 스크립트: 프로그램이 닫힐 때까지 기다림", waited >= 1.5, waited)
    check("맥 스크립트: 새 앱으로 바뀜", rc == 0 and (old / "Contents" / "version").read_text() == "9.9.9" and not new.exists()
          and not (apps / "상품가격계산기.old.app").exists(), sorted(p.name for p in apps.iterdir()))
    # 새 앱이 없으면 예전 앱을 그대로 둠
    update.launch_installer(old, apps / ".없음.app", pids=[999999], platform="darwin", wait=True)
    check("맥 스크립트: 바꿀 것이 없으면 그대로", (old / "Contents" / "version").read_text() == "9.9.9" and not (apps / "상품가격계산기.old.app").exists())

# 새로 띄우는 프로그램이 기존 임시 폴더(_MEI…)를 같이 쓰지 않도록 실행 정보 제거
os.environ["_PYI_APPLICATION_HOME_DIR"] = r"C:\Temp\_MEI123"
os.environ["_PYI_PARENT_PROCESS_LEVEL"] = "1"
os.environ["_MEIPASS2"] = r"C:\Temp\_MEI123"
ce = update.child_env({"X_TEST": "1"})
check("새 프로세스 환경: PyInstaller 실행 정보 제거",
      not any(k.startswith("_PYI_") for k in ce) and "_MEIPASS2" not in ce
      and ce.get("PYINSTALLER_RESET_ENVIRONMENT") == "1" and ce.get("X_TEST") == "1" and "PATH" in ce, sorted(ce))
for k in ("_PYI_APPLICATION_HOME_DIR", "_PYI_PARENT_PROCESS_LEVEL", "_MEIPASS2"):
    os.environ.pop(k, None)

# 남은 '….update.exe' 정리: 지금 것이 최신일 때만 지움
_d = Path(tempfile.mkdtemp())
os.environ["JINJU_CAL_DATA"] = str(_d / "data")
_exe = _d / "상품가격계산기.exe"
_exe.write_bytes(b"cur")
check("남은 파일 없으면 None", update.leftover_staged(str(_exe)) is None)
(_d / "상품가격계산기.update.exe").write_bytes(b"new")
check("남은 update 파일 찾음", update.leftover_staged(str(_exe)) == _d / "상품가격계산기.update.exe")
check("새 버전이 있으면 남겨 둠 (업데이트 때 덮어씀)", not update.cleanup_leftover(False, str(_exe)) and (_d / "상품가격계산기.update.exe").exists())
check("막 받은 파일(10분 안)은 최신이어도 건드리지 않음", not update.cleanup_leftover(True, str(_exe)) and (_d / "상품가격계산기.update.exe").exists())
_old = time.time() - 3600
os.utime(_d / "상품가격계산기.update.exe", (_old, _old))
check("최신이면 지움 + 기록", update.cleanup_leftover(True, str(_exe)) and not (_d / "상품가격계산기.update.exe").exists()
      and "정리" in update.log_path().read_text(encoding="utf-8"))
check("기록 파일은 설정 폴더", update.log_path() == _d / "data" / "update.log")
check("윈도우 스크립트: 2분 재시도·복사 대비·기록", "Copy-Item" in update.WIN_SCRIPT and "$Log" in update.WIN_SCRIPT and update.WIN_SCRIPT.count("-lt 240") == 2)

print("실패 %d건" % len(fails) if fails else "모두 통과")
srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
