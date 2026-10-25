"""Lint every ```go block (fragments too) in the given md/mdx/astro files for
framework packages or package-level symbols that do not exist.
usage: python3 -I apilint.py <api.json> <file-or-dir>... ; exit 1 if any finding."""
import json, os, re, sys, collections
MOD = "github.com/lookatitude/beluga-ai/v2"
api = json.load(open(sys.argv[1]))
API, NAMES = api["api"], api["names"]
byname = collections.defaultdict(set)
for ip, n in NAMES.items():
    byname[n].add(ip)
# common non-framework names that collide with framework package names
STDLIB_COLLIDE = {"errors", "context", "time", "log", "trace", "http", "json", "sync", "io", "os", "fmt", "strings", "template", "url", "rand", "codes", "metric", "sql", "slog", "testing", "iter", "bytes", "filepath", "exec", "signal", "atomic", "regexp", "sort", "strconv", "math", "net", "bufio", "base64", "hex", "sha256", "hmac", "tls", "zap", "otel", "attribute", "propagation", "httptest", "runtime", "debug", "embed", "maps", "slices", "cmp", "utf8", "unicode", "binary", "csv", "xml", "yaml", "uuid", "redis", "jwt", "grpc", "mongo", "nats", "kafka", "temporal", "openai", "anthropic", "workflow", "config"}
fence = re.compile(r'^([ \t]*)(```+|~~~+)\s*go\b[^\n]*\n(.*?)^\1\2\s*$', re.M | re.S)
imp_re = re.compile(r'^\s*(?:import\s+)?(?:(\w+|_|\.)\s+)?"([^"\s]+)"', re.M)
anyimp = re.compile(r'github\.com/lookatitude/beluga-ai/v2(/[\w./-]*\w)?')

def check_text(path, txt, findings):
    file_aliases = {}
    for m in fence.finditer(txt):
        code = m.group(3)
        line = txt[:m.start()].count("\n") + 1
        local = {}
        for im in imp_re.finditer(code):
            alias, p = im.group(1), im.group(2)
            if not p.startswith("github.com/lookatitude/beluga-ai"):
                parts = p.split("/")
                last = parts[-1]
                if re.fullmatch(r"v\d+", last) and len(parts) > 1:
                    last = parts[-2]
                a = alias or last.replace("go-", "")
                local[a] = None  # non-framework import shadows
                local[last] = None
                continue
            if p not in API and not p.startswith(MOD + "/cmd"):
                findings.append((line, f"missing package {p.replace(MOD + '/', '')}"))
                continue
            if alias in ("_", "."):
                continue
            a = alias or NAMES.get(p, p.rsplit("/", 1)[-1])
            local[a] = {p}
        file_aliases.update({k: v for k, v in local.items()})
        aliases = dict(file_aliases)
        # shadowed identifiers (locals/params named like a package)
        shadow = set(re.findall(r'\b(\w+)\s*(?:,\s*\w+\s*)?:=', code)) | set(re.findall(r'\bvar\s+(\w+)', code)) \
            | set(re.findall(r'[(,]\s*(\w+)\s+\*?[\w.\[\]]+\s*[,)]', code)) | set(re.findall(r'\bfor\s+\w*,?\s*(\w+)\s*:=', code)) \
            | set(re.findall(r'func\s*\(\s*(\w+)\s', code))
        for mm in re.finditer(r'(?<![\w.])([a-z]\w*)\.([A-Z]\w*)', code):
            pk, sym = mm.group(1), mm.group(2)
            if pk in shadow and pk not in local:
                continue
            cands = aliases.get(pk, "unset")
            if cands is None:
                continue
            if cands == "unset":
                if pk in STDLIB_COLLIDE or pk not in byname:
                    continue
                cands = byname[pk]
            if not any(sym in API.get(ip, {}) for ip in cands):
                ln = line + code[:mm.start()].count("\n") + 1
                findings.append((ln, f"undefined {pk}.{sym}"))
    # framework paths outside go fences (go get lines etc.)
    for mm in anyimp.finditer(txt):
        p = MOD + (mm.group(1) or "")
        if "..." in p or p.endswith("/v2"):
            continue
        p = p.split("@")[0]
        if p not in API and not p.startswith(MOD + "/cmd") and not p.startswith(MOD + "/internal"):
            ln = txt[:mm.start()].count("\n") + 1
            findings.append((ln, f"missing package {p.replace(MOD + '/', '')}"))

total = 0
out = {}
for arg in sys.argv[2:]:
    paths = [arg] if os.path.isfile(arg) else [os.path.join(dp, f) for dp, _, fs in os.walk(arg) for f in fs if f.endswith((".md", ".mdx", ".astro"))]
    for p in sorted(paths):
        f = []
        check_text(p, open(p, encoding="utf-8").read(), f)
        f = sorted(set(f))
        if f:
            out[p] = f
            total += len(f)
for p, fs in out.items():
    print(p)
    for ln, msg in fs:
        print(f"  {ln}: {msg}")
print(f"TOTAL {total} findings in {len(out)} files", file=sys.stderr)
sys.exit(1 if total else 0)
