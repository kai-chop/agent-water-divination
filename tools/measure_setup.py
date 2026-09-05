# -*- coding: utf-8 -*-
"""measure_setup — how deep this operator's Claude Code setup is, and what shape their usage has.

Read-only. Two halves, and only the first one is a measurement:

  SETUP / REF / EST   what is in --claude-dir, against a published adoption table. The one axis
                      with a real reference population, so the one axis 偏差値 can be computed on.
  SHAPE / TEMPO /     proxies read out of a corpus.jsonl built by mizumi_corpus.py. Regex counts
  AUTONOMY / HOURS    of surface features; context for a judge, never a verdict.

Self-test: python measure_setup.py --self-test
"""
import argparse
import collections
import datetime
import glob
import io
import json
import math
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Adoption rates = share of the sample that has the feature at all.
# Source: Build This Now, "2,500 public Claude Code repositories", 2026-06.
# Refresh when newer public data exists, and cite source + date wherever the number is shown.
REF = {"CLAUDE.md": 0.849, ".claude dir": 0.621, "settings.json": 0.410, "skills": 0.281,
       "commands": 0.256, "subagents": 0.246, "MCP": 0.170, "hooks": 0.133}
EST_TAIL = (0.05, 0.03, 0.02, 0.01, 0.005)
HEAVY_CHARS = 120
LONG_CHARS = 300

CORR = re.compile(r"(違う|そうじゃな|ではなく|じゃなくて|直して|戻して|間違|ズレ|誤)")
QUES = re.compile(r"(？|\?|かな$|だろうか|できる？|と思う？)")
RULE = re.compile(r"(今後|毎回|ルール|仕様に|恒久|台帳|skill|スキル|仕組|機構|索引|正典|規律)")
IMAGE = re.compile(r"(したい|してほしい|がほしい|が欲しい|を実現|ように(して|なる)|になったら|完成|理想|ゴール)")
METAPH = re.compile(r"(のように|みたいに|みたいな|的な|に似|に喩|たとえば|例えば|みたい|っぽい)")


def hensachi(p_top):
    """p_top = fraction of the population at or above this level -> 偏差値 = 50 + 10*inverse-normal(1-p)."""
    lo, hi = -6.0, 6.0
    target = 1 - p_top
    for _ in range(80):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < target:
            lo = mid
        else:
            hi = mid
    return 50 + 10 * (lo + hi) / 2


def measure_setup(claude_dir):
    def size(p):
        try:
            return os.path.getsize(p)
        except OSError:
            return 0

    def count(pattern):
        return len(glob.glob(os.path.join(claude_dir, pattern)))

    setup = collections.OrderedDict()
    setup["CLAUDE.md_bytes"] = size(os.path.join(claude_dir, "CLAUDE.md"))
    setup["rules_files"] = count(os.path.join("rules", "*.md"))
    setup["rules_bytes"] = sum(size(p) for p in glob.glob(os.path.join(claude_dir, "rules", "*.md")))
    setup["skills"] = len([d for d in glob.glob(os.path.join(claude_dir, "skills", "*")) if os.path.isdir(d)])
    setup["commands"] = count(os.path.join("commands", "*.md"))
    setup["agents"] = count(os.path.join("agents", "*.md"))
    setup["ledgers"] = count(os.path.join("ledgers", "*.md"))
    setup["scripts_py"] = count(os.path.join("scripts", "*.py")) + count(os.path.join("scripts", "**", "*.py"))
    setup["scripts_ps1"] = count(os.path.join("scripts", "*.ps1"))
    try:
        st = json.load(io.open(os.path.join(claude_dir, "settings.json"), encoding="utf-8"))
        hooks = st.get("hooks", {})
        setup["hook_events"] = sorted(hooks.keys())
        setup["hook_commands"] = sum(len(h.get("hooks", [])) for ev in hooks.values() for h in ev)
        setup["permissions_allow"] = len(st.get("permissions", {}).get("allow", []))
        setup["permissions_deny"] = len(st.get("permissions", {}).get("deny", []))
    except Exception as e:
        setup["settings_error"] = str(e)
    setup["mcp_servers"] = 0
    try:
        j = json.load(io.open(os.path.join(claude_dir, os.pardir, ".claude.json"), encoding="utf-8"))
        setup["mcp_servers"] = len(j.get("mcpServers", {}))
    except Exception:
        pass
    return setup


def print_reference():
    for k, p in REF.items():
        print("REF %-14s top%5.1f%% -> 偏差値 %.1f" % (k, p * 100, hensachi(p)))
    for p in EST_TAIL:
        print("EST top%4.1f%% -> 偏差値 %.1f" % (p * 100, hensachi(p)))


