# -*- coding: utf-8 -*-
"""nen_context — pull a quote back out of the transcript with the turns around it.

A quote that arrives through a signal count has been stripped of the thing that decides what it
means: what came before it. "No, the other one" is a correction or a clarification depending
entirely on what the agent had just said.

Transcripts are one enormous JSON object per line, so neither grep nor a text editor makes them
readable. This is the way back to the original.

Deliberately unfiltered, unlike the corpus reader: pasted text, harness injections and agent turns
are all shown as they were stored. Verification means seeing what was actually there.

Exit codes carry a finding, not just a status:
  0  found
  1  no match -- **the quote is not in the corpus, so it may not be used as evidence**
  2  nothing scanned -- the roots are wrong or empty, which is not the same as "not found"

Self-test: python tools/nen_context.py --self-test
"""
import argparse
import glob
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nen_corpus as corpus  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _line_text(d):
    msg = d.get("message") if isinstance(d.get("message"), dict) else None
    if msg:
        return corpus._text_blocks(msg.get("content"))
    payload = d.get("payload") if isinstance(d.get("payload"), dict) else None
    if payload and payload.get("content") is not None:
        return corpus._text_blocks(payload.get("content"))
    for key in ("text", "content"):
        if isinstance(d.get(key), str):
            return d[key].strip()
    return ""


def _line_role(d):
    payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}
    return d.get("type") or payload.get("role") or "?"


def find(needle, roots, span, chars):
    """Yield rendered context blocks. Scans every jsonl under each root, format-agnostically."""
    paths = []
    for root in roots:
        root = os.path.expanduser(os.path.expandvars(root))
        paths += sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))

    hits = 0
    for path in paths:
        rows = [(_line_role(d), (d.get("timestamp") or d.get("ts") or "")[:16], _line_text(d))
                for d in corpus._read_jsonl(path)]
        for i, (_role, _ts, text) in enumerate(rows):
            if needle not in text:
                continue
            hits += 1
            block = ["===== %s @ %s =====" % (os.path.basename(path), rows[i][1])]
            for j in range(max(0, i - span), min(len(rows), i + span + 1)):
                role, ts, txt = rows[j]
                block.append("%s [%s] %s %s"
                             % (">>>" if j == i else "   ", role, ts, txt[:chars]))
            yield "\n".join(block)
    yield {"scanned": len(paths), "hits": hits}


def _self_test():
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "proj")
        os.makedirs(d)
        rows = [
            {"type": "assistant", "timestamp": "2026-08-01T09:58:00Z",
             "message": {"content": [{"type": "text", "text": "I moved the file to /tmp"}]}},
            {"type": "user", "timestamp": "2026-08-01T09:59:00Z",
             "message": {"content": [{"type": "text", "text": "no, put it back"}]}},
            {"type": "assistant", "timestamp": "2026-08-01T10:00:00Z",
             "message": {"content": [{"type": "text", "text": "restored"}]}},
        ]
        with io.open(os.path.join(d, "a.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

        out = list(find("put it back", [tmp], span=1, chars=200))
        stats = out[-1]
        blocks = out[:-1]
        check("the quote is found", stats["hits"] == 1, str(stats))
        check("the turn before it comes too", "I moved the file to /tmp" in blocks[0])
        check("the turn after it comes too", "restored" in blocks[0])
        check("the matched line is marked", ">>>" in blocks[0])
        check("agent turns are shown, unlike in the corpus reader",
              "[assistant]" in blocks[0])

        miss = list(find("a quote nobody ever wrote", [tmp], 1, 200))[-1]
        check("a quote that isn't there reports zero hits, having scanned files",
              miss["hits"] == 0 and miss["scanned"] == 1, str(miss))

        empty = list(find("anything", [os.path.join(tmp, "nowhere")], 1, 200))[-1]
        check("scanning nothing is distinguishable from finding nothing",
              empty["scanned"] == 0, str(empty))

    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="pull a quote back out of the transcript")
    ap.add_argument("needle", nargs="?", help="any distinctive fragment of the quote")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--span", type=int, default=2, help="turns of context each side (default 2)")
    ap.add_argument("--chars", type=int, default=300, help="characters shown per turn")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()
    if not args.needle:
        ap.error("give a fragment of the quote, or --self-test")

    cfg = corpus.load_config(args.config)
    roots = [s.get("root", "") for s in cfg["sources"]]
    stats = None
    for item in find(args.needle, roots, args.span, args.chars):
        if isinstance(item, dict):
            stats = item
        else:
            print("\n" + item)

    print("\n[nen-context] alive: scanned=%d hits=%d" % (stats["scanned"], stats["hits"]))
    if not stats["scanned"]:
        print("no transcripts scanned -- check the roots in your config (exit 2)")
        return 2
    if not stats["hits"]:
        print("not in the corpus: this quote cannot be used as evidence (exit 1)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
