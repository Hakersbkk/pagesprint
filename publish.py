#!/usr/bin/env python3
"""Publish ~/pagesprint to a new public GitHub repo via the REST API
(github.com is blocked on this network; api.github.com is not).
Reads the token from ~/pagesprint/.gh-token (never print it).
Usage: python3 publish.py [repo-name]
"""
import base64, json, os, pathlib, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
REPO = sys.argv[1] if len(sys.argv) > 1 else "pagesprint"
API = "https://api.github.com"
IGNORE = {".git", "data.db", "server.log", "__pycache__", ".gh-token", "tunnel.log",
          "tunnel.pid", "public.url", "sites/1", "sites/2", "sites/3", "node_modules"}
SKIP_EXT = {".png", ".ico"}  # template artwork: skip big binaries, keep code


def call(method, path, body=None, token=None, ok=(200, 201, 204)):
    req = urllib.request.Request(API + path, method=method, headers={
        "Accept": "application/vnd.github+json",
        **({"Authorization": "Bearer " + token} if token else {}),
        **({"Content-Type": "application/json"} if body is not None else {})})
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as r:
            return r.status, json.load(r) if r.status != 204 else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def collect():
    files = {}
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == i or rel.startswith(i + "/") or p.is_dir() for i in IGNORE):
            continue
        if p.suffix.lower() in SKIP_EXT or p.stat().st_size > 900000:
            print("skip", rel)
            continue
        files[rel] = p.read_text(errors="replace")
    store = ROOT / "public" / "index.html"
    if store.exists():  # the storefront becomes the GitHub Pages homepage
        files["index.html"] = store.read_text(errors="replace")
    return files


def main():
    token = (ROOT / ".gh-token").read_text().strip()
    code, me = call("GET", "/user", token=token)
    if code != 200:
        sys.exit("token invalid: " + str(me.get("message")))
    user = me["login"]
    code, repo = call("GET", f"/repos/{user}/{REPO}", token=token)
    if code == 200:
        print(f"repo exists: https://github.com/{user}/{REPO} (page: https://{user}.github.io/{REPO}/)")
    else:
        code, repo = call("POST", "/user/repos", {"name": REPO, "description":
            "PageSprint — one-page websites business. $0 AI-powered stack (local LLM gateway + MIT templates).",
            "private": False}, token=token)
        if code != 201:
            sys.exit("create failed: " + str(repo))
        print(f"created: https://github.com/{user}/{REPO}")
    files = collect()
    print(f"pushing {len(files)} files ...")
    for i, (path, content) in enumerate(files.items(), 1):
        b64 = base64.b64encode(content.encode()).decode()
        code, old = call("GET", f"/repos/{user}/{REPO}/contents/{path}?ref=main", token=token)
        body = {"message": f"publish {path}", "content": b64, "branch": "main"}
        if code == 200:
            body["sha"] = old["sha"]
        c, _ = call("PUT", f"/repos/{user}/{REPO}/contents/{path}", body, token=token)
        if c not in (200, 201):
            print(f"  FAIL {path}: {c}")
        else:
            print(f"  {i}/{len(files)} {path}")
    # README so the repo page sells the idea
    readme = (f"# PageSprint — one-page websites business\n\n"
              f"Sells professional one-page websites to local businesses for a flat fee, delivered in 24h.\n"
              f"Zero-cost stack: a local LLM gateway writes pitches and builds every site; MIT themes from"
              f" Start Bootstrap are filled by the AI; payment is collected locally.\n\n"
              f"## Stack\n- `app.py` — stdlib Python server + AI builder (OpenAI-compatible endpoint)\n"
              f"- `dashboard.html` — orders/leads/revenue control panel\n"
              f"- `store.template.html` — public storefront with service tiers\n"
              f"- `templates/` — 5 MIT themes (agency, creative, freelancer, grayscale, resume)\n"
              f"- `templates/fetch.py` — re-fetches themes via the jsDelivr CDN mirror of GitHub\n\n"
              f"## Run\n```bash\npython3 app.py   # dashboard on http://127.0.0.1:8790\n```\n"
              f"Set your ebony/OpenAI-compatible key in ~/.our-free-model/settings.json.\n")
    b64 = base64.b64encode(readme.encode()).decode()
    code, old = call("GET", f"/repos/{user}/{REPO}/contents/README.md?ref=main", token=token)
    body = {"message": "add README", "content": b64, "branch": "main",
            **({"sha": old["sha"]} if code == 200 else {})}
    call("PUT", f"/repos/{user}/{REPO}/contents/README.md", body, token=token)
    # free hosting: GitHub Pages
    c, pages = call("POST", f"/repos/{user}/{REPO}/pages",
                    {"source": {"branch": "main", "path": "/"}}, token=token)
    if c in (201, 204):
        print(f"Pages enabled -> https://{user}.github.io/{REPO}/ (live in ~1 min)")
    else:
        print("pages:", c, pages.get("message", ""))
    (ROOT / ".last-repo").write_text(f"{user}/{REPO}")
    print("DONE — repo:", f"https://github.com/{user}/{REPO}")


if __name__ == "__main__":
    main()
