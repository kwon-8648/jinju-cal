#!/bin/bash
# 맥 앱 임시 서명(ad-hoc) — 안쪽부터 하나씩.
# PyInstaller 의 codesign --deep 이 이 앱(PySide6)에서 멈춰(Bus error / -10) 반쯤 쓴 *.cstemp 파일을 남기고
# 서명이 깨진 채 끝나서, 맥이 "손상된 파일"이라며 막았음. 그래서 --deep 을 쓰지 않음.
#   scripts/mac_sign.sh <앱.app>
set -euo pipefail
APP="$1"
xattr -cr "$APP"
find "$APP" -name '*.cstemp' -print -delete       # 멈춘 서명이 남긴 찌꺼기
# 1) 실행 코드 파일(Mach-O) 하나씩 (심볼릭 링크는 건너뜀)
find "$APP/Contents" -type f -print0 | while IFS= read -r -d '' f; do
  if file -b "$f" | grep -q 'Mach-O'; then codesign --force --sign - "$f" >/dev/null; fi
done
# 2) 안쪽 번들(.framework 등) — 깊은 것부터
find "$APP/Contents" -type d \( -name '*.framework' -o -name '*.bundle' -o -name '*.app' \) -print0 \
  | xargs -0 -I{} sh -c 'printf "%s\t%s\n" "$(printf %s "{}" | wc -c)" "{}"' | sort -rn | cut -f2- \
  | while IFS= read -r b; do codesign --force --sign - "$b" >/dev/null; done
# 3) 앱 전체
codesign --force --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
