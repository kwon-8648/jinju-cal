"""빌드 때 실제 맥·윈도우에서 업데이트 바꿔치기 확인 (GitHub Actions 에서만 실행).

  python tests/test_update_ci.py mac  <받은.dmg> <만든.app>
  python tests/test_update_ci.py windows <만든.exe>

실행 중인 프로그램을 띄워 두고 → 설치 스크립트가 그 프로그램이 닫히길 기다리는지,
닫은 뒤 새 것으로 바뀌는지(맥은 서명도 그대로인지) 확인.
"""
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
    print(("  ok  " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra and not cond else ""), flush=True)
    if not cond:
        fails.append(name)


os.environ["JINJU_UPDATE_NO_OPEN"] = "1"  # 바꾼 뒤 새 프로그램을 띄우지 않음
work = Path(tempfile.mkdtemp(prefix="jinjucal-ci-"))
env = dict(os.environ, JINJU_CAL_DATA=str(work / "data"), QT_QPA_PLATFORM="offscreen")


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
    t, why = update.current_target("darwin", str(old / "Contents" / "MacOS" / built.stem))
    check("바꿀 대상 = 복사한 앱", t == old.resolve(), (t, why))

    staged = update.prepare_mac(dmg, old)
    check("dmg 에서 새 앱 꺼내 옆에 둠", staged.exists() and staged.parent == old.parent, staged)

    prog = subprocess.Popen([str(old / "Contents" / "MacOS" / built.stem)], env=env)
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
    old = work / "jinju-cal-old.exe"
    shutil.copy2(built, old)
    staged = work / "jinju-cal-old.update.exe"
    staged.write_bytes(b"NEW-VERSION")  # 바뀌었는지 알아보기 쉬운 내용
    t, why = update.current_target("win32", str(old))
    check("바꿀 대상 = exe", t == old.resolve(), (t, why))

    prog = subprocess.Popen([str(old)], env=env)
    time.sleep(10)  # 한 파일 exe 는 풀어서 여는 데 시간이 걸림
    running = prog.poll() is None
    th, box = run_installer(old, staged, prog.pid, "win32")
    time.sleep(4)
    check("프로그램이 열려 있는 동안은 바꾸지 않음", (not running) or old.read_bytes() != b"NEW-VERSION")
    subprocess.run(["taskkill", "/PID", str(prog.pid), "/T", "/F"], capture_output=True)
    th.join(150)
    check("닫은 뒤 새 exe 로 바뀜", box.get("rc") == 0 and old.read_bytes() == b"NEW-VERSION" and not staged.exists(), box)
    print("  (프로그램이 떠 있었는지: %s)" % running)

print("실패 %d건" % len(fails) if fails else "모두 통과", flush=True)
shutil.rmtree(work, ignore_errors=True)
sys.exit(1 if fails else 0)
