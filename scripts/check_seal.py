"""앱 서명 기록(CodeResources)과 실제 파일을 하나씩 비교해 어긋난 것을 보여줌 (맥 진단용)."""
import hashlib, os, plistlib, sys
app = sys.argv[1]
c = os.path.join(app, "Contents")
d = plistlib.load(open(os.path.join(c, "_CodeSignature", "CodeResources"), "rb"))
files2 = d.get("files2", {})
bad = 0
for rel, v in files2.items():
    p = os.path.join(c, rel)
    if isinstance(v, dict) and "symlink" in v:
        ok = os.path.islink(p) and os.readlink(p) == v["symlink"]
        if not ok: bad += 1; print("SYMLINK", rel, v["symlink"], os.readlink(p) if os.path.islink(p) else "(없음)")
        continue
    if isinstance(v, dict) and ("cdhash" in v or "requirement" in v):
        if not os.path.exists(p): bad += 1; print("NESTED MISSING", rel); continue
        import subprocess
        r = subprocess.run(["codesign", "-d", "--verbose=4", p], capture_output=True, text=True)
        cur = [l.split("=", 1)[1] for l in r.stderr.splitlines() if l.startswith("CDHash=")]
        rec = v.get("cdhash").hex() if isinstance(v.get("cdhash"), bytes) else None
        vr = subprocess.run(["codesign", "--verify", "--strict", p], capture_output=True, text=True)
        if (rec and cur and cur[0] != rec) or vr.returncode != 0:
            bad += 1; print("NESTED BAD", rel, "rec", rec, "cur", cur[:1], vr.stderr.strip()[:200])
        continue
    h = v.get("hash2") if isinstance(v, dict) else None
    if h is None: continue
    if not os.path.exists(p): bad += 1; print("MISSING", rel); continue
    if os.path.islink(p): bad += 1; print("IS LINK (기록은 파일)", rel); continue
    if hashlib.sha256(open(p, "rb").read()).digest() != h: bad += 1; print("MODIFIED", rel)
# 기록에 없는 파일
seen = set(files2)
for root, dirs, fs in os.walk(c):
    for n in fs + [x for x in dirs if os.path.islink(os.path.join(root, x))]:
        rel = os.path.relpath(os.path.join(root, n), c)
        if rel.startswith("_CodeSignature") or rel.startswith("MacOS/") or rel == "Info.plist": continue
        if rel not in seen and not any(rel.startswith(s + "/") for s in seen): print("UNSEALED", rel)
print("files2", len(files2), "bad", bad)
