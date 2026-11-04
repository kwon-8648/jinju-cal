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
    exe = Path(exe or sys.executable).resolve()
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

WIN_SCRIPT = r'''param([string]$Pids, [string]$Old, [string]$New)
$ErrorActionPreference = 'SilentlyContinue'
$ids = $Pids -split ' ' | Where-Object { $_ } | ForEach-Object { [int]$_ }
for ($i = 0; $i -lt 240; $i++) {
  if (-not (Get-Process -Id $ids -ErrorAction SilentlyContinue)) { break }
  Start-Sleep -Milliseconds 500
}
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
  try { Move-Item -LiteralPath $New -Destination $Old -Force -ErrorAction Stop; $ok = $true; break }
  catch { Start-Sleep -Milliseconds 500 }
}
if ($env:JINJU_UPDATE_NO_OPEN -ne '1') { Start-Process -FilePath $Old }
Remove-Item -LiteralPath $PSCommandPath -Force
if (-not $ok) { exit 1 }
'''


def stage_windows(exe: Path, downloaded: Path) -> Path:
    """받은 exe 를 지금 exe 옆으로 (같은 드라이브라 바꿀 때 바로 옮겨짐)."""
    staged = exe.with_name(exe.stem + ".update.exe")
    if staged.exists():
        staged.unlink()
    shutil.move(str(downloaded), str(staged))
    return staged


def wait_pids():
    """기다릴 프로세스. 윈도우 한 파일 exe 는 바깥 실행기(부모)가 exe 를 잡고 있어서 부모도 기다림."""
    pids = [os.getpid()]
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        try:
            pids.append(os.getppid())
        except Exception:
            pass
    return pids


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
    elif key == "windows":
        ps = tmp / "install.ps1"
        ps.write_text(WIN_SCRIPT, encoding="utf-8-sig")
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                "-File", str(ps), "-Pids", pids, "-Old", str(target), "-New", str(staged)]
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
        kw = {"creationflags": flags} if not wait else {"creationflags": 0x08000000}
    else:
        raise UpdateError("이 컴퓨터에서는 업데이트할 수 없습니다.")
    p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)
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
    staged = prepare_mac(f, target) if key == "mac" else stage_windows(target, f)
    shutil.rmtree(work, ignore_errors=True)
    launch_installer(target, staged, platform=platform)
    return target


__all__ = ["UpdateError", "check", "download", "install", "parse_version", "current_target"]
