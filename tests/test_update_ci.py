"""빌드 때 실제 맥·윈도우에서 업데이트 바꿔치기 확인 (GitHub Actions 에서만 실행).

  python tests/test_update_ci.py mac  <받은.dmg> <만든.app>
  python tests/test_update_ci.py windows <만든.exe>

실행 중인 프로그램을 띄워 두고 → 설치 스크립트가 그 프로그램이 닫히길 기다리는지,
닫은 뒤 새 것으로 바뀌는지(맥은 서명도 그대로인지) 확인.
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:  # 윈도우 콘솔에서도 한글 결과가 찍히게
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from jinju_cal import update  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra and not cond else ""), flush=True)
    if not cond:
        fails.append(name)


os.environ["JINJU_UPDATE_NO_OPEN"] = "1"  # 바꾼 뒤 새 프로그램을 띄우지 않음
work = Path(tempfile.mkdtemp(prefix="jinjucal-ci-"))
os.environ["JINJU_CAL_DATA"] = str(work / "data")  # 업데이트 기록(update.log)도 여기로
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")


def run_installer(target, staged, pid, platform):
    box = {}
    t = threading.Thread(target=lambda: box.setdefault("rc", update.launch_installer(target, staged, pids=[pid], platform=platform, wait=True)))
    t.start()
    return t, box


if sys.argv[1] == "mac":
    dmg, built = Path(sys.argv[2]), Path(sys.argv[3])
    apps = work / "Applications"
    apps.mkdir()
    old = apps / built.name
    subprocess.run(["ditto", str(built), str(old)], check=True)
    (old / "Contents" / "Resources" / "OLD_MARKER").write_text("old")  # 예전 것 표시
    exe_name = plistlib.load(open(old / "Contents" / "Info.plist", "rb"))["CFBundleExecutable"]
    t, why = update.current_target("darwin", str(old / "Contents" / "MacOS" / exe_name))
    check("바꿀 대상 = 복사한 앱", t == old.resolve(), (t, why))

    staged = update.prepare_mac(dmg, old)
    check("dmg 에서 새 앱 꺼내 옆에 둠", staged.exists() and staged.parent == old.parent, staged)

    prog = subprocess.Popen([str(old / "Contents" / "MacOS" / exe_name)], env=env)
    threading.Thread(target=prog.wait, daemon=True).start()
    time.sleep(6)
    running = prog.poll() is None
    th, box = run_installer(old, staged, prog.pid, "darwin")
    time.sleep(3)
    check("프로그램이 열려 있는 동안은 바꾸지 않음", (not running) or (old / "Contents" / "Resources" / "OLD_MARKER").exists())
    prog.terminate()
    th.join(120)
    check("닫은 뒤 새 앱으로 바뀜", box.get("rc") == 0 and not (old / "Contents" / "Resources" / "OLD_MARKER").exists() and not staged.exists(),
          (box, sorted(p.name for p in apps.iterdir())))
    r = subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(old)], capture_output=True, text=True)
    check("바뀐 앱 서명 정상", r.returncode == 0, r.stderr)
    print("  (프로그램이 떠 있었는지: %s)" % running)

elif sys.argv[1] == "windows":
    built = Path(sys.argv[2])
    os.environ.pop("JINJU_UPDATE_NO_OPEN", None)  # 윈도우는 다시 열리는 것까지 확인

    # 1) 다른 이름으로 실행하면 '금계산기.exe' 로 이름이 맞춰지고, 남은 update 파일이 정리됨
    d1 = work / "rename"
    d1.mkdir()
    shutil.copy2(built, d1 / "jinju-cal-0.0.1-windows.exe")
    (d1 / "상품가격계산기.update.exe").write_bytes(b"x")
    p1 = subprocess.Popen([str(d1 / "jinju-cal-0.0.1-windows.exe")], env=dict(env, JINJU_CAL_DATA=str(work / "data1")))
    time.sleep(15)
    names1 = sorted(f.name for f in d1.iterdir())
    subprocess.run(["taskkill", "/PID", str(p1.pid), "/T", "/F"], capture_output=True)
    check("실행하면 파일 이름이 '금계산기.exe' 로 바뀌고 update 파일 정리", names1 == ["금계산기.exe"], names1)

    # 2) 업데이트: 예전 이름 + 남은 update 파일이 있는 폴더에서 실행 중인 프로그램을 새 exe 가 바꾸고 다시 엶
    prog = work / "prog"
    prog.mkdir()
    old = prog / "상품가격계산기.exe"
    shutil.copy2(built, old)
    (prog / "상품가격계산기.update.exe").write_bytes(b"x")
    (prog / "상품가격계산기.update.update.exe").write_bytes(b"x")
    dl = work / "dl.exe"
    shutil.copy2(built, dl)
    staged = update.stage_windows(dl)
    check("받은 새 exe 는 설정 폴더에", staged.parent == update.stage_dir() and staged.exists(), staged)
    running = subprocess.Popen([str(old)], env=dict(env, JINJU_NO_SELF_RENAME="1", JINJU_CAL_DATA=str(work / "data2")))
    time.sleep(12)
    check("기존 프로그램 실행 중", running.poll() is None)
    update.launch_finisher(staged, old, pids=[running.pid])
    time.sleep(6)
    check("기존 프로그램이 열려 있는 동안은 바꾸지 않음", old.exists() and not (prog / "금계산기.exe").exists(),
          sorted(f.name for f in prog.iterdir()))
    subprocess.run(["taskkill", "/PID", str(running.pid), "/T", "/F"], capture_output=True)
    lg = ""
    for _ in range(120):
        time.sleep(1)
        lg = update.log_path().read_text(encoding="utf-8", errors="replace") if update.log_path().exists() else ""
        if "다시 엶" in lg or "다시 열지 못함" in lg or "바꾸지 못함" in lg:
            break
    names = sorted(f.name for f in prog.iterdir())
    check("닫힌 뒤 '금계산기.exe' 로 바뀌고 예전 파일·update 파일 정리", names == ["금계산기.exe"] and
          (prog / "금계산기.exe").read_bytes() == built.read_bytes(), (names, lg[-800:]))
    m = __import__("re").search(r"다시 엶: 금계산기\.exe \(pid (\d+)\)", lg)
    reopened = m and update.pid_alive(int(m.group(1)))
    check("새 버전이 다시 열림", bool(reopened), lg[-800:])
    time.sleep(25)  # 다시 열린 프로그램이 받은 파일(update 폴더)을 정리할 시간
    check("다시 열린 뒤 받은 파일 정리됨", not list(update.stage_dir().glob("*.exe")), list(update.stage_dir().glob("*")))
    if m:
        subprocess.run(["taskkill", "/PID", m.group(1), "/T", "/F"], capture_output=True)
    print(lg[-1500:])

    # 3) 바꿀 파일이 잠깐 잡혀 있어도 (백신 검사 등) 기다렸다가 바꿈
    dl2 = work / "dl2.exe"
    shutil.copy2(built, dl2)
    staged = update.stage_windows(dl2)
    holder = subprocess.Popen([sys.executable, "-c", "import sys,time; f=open(sys.argv[1],'rb'); time.sleep(25)", str(prog / "금계산기.exe")])
    time.sleep(2)
    os.environ["JINJU_UPDATE_NO_OPEN"] = "1"
    rc = update.launch_finisher(staged, prog / "금계산기.exe", pids=[999999], wait=True)
    holder.wait(30)
    lg = update.log_path().read_text(encoding="utf-8", errors="replace")
    check("파일이 25초 잡혀 있어도 결국 바뀜", rc == 0 and sorted(f.name for f in prog.iterdir()) == ["금계산기.exe"], (rc, lg[-600:]))

print("실패 %d건" % len(fails) if fails else "모두 통과", flush=True)
shutil.rmtree(work, ignore_errors=True)
sys.exit(1 if fails else 0)
