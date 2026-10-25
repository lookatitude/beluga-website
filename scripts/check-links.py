"""Fail when a built page links to an internal URL that does not exist.

usage: python3 scripts/check-links.py dist/
Ignores external links and /godoc/ (fetched from the framework release).
"""
import collections
import os
import re
import sys
import urllib.parse

dist = sys.argv[1]
href = re.compile(r'(?:href|src)="([^"#?]*)(?:[#?][^"]*)?"')


def exists(u):
    p = urllib.parse.unquote(os.path.join(dist, u.lstrip("/")))
    return os.path.isfile(p) or os.path.isfile(os.path.join(p, "index.html")) or os.path.isfile(p + ".html")


broken = collections.defaultdict(set)
for dp, _, fn in os.walk(dist):
    for f in fn:
        if not f.endswith(".html"):
            continue
        page = os.path.join(dp, f)
        rel = "/" + os.path.relpath(page, dist)
        base = os.path.dirname(rel)
        html = open(page, encoding="utf-8", errors="ignore").read()
        for u in href.findall(html):
            if not u or re.match(r"^(https?:|mailto:|tel:|data:|javascript:|//)", u):
                continue
            t = u if u.startswith("/") else os.path.normpath(os.path.join(base, u))
            if t.startswith("/godoc"):
                continue
            if not exists(t):
                broken[t].add(rel)

for t, ps in sorted(broken.items(), key=lambda x: -len(x[1])):
    print(f"{len(ps):4d} {t}  <- {sorted(ps)[0]}")
print(f"{len(broken)} broken internal link targets")
sys.exit(1 if broken else 0)
