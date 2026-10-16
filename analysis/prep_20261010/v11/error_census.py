"""Registered census of tool-error messages in original MCP server code (PREREG_addendum_v11_error_census_KO.md).

No model, no network. Reads pinned server sources under /workspace/TAEYUN/tp-redteam/local/vendor (read only),
extracts the message templates that a failing tool call can return, and classifies each template with the
registered keyword rules: explained > call-blaming > unexplained, plus passthrough (no literal words).

Usage (from condition_study/):
    python3 -B analysis/prep_20261010/v11/error_census.py            # writes census.json, templates.jsonl here
    python3 -B analysis/prep_20261010/v11/error_census.py --selftest # synthetic examples only
"""
import collections, hashlib, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VEND = Path("/workspace/TAEYUN/tp-redteam/local/vendor")
SERVERS = {
    "FileSystem": "ctx-filesystem/source/src/filesystem",
    "Memory": "ctx-filesystem/source/src/memory",
    "Fetch": "ctx-filesystem/source/src/fetch/src",
    "Sequential Thinking": "ctx-filesystem/source/src/sequentialthinking",
    "Everything": "ctx-filesystem/source/src/everything",
    "AWSKnowledgeBase": "ctx-archived/source/src/aws-kb-retrieval-server",
    "BraveSearch": "ctx-archived/source/src/brave-search",
    "EverArt": "ctx-archived/source/src/everart",
    "GoogleDrive": "ctx-archived/source/src/gdrive",
    "Github": "ctx-archived/source/src/github",
    "Gitlab": "ctx-archived/source/src/gitlab",
    "Google Maps": "ctx-archived/source/src/google-maps",
    "Puppeteer": "ctx-archived/source/src/puppeteer",
    "Redis": "ctx-archived/source/src/redis",
    "Sentry": "ctx-archived/source/src/sentry",
    "Slack": "ctx-archived/source/src/slack",
    "SQLite": "ctx-archived/source/src/sqlite",
    "Git": "ctx-git/source/src",
    "Commander": "ctx-commander/source/src",
    "Email": "ctx-email/source/src",
    "ClickHouse": "ctx-clickhouse/source/mcp_clickhouse",
    "QuickChart": "ctx-quickchart/source/src",
}
SKIP_PARTS = {"node_modules", "dist", "build", "__tests__", "tests", "test", "__pycache__"}

EXPLAINED = ["not found", "no such", "does not exist", "doesn't exist", "enoent", "permission", "denied", "forbidden",
             "unauthori", "authenticat", "timeout", "timed out", "rate limit", "too many requests", "network",
             "connection", "econn", "unavailable", "status", "http", "api error", "quota", "outside allowed",
             "not allowed"]
CALL = ["invalid", "missing", "required", "must", "unknown tool", "unknown command", "unknown action",
        "not supported", "unsupported", "expected", "validation", "malformed", "cannot be empty", "too long",
        "exceeds", "out of range", "parse"]

START_TS = [re.compile(r"throw\s+new\s+(?!McpError)\w*Error\s*\("), re.compile(r"new\s+McpError\s*\(")]
START_PY = [re.compile(r"raise\s+(?!McpError)\w+(?:\.\w+)*\s*\("), re.compile(r"McpError\s*\(")]
ISERR = re.compile(r"isError\s*[:=]\s*(?:true|True)")
TEXT_TS = re.compile(r"text\s*:\s*")
TEXT_PY = re.compile(r"text\s*=\s*")
TEXTCONTENT_PY = re.compile(r"TextContent\s*\(")


def balanced(s, i):
    """Return s[i:j] where s[i-1] is '(' and s[j] is its closing ')'. Quotes are skipped."""
    depth, j, q = 1, i, None
    while j < len(s):
        ch = s[j]
        if q:
            if ch == "\\":
                j += 2
                continue
            if ch == q:
                q = None
        elif ch in "'\"`":
            q = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return s[i:j]
        j += 1
    return s[i:j]


def first_arg(expr):
    depth, q = 0, None
    for j, ch in enumerate(expr):
        if q:
            if ch == q and expr[j - 1] != "\\":
                q = None
        elif ch in "'\"`":
            q = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            return expr[:j]
    return expr


def value_expr(s, i):
    """Expression starting at s[i] up to a top-level ',' or closing bracket or newline outside quotes."""
    depth, j, q = 0, i, None
    while j < len(s):
        ch = s[j]
        if q:
            if ch == "\\":
                j += 2
                continue
            if ch == q:
                q = None
        elif ch in "'\"`":
            q = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch in ",\n" and depth == 0:
            break
        j += 1
    return s[i:j]


LIT = re.compile(r"""(?P<pre>[fFrRbB]{0,2})(?P<q>`|'''|\"\"\"|'|")(?P<body>.*?)(?<!\\)(?P=q)""", re.S)


def template(expr):
    """Literal text of an expression; interpolations and non-literal parts become {x}."""
    out, last = [], 0
    for m in LIT.finditer(expr):
        gap = expr[last:m.start()].strip(" +\n\t()")
        if gap and re.search(r"[A-Za-z_]", gap):
            out.append("{x}")
        body = m.group("body")
        if m.group("q") == "`":
            body = re.sub(r"\$\{[^}]*\}", "{x}", body)
        elif "f" in m.group("pre").lower():
            body = re.sub(r"\{[^}]*\}", "{x}", body)
        out.append(body)
        last = m.end()
    tail = expr[last:].strip(" +\n\t()")
    if tail and re.search(r"[A-Za-z_]", tail):
        out.append("{x}")
    t = re.sub(r"(\{x\}\s*)+", "{x} ", "".join(out)).strip()
    return re.sub(r"\s+", " ", t)


