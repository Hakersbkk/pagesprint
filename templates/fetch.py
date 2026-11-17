#!/usr/bin/env python3
"""Fetch Start Bootstrap templates (MIT) via the jsDelivr CDN mirror of GitHub."""
import json, sys, urllib.request, pathlib

CDN = "https://cdn.jsdelivr.net/gh/StartBootstrap/{repo}@master/{path}"
API = "https://data.jsdelivr.com/v1/packages/gh/StartBootstrap/{repo}@master"
TEMPLATES = {"agency", "freelancer", "grayscale", "creative", "resume"}


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def fetch(repo, dest):
    tree = json.loads(get(API.format(repo=repo)))
    files = []

    def walk(nodes, p=""):
        for f in nodes:
            if f["type"] == "directory":
                walk(f.get("files", []), p + "/" + f["name"])
            elif p.startswith("/dist"):
                files.append((p + "/" + f["name"], f["size"]))
    walk(tree["files"])
    for path, size in files:
        out = dest / path.lstrip("/").replace("dist/", "", 1)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(get(CDN.format(repo=repo, path=path.lstrip("/"))))
        print(f"  {path} ({size//1024}KB)")
    n = len(list(dest.rglob("*")))
    print(f"{repo}: {n} files -> {dest}")


if __name__ == "__main__":
    for name in TEMPLATES:
        fetch("startbootstrap-" + name, pathlib.Path(__file__).parent / name)
