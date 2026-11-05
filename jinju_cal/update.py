"""프로그램 안에서 새 버전 받기 — GitHub Releases 의 최신 버전을 받아 지금 프로그램과 바꿈.

프로그램이 직접 받은 파일에는 '인터넷에서 받음' 표시가 붙지 않아서,
처음 한 번만 맥 '그래도 열기'(윈도우 'PC 보호' 실행)를 하면 그다음 업데이트는 확인 창 없이 열림.

순서: check() → download() → (맥) prepare_mac() → launch_installer() → 프로그램 종료
      → 설치 스크립트가 프로그램이 닫히길 기다렸다가 파일을 바꾸고 새 버전을 엶
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import __version__
from .price import _reason, _ssl_context

REPO = "kwon-8648/jinju-cal"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
UA = "jinju-cal-updater"


class UpdateError(Exception):
    pass


def parse_version(s: str) -> tuple:
    nums = re.findall(r"\d+", str(s or ""))
    return tuple(int(x) for x in nums[:3]) or (0,)


def platform_key(platform: str = None):
    p = platform or sys.platform
    if p == "darwin":
        return "mac"
    if p == "win32":
        return "windows"
    return None


def _open(url: str, timeout: float, accept: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_context()))
    try:
        return opener.open(req, timeout=timeout)
    except Exception as e:
        raise UpdateError(_reason(e))


def check(api_url: str = None, current: str = __version__, platform: str = None, timeout: float = 15.0):
    """새 버전이 있으면 {version, url, size, digest, name}, 없으면 None."""
    key = platform_key(platform)
    with _open(api_url or API_URL, timeout, "application/vnd.github+json") as r:
        try:
            d = json.loads(r.read().decode("utf-8"))
        except Exception:
            raise UpdateError("업데이트 정보를 읽을 수 없습니다")
    tag = str(d.get("tag_name") or "")
    if not tag or parse_version(tag) <= parse_version(current):
        return None
    suffix = {"mac": "-mac.dmg", "windows": "-windows.exe"}.get(key)
    asset = next((a for a in d.get("assets") or [] if suffix and str(a.get("name", "")).endswith(suffix)), None)
    if not asset:
        raise UpdateError(f"새 버전 {tag.lstrip('v')}에 이 컴퓨터용 파일이 없습니다")
    return {"version": tag.lstrip("v"), "url": asset["browser_download_url"], "size": int(asset.get("size") or 0),
            "digest": str(asset.get("digest") or ""), "name": asset["name"]}


def download(info: dict, dest_dir, progress=None, cancelled=lambda: False, timeout: float = 60.0) -> Path:
    """받아서 크기(와 있으면 sha256)를 확인한 파일 경로. progress(받은 바이트, 전체)."""
    dest = Path(dest_dir) / info["name"]
    part = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    got = 0
    with _open(info["url"], timeout, "application/octet-stream") as r, open(part, "wb") as f:
        total = info.get("size") or int(r.headers.get("Content-Length") or 0)
        while True:
            if cancelled():
                f.close()
                part.unlink(missing_ok=True)
                raise UpdateError("취소했습니다")
            try:
                chunk = r.read(256 * 1024)
            except Exception as e:
                raise UpdateError("받는 중 끊김 (" + _reason(e) + ")")
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if progress:
                progress(got, total)
    if info.get("size") and got != info["size"]:
        part.unlink(missing_ok=True)
        raise UpdateError(f"파일을 다 받지 못했습니다 ({got:,} / {info['size']:,} 바이트)")
    dg = info.get("digest", "")
    if dg.startswith("sha256:") and dg[7:].lower() != h.hexdigest():
        part.unlink(missing_ok=True)
        raise UpdateError("받은 파일이 올린 파일과 다릅니다 (sha256 불일치)")
    os.replace(part, dest)
    return dest


# ---------------------------------------------------------------- 지금 실행 중인 프로그램 위치
def current_target(platform: str = None, exe: str = None):
    """바꿀 대상: 맥은 .app 폴더, 윈도우는 .exe 파일. 바꿀 수 없으면 (None, 이유)."""
    if not getattr(sys, "frozen", False) and exe is None:
        return None, "만들어진 프로그램(.app/.exe)으로 실행할 때만 업데이트할 수 있습니다."
    exe = Path(exe or exe_path()).resolve()
    key = platform_key(platform)
    if key == "mac":
        app = next((p for p in [exe, *exe.parents] if p.suffix == ".app"), None)
        if app is None:
            return None, "앱 위치를 찾지 못했습니다."
        s = str(app)
        if "/AppTranslocation/" in s or s.startswith("/Volumes/"):
            return None, "앱을 '응용 프로그램' 폴더로 옮긴 뒤 다시 열고 업데이트하세요.\n(지금은 내려받은 곳이나 dmg 안에서 열려 있습니다)"
        target = app
    elif key == "windows":
        target = exe
    else:
        return None, "이 컴퓨터에서는 업데이트할 수 없습니다."
    if not os.access(target.parent, os.W_OK):
        return None, f"'{target.parent}' 폴더에 쓸 권한이 없어 업데이트할 수 없습니다."
    return target, ""


# ---------------------------------------------------------------- 맥: dmg 안의 앱을 옆에 복사해 둠
def prepare_mac(dmg: Path, app: Path) -> Path:
    mnt = Path(tempfile.mkdtemp(prefix="jinjucal-dmg-"))
    staged = app.with_name("." + app.stem + ".update.app")
    try:
        r = subprocess.run(["hdiutil", "attach", str(dmg), "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mnt)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise UpdateError("받은 dmg 를 열지 못했습니다: " + (r.stderr or r.stdout).strip()[:200])
        try:
            src = next(iter(sorted(mnt.glob("*.app"))), None)
            if src is None:
                raise UpdateError("dmg 안에 앱이 없습니다")
            if staged.exists():
                shutil.rmtree(staged)
            r = subprocess.run(["ditto", str(src), str(staged)], capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                raise UpdateError("새 앱을 복사하지 못했습니다: " + (r.stderr or r.stdout).strip()[:200])
        finally:
            subprocess.run(["hdiutil", "detach", str(mnt), "-quiet", "-force"], capture_output=True, timeout=60)
        subprocess.run(["xattr", "-cr", str(staged)], capture_output=True, timeout=60)
        return staged
    except Exception:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        raise
    finally:
        try:
            mnt.rmdir()
        except OSError:
            pass


# 프로그램이 닫히길 기다렸다가 바꾸고 새 버전을 엶. 바꾸다 실패하면 예전 것을 되돌려 놓음.
# JINJU_UPDATE_NO_OPEN=1 이면 열지 않음 (빌드 때 시험용)
MAC_SCRIPT = r'''#!/bin/bash
PIDS="$1"; OLD="$2"; NEW="$3"
for i in $(seq 1 240); do
  alive=0; for p in $PIDS; do kill -0 "$p" 2>/dev/null && alive=1; done
  [ "$alive" = 0 ] && break; sleep 0.5
done
BAK="${OLD%.app}.old.app"
rm -rf "$BAK"
if mv "$OLD" "$BAK" && mv "$NEW" "$OLD"; then
  rm -rf "$BAK"
else
  [ -d "$BAK" ] && [ ! -d "$OLD" ] && mv "$BAK" "$OLD"
fi
xattr -cr "$OLD" 2>/dev/null
[ "$JINJU_UPDATE_NO_OPEN" = "1" ] || open "$OLD"
rm -f "$0"
'''

def wait_pids():
    """기다릴 프로세스. 윈도우 한 파일 exe 는 바깥 실행기(부모)가 exe 를 잡고 있어서 부모도 기다림."""
    pids = [os.getpid()]
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        try:
            pids.append(os.getppid())
        except Exception:
            pass
    return pids


def log_path() -> Path:
    """업데이트 기록 파일 (설정 폴더의 update.log)."""
    from .storage import data_dir
    d = data_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d / "update.log"


def log(msg: str):
    try:
        p = log_path()
        if p.exists() and p.stat().st_size > 200_000:  # 너무 커지면 뒤쪽만 남김
            p.write_bytes(p.read_bytes()[-50_000:])
        import datetime
        with open(p, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + msg + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- 윈도우: 새 exe 가 직접 바꿔치기
# 예전 방식(PowerShell 스크립트)은 보안 프로그램이 막으면 바꾸지도, 다시 열지도 못하고
# '….update.exe' 가 남았다. 이제 받은 새 exe 를 설정 폴더(update)에 두고, 그 새 exe 를
# '--finish-update' 로 실행해 직접 기존 프로그램이 닫히길 기다렸다가 '금계산기.exe' 로
# 복사하고 다시 연다. 프로그램 폴더에는 임시 파일이 생기지 않는다.
WIN_NAME = "금계산기.exe"           # 아이콘 밑에 보이는 파일 이름 (고정)
OLD_STEMS = ("상품가격계산기", "금계산기")  # 예전에 쓰던 이름
_EXE = None                          # 실행 중 이름을 바꾸면 여기에 새 경로


def exe_path() -> Path:
    """지금 실행 중인 프로그램 파일 (이름을 바꿨으면 바뀐 경로)."""
    return Path(_EXE or sys.executable)


def stage_dir() -> Path:
    from .storage import data_dir
    return data_dir() / "update"


def stage_windows(downloaded: Path) -> Path:
    """받은 새 exe 를 설정 폴더(update)에 둠. 프로그램 폴더에는 아무것도 만들지 않음."""
    d = stage_dir()
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("*.exe"):  # 예전에 받아 둔 것 (쓰는 중이면 그냥 둠)
        try:
            f.unlink()
        except Exception:
            pass
    dest = d / "금계산기-new.exe"
    if dest.exists():  # 지우지 못했으면 다른 이름으로
        dest = d / f"금계산기-new-{os.getpid()}.exe"
    shutil.move(str(downloaded), str(dest))
    return dest


def pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000 | 0x1000, False, int(pid))  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            return k.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT → 아직 실행 중
        finally:
            k.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    try:  # 끝났는데 거둬지지 않은(좀비) 프로세스는 닫힌 것으로
        with open(f"/proc/{int(pid)}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except Exception:
        return True


def leftovers(folder: Path, keep=()):
    """프로그램 폴더에 예전 업데이트가 남긴 '….update.exe' 들."""
    keep = {os.path.normcase(str(k)) for k in keep}
    out = []
    try:
        files = list(Path(folder).glob("*.exe"))
    except Exception:
        return out
    for f in files:
        name = f.name
        low = name.lower()
        if ".update" not in low or os.path.normcase(str(f)) in keep:
            continue
        if name[:low.index(".update")] in OLD_STEMS:
            out.append(f)
    return out


def _remove(f: Path, seconds: float = 0) -> bool:
    import time
    end = time.time() + seconds
    while True:
        try:
            f.unlink()
            return True
        except FileNotFoundError:
            return True
        except Exception:
            if time.time() >= end:
                return False
            time.sleep(0.5)


def _start(exe: Path):
    flags = (0x00000008 | 0x00000200) if sys.platform == "win32" else 0  # DETACHED | NEW_PROCESS_GROUP
    kw = {"creationflags": flags} if sys.platform == "win32" else {"start_new_session": True}
    return subprocess.Popen([str(exe)], cwd=str(exe.parent), env=child_env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)


def finish_update(old: str, pids, me: str = None, open_after: bool = True,
                  wait_s: float = 120, retry_s: float = 120) -> int:
    """(새 exe 안에서 실행) 기존 프로그램이 닫히길 기다렸다가 '금계산기.exe' 로 바꾸고 다시 엶."""
    import time
    me = Path(me or sys.executable)
    old = Path(old)
    target = old.with_name(WIN_NAME)
    log(f"업데이트 마무리 시작: {me} → {target} (기존 {old.name})")
    end = time.time() + wait_s
    while any(pid_alive(p) for p in pids) and time.time() < end:
        time.sleep(0.5)
    log("기존 프로그램 닫힘" if not any(pid_alive(p) for p in pids) else "2분 지나도 기존 프로그램이 열려 있음")
    ok, last, tries = False, "", 0
    tmp = target.with_name("~" + target.stem + ".tmp")
    end = time.time() + retry_s
    while True:
        tries += 1
        try:
            shutil.copyfile(me, tmp)
            os.replace(tmp, target)
            ok = True
            break
        except Exception as e:
            last = str(e)
            _remove(tmp)
            if time.time() >= end:
                break
            time.sleep(0.5)
    if ok:
        log(f"바꿈 ({tries}번째 시도): {target.name}")
        if os.path.normcase(str(old)) != os.path.normcase(str(target)) and old.exists():
            log(("예전 이름 파일 지움: " if _remove(old, 30) else "예전 이름 파일을 지우지 못함: ") + old.name)
        for f in leftovers(target.parent, keep=(target, me)):
            log(("남은 update 파일 지움: " if _remove(f, 5) else "남은 update 파일을 지우지 못함: ") + f.name)
    else:
        log(f"바꾸지 못함: {last}")
    run = target if ok else old
    if open_after and os.environ.get("JINJU_UPDATE_NO_OPEN") != "1" and run.exists():
        try:
            p = _start(run)
            log(f"다시 엶: {run.name} (pid {p.pid})")
        except Exception as e:
            log(f"다시 열지 못함: {e}")
    return 0 if ok else 1


def launch_finisher(staged: Path, old: Path, pids=None, wait: bool = False):
    """받은 새 exe 를 '--finish-update' 로 실행 (지금 프로그램은 바로 닫아야 함)."""
    pids = [str(p) for p in (pids or wait_pids())]
    args = [str(staged), "--finish-update", str(old), ",".join(pids)]
    kw = {"creationflags": 0x00000008 | 0x00000200} if sys.platform == "win32" else {"start_new_session": True}
    p = subprocess.Popen(args, cwd=str(Path(staged).parent), env=child_env(), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)
    log(f"새 버전으로 바꾸기 시작 (pid {p.pid})")
    if wait:
        return p.wait(timeout=400)
    return 0


def finish_from_argv(argv) -> int:
    i = argv.index("--finish-update")
    old = argv[i + 1]
    pids = [int(x) for x in argv[i + 2].split(",") if x.strip()] if len(argv) > i + 2 else []
    return finish_update(old, pids)


def tidy_windows(rename: bool = True):
    """윈도우 실행 시 정리: 이름을 '금계산기.exe' 로 맞추고, 남은 update 파일·받아 둔 파일을 지움."""
    global _EXE
    if not (sys.platform == "win32" and getattr(sys, "frozen", False)):
        return
    cur = exe_path()
    target = cur.with_name(WIN_NAME)
    if rename and os.environ.get("JINJU_NO_SELF_RENAME") != "1" \
            and os.path.normcase(str(cur)) != os.path.normcase(str(target)) and not target.exists():
        try:  # 실행 중인 exe 도 같은 폴더 안에서는 이름을 바꿀 수 있음
            os.rename(cur, target)
            _EXE = str(target)
            log(f"파일 이름을 바꿈: {cur.name} → {target.name}")
            cur = target
        except Exception as e:
            log(f"파일 이름을 바꾸지 못함: {cur.name} ({e})")
    for f in leftovers(cur.parent, keep=(cur,)):
        if _remove(f):
            log("남은 update 파일 지움: " + f.name)
    try:
        for f in stage_dir().glob("*.exe"):
            _remove(f)
    except Exception:
        pass


def child_env(extra=None):
    """새 프로세스용 환경 변수.

    윈도우 한 파일(onefile) 실행 파일은 자기 실행 정보(_PYI_*, _MEIPASS2)를 환경 변수로 남긴다.
    그대로 넘기면 새로 띄운 프로그램이 기존 임시 폴더(_MEI…)를 같이 써서, 기존 프로그램이
    닫힐 때 "Failed to remove temporary directory" 경고가 뜬다. 그래서 지우고 초기화를 요청한다.
    """
    env = {k: v for k, v in os.environ.items() if not (k.startswith("_PYI_") or k == "_MEIPASS2")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if extra:
        env.update(extra)
    return env


def launch_installer(target: Path, staged: Path, pids=None, platform: str = None, wait: bool = False):
    """설치 스크립트를 따로 실행. wait=True 면 끝날 때까지 기다림 (시험용)."""
    key = platform_key(platform)
    pids = " ".join(str(p) for p in (pids or wait_pids()))
    tmp = Path(tempfile.mkdtemp(prefix="jinjucal-up-"))
    if key == "mac":
        sh = tmp / "install.sh"
        sh.write_text(MAC_SCRIPT, encoding="utf-8")
        sh.chmod(0o755)
        args = ["/bin/bash", str(sh), pids, str(target), str(staged)]
        kw = {"start_new_session": True}
    else:
        raise UpdateError("이 컴퓨터에서는 업데이트할 수 없습니다.")
    p = subprocess.Popen(args, env=child_env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, **kw)
    if wait:
        return p.wait(timeout=180)
    return 0


def install(info: dict, progress=None, cancelled=lambda: False, platform: str = None, exe: str = None):
    """받기 → 준비 → 설치 스크립트 실행. 성공하면 프로그램을 바로 닫아야 함."""
    target, why = current_target(platform, exe)
    if target is None:
        raise UpdateError(why)
    work = Path(tempfile.mkdtemp(prefix="jinjucal-dl-"))
    f = download(info, work, progress, cancelled)
    key = platform_key(platform)
    log(f"새 버전 {info.get('version')} 받음")
    if key == "mac":
        staged = prepare_mac(f, target)
        shutil.rmtree(work, ignore_errors=True)
        launch_installer(target, staged, platform=platform)
    else:
        staged = stage_windows(f)
        shutil.rmtree(work, ignore_errors=True)
        launch_finisher(staged, target)
    return target


__all__ = ["UpdateError", "check", "download", "install", "parse_version", "current_target"]
