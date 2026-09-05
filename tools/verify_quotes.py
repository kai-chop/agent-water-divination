# -*- coding: utf-8 -*-
"""verify_quotes — every quotation on the reading page has to exist in the history, verbatim.

Each <blockquote><p>...</p> in the page must be a substring of some `display` field in
history.jsonl. Zero-fail: a page with no quotes exits 1 too, because "nothing to check" and
"everything checked out" print the same green otherwise.

Usage:  python verify_quotes.py page.html [--history ~/.claude/history.jsonl]
Self-test: python verify_quotes.py --self-test
"""
import argparse
import html
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

QUOTE_RX = re.compile(r"<blockquote[^>]*>\s*<p>(.*?)</p>", re.S)
TAG_RX = re.compile(r"<[^>]+>")


def norm(s):
    s = s.replace("\r\n", "\n")
    s = re.sub(r"[ \t　]+", lambda m: " " if " " in m.group(0) else m.group(0), s)
    return s.strip()


def quotes_in(page):
    return [html.unescape(TAG_RX.sub("", q)) for q in QUOTE_RX.findall(page)]


def verify(page_path, history_path):
    page = io.open(page_path, encoding="utf-8").read()
    texts = []
    for line in io.open(history_path, encoding="utf-8", errors="replace"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and isinstance(r.get("display"), str):
            texts.append(r["display"].replace("\r\n", "\n"))
    normed = [norm(t) for t in texts]
    scanned = matched = 0
    for q in quotes_in(page):
        scanned += 1
        # tolerate only a run of spaces having been collapsed by the page's own formatting
        ok = any(q in t for t in texts) or any(norm(q) in t for t in normed)
        print(("PASS " if ok else "FAIL ") + q[:70].replace("\n", " "))
        matched += ok
    print("[verify-quotes] alive: scanned=%d matched=%d history=%s" % (scanned, matched, history_path))
    return 0 if scanned and matched == scanned else 1


def _self_test():
    import tempfile
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    page_tpl = "<html><body><blockquote><p>%s</p></blockquote><blockquote><p>%s</p></blockquote></body></html>"
    with tempfile.TemporaryDirectory() as tmp:
        hist = os.path.join(tmp, "h.jsonl")
        with io.open(hist, "w", encoding="utf-8") as f:
            for d in ("完成した状態を先に書いてから作り始めてほしい", "not that one -- read the index instead"):
                f.write(json.dumps({"display": d, "timestamp": 1750000000000, "sessionId": "s1"}, ensure_ascii=False) + "\n")
            f.write("{ half a line\n")

        good = os.path.join(tmp, "good.html")
        io.open(good, "w", encoding="utf-8").write(
            page_tpl % ("完成した状態を先に書いてから<em>作り始めて</em>ほしい", "not that one -- read the index instead"))
        buf, real = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            rc_good = verify(good, hist)
        finally:
            sys.stdout = real
        print(buf.getvalue().rstrip())
        check("a page whose quotes all exist exits 0", rc_good == 0, "rc=%d" % rc_good)
        check("and says so in the alive line", "scanned=2 matched=2" in buf.getvalue())

        bad = os.path.join(tmp, "bad.html")
        io.open(bad, "w", encoding="utf-8").write(
            page_tpl % ("完成した状態を先に書いてから作り始めてほしい", "a sentence the operator never wrote"))
        buf2, real = io.StringIO(), sys.stdout
        sys.stdout = buf2
        try:
            rc_bad = verify(bad, hist)
        finally:
            sys.stdout = real
        check("one invented quote fails the whole page", rc_bad == 1, "rc=%d" % rc_bad)
        check("and the failing quote is named", "FAIL a sentence the operator never wrote" in buf2.getvalue())

        none = os.path.join(tmp, "none.html")
        io.open(none, "w", encoding="utf-8").write("<html><body><p>no quotes at all</p></body></html>")
        buf3, real = io.StringIO(), sys.stdout
        sys.stdout = buf3
        try:
            rc_none = verify(none, hist)
        finally:
            sys.stdout = real
        check("a page with zero quotes fails rather than passing vacuously", rc_none == 1, "rc=%d" % rc_none)
        check("scanned=0 is visible in the alive line", "scanned=0 matched=0" in buf3.getvalue())
    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="check every blockquote on the page against history.jsonl")
    ap.add_argument("page", nargs="?", help="the reading, as HTML")
    ap.add_argument("--history", default=os.path.join(os.path.expanduser("~"), ".claude", "history.jsonl"))
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.page:
        ap.error("give the page to check, or --self-test")
    return verify(args.page, args.history)


if __name__ == "__main__":
    sys.exit(main())
