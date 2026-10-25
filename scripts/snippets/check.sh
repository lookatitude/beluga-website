#!/usr/bin/env bash
# Compile-check the Go snippets in the docs against a framework checkout.
#
# usage: scripts/snippets/check.sh <framework-dir> [out-dir]
#
# 1. Dumps the framework's exported API (apidump) and lints every ```go
#    block, fragments included, for packages/symbols that do not exist.
# 2. Extracts every ```go block that has a `package` clause and runs
#    `go build` on each one against the framework (via a replace directive).
#
# Exit status: 0 when every check passed, 1 otherwise. Partial snippets that
# intentionally omit app-specific helpers fail step 2, so CI runs this as an
# advisory job and publishes the summary.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
fw=$(cd "$1" && pwd)
out=${2:-$(mktemp -d)}
mkdir -p "$out"
mod=github.com/lookatitude/beluga-ai/v2
status=0

echo "::group::API lint"
(cd "$here/apidump" && go run . "$fw" "$mod") > "$out/api.json"
if ! python3 -I "$here/apilint.py" "$out/api.json" "$repo/src" > "$out/apilint.txt"; then
  status=1
fi
cat "$out/apilint.txt"
echo "::endgroup::"

echo "::group::Snippet compile"
rm -rf "$out/snips"
python3 -I "$here/extract.py" "$repo/src/content" "$out/snips/snips"
cat > "$out/snips/go.mod" <<MOD
module snips

go 1.26

require $mod v2.0.0

replace $mod => $fw
MOD
(cd "$out/snips" && go mod tidy -e >/dev/null 2>&1)
ok=0; fail=0
: > "$out/snipbuild.log"
for d in "$out"/snips/snips/s*/; do
  id=$(basename "$d")
  if res=$(cd "$out/snips" && go build -o /dev/null "./snips/$id" 2>&1); then
    ok=$((ok+1)); echo "snips/$id OK" >> "$out/snipbuild.log"
  else
    fail=$((fail+1)); { echo "snips/$id FAIL"; echo "$res" | sed 's/^/  /'; } >> "$out/snipbuild.log"
  fi
done
echo "::endgroup::"
python3 -I - "$out" <<'PY'
import json, re, sys
out = sys.argv[1]
idx = {e["id"]: e for e in json.load(open(out + "/snips/snips/index.json"))}
cur = None
for line in open(out + "/snipbuild.log"):
    m = re.match(r"snips/(s\d+) (OK|FAIL)", line)
    if m:
        cur = m.group(1)
        if m.group(2) == "FAIL":
            e = idx[cur]
            print(f"FAIL {e['file']}:{e['line']}")
        continue
    if cur and line.strip() and not line.strip().startswith("#"):
        print("    " + line.strip()[:200])
PY
echo "complete snippets: $ok compile, $fail fail"
[ "$fail" -eq 0 ] || status=1
exit $status