def classify(t):
    words = re.sub(r"\{x\}", " ", t).lower()
    letters = re.sub(r"\b(error|err|failed|failure)\b|[^a-z]", "", words)
    if len(letters) < 3:
        return "passthrough"
    if any(k in words for k in EXPLAINED):
        return "explained"
    if any(k in words for k in CALL):
        return "call-blaming"
    return "unexplained"


def extract(text, lang):
    found = []
    starts = START_TS if lang == "ts" else START_PY
    for rx in starts:
        for m in rx.finditer(text):
            arg = first_arg(balanced(text, m.end()))
            if "McpError" in rx.pattern:
                full = balanced(text, m.end())
                mm = re.search(r"message\s*=\s*", full)
                if mm:                                   # Python: McpError(ErrorData(code=..., message=...))
                    arg = value_expr(full, mm.end())
                else:                                    # TS: new McpError(ErrorCode.X, message)
                    rest = full[len(arg) + 1:]
                    arg = first_arg(rest) if rest.strip() else arg
            found.append((m.start(), "throw", arg))
    for m in ISERR.finditer(text):
        window = text[max(0, m.start() - 500):m.end() + 300]
        rx = TEXT_TS if lang == "ts" else TEXT_PY
        hits = list(rx.finditer(window))
        if hits:
            h = min(hits, key=lambda h: abs(h.start() - 500))
            found.append((m.start(), "isError", value_expr(window, h.end())))
    if lang == "py":
        for m in TEXTCONTENT_PY.finditer(text):
            body = balanced(text, m.end())
            t = TEXT_PY.search(body)
            if t:
                v = value_expr(body, t.end())
                lit = template(v)
                if re.match(r"(?i)\s*(\{x\}\s*)?(error|failed)", lit):
                    found.append((m.start(), "TextContent", v))
    return found


def files_of(root):
    for p in sorted(root.rglob("*")):
        if p.suffix in (".ts", ".py") and not (SKIP_PARTS & set(p.parts)) and not p.name.endswith(".d.ts"):
            yield p


def census():
    rows, per = [], {}
    for server, rel in SERVERS.items():
        root = VEND / rel
        if not root.exists():
            per[server] = {"missing_source": str(root)}
            continue
        seen = {}
        for p in files_of(root):
            text = p.read_text(encoding="utf-8", errors="replace")
            lang = "ts" if p.suffix == ".ts" else "py"
            for pos, kind, expr in extract(text, lang):
                t = template(expr)
                if not t:
                    continue
                line = text.count("\n", 0, pos) + 1
                key = t
                if key not in seen:
                    seen[key] = {"server": server, "template": t, "class": classify(t), "kind": kind,
                                 "where": f"{p.relative_to(VEND)}:{line}", "n_sites": 0}
                seen[key]["n_sites"] += 1
        rows += list(seen.values())
        per[server] = dict(collections.Counter(r["class"] for r in seen.values()))
    classes = ["explained", "call-blaming", "unexplained", "passthrough"]
    pooled = collections.Counter(r["class"] for r in rows)
    shares = {}
    for s, c in per.items():
        n = sum(c.get(k, 0) for k in classes)
        if n:
            shares[s] = {k: c.get(k, 0) / n for k in classes}
    server_mean = {k: round(sum(v[k] for v in shares.values()) / len(shares), 4) for k in classes} if shares else {}
    return rows, {"per_server_counts": per, "pooled_counts": dict(pooled), "n_templates": len(rows),
                  "pooled_share": {k: round(pooled.get(k, 0) / max(1, len(rows)), 4) for k in classes},
                  "server_mean_share": server_mean, "n_servers_with_templates": len(shares),
                  "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def selftest():
    ts = '''
      if (!x) throw new Error(`Invalid arguments for ${name}: ${err}`);
      throw new Error("Access denied - path outside allowed directories: " + p);
      throw new McpError(ErrorCode.InternalError, `Failed to create issue`);
      return { content: [{ type: "text", text: `Error: ${error instanceof Error ? error.message : String(error)}` }], isError: true };
    '''
    py = '''
        raise ValueError(f"Unknown tool: {name}")
        raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to fetch {url} - status code {r.status_code}"))
        return [TextContent(type="text", text=f"Error: {str(e)}")]
        raise RuntimeError(str(e))
    '''
    got_ts = [(k, template(e), classify(template(e))) for _, k, e in extract(ts, "ts")]
    got_py = [(k, template(e), classify(template(e))) for _, k, e in extract(py, "py")]
    for g in got_ts + got_py:
        print(g)
    cls = [c for _, _, c in got_ts + got_py]
    assert cls.count("call-blaming") == 2, cls          # Invalid arguments..., Unknown tool...
    assert len(got_ts) == 4 and len(got_py) == 4, (len(got_ts), len(got_py))
    assert ("throw", "Failed to fetch {x} - status code {x}", "explained") in got_py, got_py
    assert "explained" in cls and "unexplained" in cls and "passthrough" in cls, cls
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        rows, summary = census()
        with open(HERE / "templates.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        json.dump(summary, open(HERE / "census.json", "w"), indent=1, ensure_ascii=False)
        print(json.dumps({k: summary[k] for k in ("n_templates", "pooled_share", "server_mean_share")}, indent=1))