def print_shape(corpus_path):
    """The proxy half. Returns the number of corpus rows read (0 = nothing to describe)."""
    rows = [json.loads(l) for l in io.open(corpus_path, encoding="utf-8") if l.strip()]
    if not rows:
        print("SHAPE (no rows in %s)" % corpus_path)
        return 0
    subst = [r for r in rows if r["kind"] == "substantive"]
    stats = collections.Counter()
    for r in subst:
        t = r["text"]
        stats["n"] += 1
        stats["correction_like"] += bool(CORR.search(t))
        stats["question_like"] += bool(QUES.search(t))
        stats["rule_like"] += bool(RULE.search(t))
        stats["image_like"] += bool(IMAGE.search(t))
        stats["metaphor_like"] += bool(METAPH.search(t))
        stats["heavy>=%d" % HEAVY_CHARS] += r["chars"] >= HEAVY_CHARS
        stats["long>=%d" % LONG_CHARS] += r["chars"] >= LONG_CHARS
    print("SHAPE", dict(stats))

    days = sorted({r["ts"][:10] for r in rows})
    first = datetime.date(*[int(x) for x in days[0].split("-")])
    last = datetime.date(*[int(x) for x in days[-1].split("-")])
    sessions = len({r["session"] for r in rows})
    print("TEMPO prompts=%d sessions=%d active_days=%d span_days=%d prompts_per_active_day=%.1f sessions_per_active_day=%.1f"
          % (len(rows), sessions, len(days), (last - first).days + 1, len(rows) / len(days), sessions / len(days)))

    aft = [r for r in rows if r.get("after")]
    runs = sorted((r["after"]["tools"] for r in aft), reverse=True)
    print("AUTONOMY with_after=%d runs>=30=%d runs>=100=%d top5=%s median=%s"
          % (len(aft), sum(1 for x in runs if x >= 30), sum(1 for x in runs if x >= 100), runs[:5],
             runs[len(runs) // 2] if runs else None))
    print("HOURS", sorted(collections.Counter(int(r["ts"][11:13]) for r in rows).items()))
    return len(rows)


def _self_test():
    import tempfile
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    check("hensachi(0.133) is the hooks row of the table", abs(hensachi(0.133) - 61.1) < 0.05, "%.3f" % hensachi(0.133))
    check("hensachi(0.5) is the median", abs(hensachi(0.5) - 50.0) < 0.05, "%.3f" % hensachi(0.5))
    check("rarer is higher", hensachi(0.005) > hensachi(0.05) > hensachi(0.5))

    with tempfile.TemporaryDirectory() as tmp:
        empty = os.path.join(tmp, "claude")
        os.makedirs(empty)
        setup = measure_setup(empty)
        check("an empty setup measures as empty, not as an error", setup["skills"] == 0 and setup["CLAUDE.md_bytes"] == 0, str(setup["skills"]))
        os.makedirs(os.path.join(empty, "skills", "one"))
        io.open(os.path.join(empty, "CLAUDE.md"), "w", encoding="utf-8").write("hello\n")
        setup = measure_setup(empty)
        check("a skill directory and a CLAUDE.md are counted", setup["skills"] == 1 and setup["CLAUDE.md_bytes"] > 0,
              "skills=%s CLAUDE.md_bytes=%s" % (setup["skills"], setup["CLAUDE.md_bytes"]))

        corpus = os.path.join(tmp, "corpus.jsonl")
        rows = [
            {"id": 0, "ts": "2026-05-01 09:00", "project": "atlas", "session": "s1", "kind": "substantive",
             "chars": 130, "text": "完成した状態はこうしたい。判断がズレたら直してほしい。" * 5,
             "after": {"tools": 42, "wrote": ["a.py"], "ai_first": "", "next_text": "", "next_gap_min": None}},
            {"id": 1, "ts": "2026-05-01 10:00", "project": "atlas", "session": "s1", "kind": "short", "chars": 3, "text": "うん"},
            {"id": 2, "ts": "2026-05-02 22:00", "project": "atlas", "session": "s2", "kind": "substantive",
             "chars": 40, "text": "今後は毎回ルールとして台帳へ書いてください。"},
        ]
        with io.open(corpus, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        buf = io.StringIO()
        real, sys.stdout = sys.stdout, buf
        try:
            n = print_shape(corpus)
        finally:
            sys.stdout = real
        text = buf.getvalue()
        print(text.rstrip())
        check("three rows read", n == 3, str(n))
        check("SHAPE line describes the substantive rows", "SHAPE" in text and "'n': 2" in text)
        check("SHAPE picked up the correction and rule proxies", "'correction_like': 1" in text and "'rule_like': 1" in text)
        check("TEMPO line spans the two days", "TEMPO prompts=3 sessions=2 active_days=2 span_days=2" in text)
        check("AUTONOMY line sees the one transcript-joined row", "AUTONOMY with_after=1 runs>=30=1" in text)
    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="setup depth against a public reference, plus usage-shape proxies")
    ap.add_argument("--claude-dir", default=os.path.join(os.path.expanduser("~"), ".claude"))
    ap.add_argument("--corpus", default=os.path.join(".", "out", "corpus.jsonl"),
                    help="corpus.jsonl from mizumi_corpus.py; skipped when the file is not there")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    setup = measure_setup(args.claude_dir)
    print("SETUP", json.dumps(setup, ensure_ascii=False))
    print_reference()
    rows = print_shape(args.corpus) if os.path.isfile(args.corpus) else 0
    if not rows:
        print("(no corpus at %s -- run mizumi_corpus.py first for the shape half)" % args.corpus)
    print("[measure-setup] alive: claude_dir=%s skills=%s corpus_rows=%d" % (args.claude_dir, setup["skills"], rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
