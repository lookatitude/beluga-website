import os, re, sys, json
root, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
fence = re.compile(r'^([ \t]*)(```+|~~~+)\s*go\b[^\n]*\n(.*?)^\1\2\s*$', re.M | re.S)
idx = []
stats = {"blocks":0,"withpkg":0}
n = 0
for dp, dn, fn in os.walk(root):
    for f in fn:
        if not f.endswith(('.md','.mdx')): continue
        p = os.path.join(dp, f)
        txt = open(p, encoding='utf-8').read()
        for m in fence.finditer(txt):
            stats["blocks"] += 1
            code = m.group(3)
            ind = m.group(1)
            if ind: code = "\n".join(l[len(ind):] if l.startswith(ind) else l for l in code.split("\n"))
            if not re.search(r'^package \w+', code, re.M): continue
            stats["withpkg"] += 1
            line = txt[:m.start()].count("\n") + 1
            orig_v1 = bool(re.search(r'"github\.com/lookatitude/beluga-ai/(?!v2/)', code))
            code2 = re.sub(r'github\.com/lookatitude/beluga-ai/(?!v2/)', 'github.com/lookatitude/beluga-ai/v2/', code)
            n += 1
            d = os.path.join(out, f"s{n:04d}")
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "main.go"), "w").write(code2)
            idx.append({"id": f"s{n:04d}", "file": os.path.relpath(p, root), "line": line, "v1import": orig_v1,
                        "uses_beluga": "lookatitude/beluga-ai" in code})
json.dump(idx, open(os.path.join(out, "index.json"), "w"), indent=1)
print(stats, n)
