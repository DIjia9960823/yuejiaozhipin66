# -*- coding: utf-8 -*-
"""用 GitHub API 直接推送整个项目（无需安装 Git）。
用法：python tools/push_github.py
"""
import base64, json, os, sys, time
import requests
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

REPO = "DIjia9960823/yuejiaozhipin66"
BRANCH = "main"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = r"F:\XIANG\粤教师\粤师聘-原型\guangdong-teacher-jobs\crawler\github_token.txt"

SKIP_DIRS = {".git", "附件缓存", "__pycache__", ".vscode", "crawler_log.txt"}
SKIP_FILES = {".DS_Store", "Thumbs.db"}
MAX_MB = 40

tok = open(TOKEN_FILE, encoding="utf-8").read().strip()
H = {"Authorization": "token " + tok, "User-Agent": "yuejiaozhiquan-push",
     "Accept": "application/vnd.github+json"}
API = "https://api.github.com"


def ensure_repo():
    r = requests.get(f"{API}/repos/{REPO}", headers=H, timeout=30)
    if r.status_code == 200:
        print(f"✅ 仓库已存在：{REPO}")
        return True
    if r.status_code == 404:
        print(f"⚠️ 仓库不存在，正在创建 {REPO} ...")
        r2 = requests.post(f"{API}/user/repos", headers=H,
                           json={"name": REPO.split("/")[1], "private": False,
                                 "auto_init": False}, timeout=30)
        if r2.status_code in (200, 201):
            print("✅ 仓库创建成功")
            return True
        print(f"❌ 创建失败 {r2.status_code}: {r2.text[:200]}")
        return False
    print(f"❌ 检查仓库失败 {r.status_code}: {r.text[:200]}")
    return False


def list_files():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES or fn.endswith((".pyc", ".log")):
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT).replace("\\", "/")
            size = os.path.getsize(fp)
            if size > MAX_MB * 1024 * 1024:
                print(f"⏭ 跳过超大文件 {rel} ({size/1024/1024:.1f}MB)")
                continue
            out.append((rel, fp, size))
    return sorted(out)


def get_sha(path):
    r = requests.get(f"{API}/repos/{REPO}/contents/{path}", headers=H,
                     params={"ref": BRANCH}, timeout=30)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def put_file(path, fp):
    data = open(fp, "rb").read()
    sha = get_sha(path)
    body = {"message": f"update {path}", "branch": BRANCH,
            "content": base64.b64encode(data).decode()}
    if sha:
        body["sha"] = sha
    r = requests.put(f"{API}/repos/{REPO}/contents/{path}", headers=H,
                     json=body, timeout=120)
    return r.status_code, r.text[:200]


def main():
    if not ensure_repo():
        return
    files = list_files()
    print(f"\n📦 共 {len(files)} 个文件待上传")
    ok = fail = skip = 0
    failed = []
    for rel, fp, size in files:
        try:
            code, msg = put_file(rel, fp)
            if code in (200, 201):
                ok += 1
                print(f"  ✅ {rel} ({size//1024}KB)")
            elif code == 422 and "sha" in msg:
                skip += 1
            else:
                fail += 1
                failed.append((rel, code, msg))
                print(f"  ❌ {rel} → {code} {msg}")
            time.sleep(0.3)
        except Exception as e:
            fail += 1
            failed.append((rel, "ERR", str(e)[:150]))
            print(f"  ❌ {rel} → {e}")
    print(f"\n结果：成功 {ok} / 失败 {fail} / 跳过 {skip}")
    if failed:
        print("\n失败明细：")
        for f in failed:
            print(f"  {f[0]} → {f[1]} {f[2]}")
    print(f"\n🌐 网站：https://dijia9960823.github.io/yuejiaozhipin66/")


if __name__ == "__main__":
    main()
