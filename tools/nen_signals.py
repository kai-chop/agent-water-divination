# -*- coding: utf-8 -*-
"""nen_signals — count the six aptitudes' signals, and list what still has to be asked.

Two outputs, and the second one is the point.

**Signals.** For each of six types, how often the operator's own messages carry the marks of that
type, plus quotes to check. These are candidates. On the corpus this was built against, 40% of one
detector's hits were false positives -- fiction dialogue and spec text that happened to contain a
correction word. A number here is a reason to go read the original, not a finding.

**Open questions.** The gap between what a regex can see and what a verdict needs, written as
questions someone can actually answer. Three kinds:

- `probe` -- the corpus could not produce two quotes for this type, so ask directly and watch the
  shape of the answer
- `authorship` -- a quote heavy enough to carry a verdict is long enough to have been pasted
- `occasion` -- a signal sits at zero, and zero has two meanings: no ability, or no opportunity.
  Only the person can say which, and the difference decides whether it is a weakness at all.

Questions marked `blocking` are the ones a verdict may not be issued without. That gate lives in
water_divination.py, which refuses to print a verdict while any blocking question is unanswered.

特質系 (Specialist) has no detector on purpose. Its definition is "the combination the other five
cannot explain", so any regex for it grants it to everybody.

Self-test: python tools/nen_signals.py --self-test
"""
import argparse
import io
import json
import os
import re
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nen_corpus as corpus  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SIGNALS_VERSION = "1"

QUOTES_FOR_VERDICT = 2      # per type, before a type may be named in a verdict
CORRECTION_CHAIN_GAP = 2    # utterances apart still counted as the same correction episode
SAMPLES_PER_SIGNAL = 3


# ---------------------------------------------------------------- patterns

def load_patterns(paths, base=None):
    """Load pattern files. Several languages merge into one alternation per signal."""
    out = []
    for p in paths:
        full = corpus.resolve(p)
        if not os.path.isfile(full):
            continue
        with io.open(full, encoding="utf-8") as f:
            out.append(json.load(f))
    if not out:
        raise SystemExit("no pattern file found -- check the `patterns` key in your config")
    return out


def _alt(pattern_sets, getter):
    """OR together one signal across languages, preserving each file's case sensitivity."""
    parts = []
    for ps in pattern_sets:
        raw = getter(ps)
        if not raw:
            continue
        parts.append("(?i:%s)" % raw if ps.get("case_insensitive") else "(?:%s)" % raw)
    return re.compile("|".join(parts)) if parts else None


def type_order(pattern_sets):
    seen = []
    for ps in pattern_sets:
        for tid in ps.get("types", {}):
            if tid not in seen:
                seen.append(tid)
    return seen


def type_meta(pattern_sets, tid, key, default=""):
    for ps in pattern_sets:
        v = (ps.get("types", {}).get(tid) or {}).get(key)
        if v:
            return v
    return default


def signal_names(pattern_sets, tid):
    names = []
    for ps in pattern_sets:
        sig = (ps.get("types", {}).get(tid) or {}).get("signals")
        for n in (sig or {}):
            if n not in names:
                names.append(n)
    return names


def shared_rx(pattern_sets, key):
    return _alt(pattern_sets, lambda ps: ps.get("shared", {}).get(key))


# ---------------------------------------------------------------- helpers

def spread(items, k):
    """Take k items evenly across the window. Taking the first k quotes the beginning of the
    period only, and the end of the period is where change would show."""
    if k <= 0 or not items:
        return []
    if len(items) <= k:
        return list(items)
    step = (len(items) - 1) / (k - 1) if k > 1 else 0
    return [items[int(round(i * step))] for i in range(k)]


def quote(m, limit=240):
    return {"ts": m["ts"][:16], "session": m["session"], "source": m["source"],
            "chars": len(m["text"]), "paste": m["paste"], "text": m["text"][:limit]}


def rate(n, d):
    return {"n": n, "denom": d, "pct": round(100 * n / d, 1) if d else None}


# ---------------------------------------------------------------- measurement

def measure(msgs, pattern_sets, cfg, samples=SAMPLES_PER_SIGNAL):
    """Count signals over the operator's own words. Returns None when there is nothing to read."""
    own = [m for m in msgs if not m["paste"]]
    pasted = [m for m in msgs if m["paste"]]
    if not own:
        return None

    types = []
    for tid in type_order(pattern_sets):
        entry = {"id": tid,
                 "label": type_meta(pattern_sets, tid, "label", tid),
                 "label_en": type_meta(pattern_sets, tid, "label_en", tid),
                 "gloss": type_meta(pattern_sets, tid, "gloss"),
                 "reaction": type_meta(pattern_sets, tid, "reaction"),
                 "signals": {}, "quotes": {}}
        names = signal_names(pattern_sets, tid)
        if not names:
            entry["signals"] = None
            entry["reason"] = type_meta(pattern_sets, tid, "reason")
        else:
            for name in names:
                rx = _alt(pattern_sets,
                          lambda ps, n=name: (ps.get("types", {}).get(tid) or {})
                          .get("signals", {}).get(n))
                hits = [m for m in own if rx and rx.search(m["text"])]
                entry["signals"][name] = rate(len(hits), len(own))
                entry["quotes"][name] = [quote(m) for m in spread(hits, samples)]
        types.append(entry)

    result = {
        "signals_version": SIGNALS_VERSION,
        "corpus_version": corpus.CORPUS_VERSION,
        "window": {"from": own[0]["ts"][:16], "to": own[-1]["ts"][:16]},
        "own": len(own),
        "scanned": len(msgs),
        "sessions": len({m["session"] for m in own}),
        "length": {"median": int(statistics.median([len(m["text"]) for m in own])),
                   "max": max(len(m["text"]) for m in own)},
        "authorship": {
            "own": len(own),
            "paste_suspect": rate(len(pasted), len(msgs)),
            "by_kind": {k: sum(1 for m in pasted if m["paste"] == k)
                        for k in ("structured", "attributed")},
            "samples": [quote(m, 120) for m in spread(pasted, samples)],
            "limit": "Pasted plain prose that names no source is still counted as the operator's.",
        },
        "types": types,
        "borrowed": _borrowed(own, msgs, pattern_sets, cfg),
        "caveat": "Regex hits are candidates. Read the originals before any of this becomes a verdict.",
    }
    return result


def _borrowed(own, allmsgs, pattern_sets, cfg):
    """Three cross-cutting metrics. Each is reported twice -- over every extracted message, and
    over the operator's own words only -- because the difference is where pasted text shows up.
    Measured on the source corpus: 26.9% vs 100% for the same period."""
    out = {}
    vague, concrete = shared_rx(pattern_sets, "vague_ref"), shared_rx(pattern_sets, "concrete")
    req, acc = shared_rx(pattern_sets, "request"), shared_rx(pattern_sets, "acceptance")
    corr = shared_rx(pattern_sets, "correction") or _alt(
        pattern_sets, lambda ps: (ps.get("types", {}).get("sousa") or {})
        .get("signals", {}).get("correction"))

    for label, pool in (("all", allmsgs), ("own", own)):
        short = [m for m in pool if len(m["text"]) <= cfg["short_chars"]
                 and vague and vague.search(m["text"])
                 and not (concrete and concrete.search(m["text"]))]
        requests = [m for m in pool if req and req.search(m["text"])]
        with_acc = [m for m in requests if acc and acc.search(m["text"])]
        out.setdefault("telegraphic", {})[label] = rate(len(short), len(pool))
        out.setdefault("acceptance_in_request", {})[label] = rate(len(with_acc), len(requests))
        out.setdefault("correction_oneshot", {})[label] = _oneshot(pool, corr)
    out["telegraphic_samples"] = [quote(m, 120) for m in spread(
        [m for m in own if len(m["text"]) <= cfg["short_chars"]
         and vague and vague.search(m["text"])
         and not (concrete and concrete.search(m["text"]))], SAMPLES_PER_SIGNAL)]
    return out


def _oneshot(pool, corr_rx):
    """Share of corrections that landed in one go. A correction followed closely by another
    correction is the shape of a mismatch that took several rounds to clear."""
    if corr_rx is None:
        return rate(0, 0)
    by_session = defaultdict(list)
    for m in sorted(pool, key=lambda x: (x["session"], x["ts"])):
        by_session[m["session"]].append(m)
    total = chained = 0
    for ms in by_session.values():
        idx = [i for i, m in enumerate(ms) if corr_rx.search(m["text"])]
        total += len(idx)
        chained += sum(1 for i in idx
                       if any(i != j and abs(i - j) <= CORRECTION_CHAIN_GAP for j in idx))
    return rate(total - chained, total)


# ---------------------------------------------------------------- the interview

def open_questions(result, pattern_sets, cfg):
    """What a regex cannot settle, written as questions. `blocking` gates the verdict."""
    qs = []
    probes = {}
    observe = {}
    for ps in pattern_sets:
        for tid, text in (ps.get("probes") or {}).items():
            probes.setdefault(tid, text)
        for tid, text in (ps.get("observe") or {}).items():
            observe.setdefault(tid, text)

    for t in result["types"]:
        tid = t["id"]
        pool = [q for qs_ in (t["quotes"] or {}).values() for q in qs_]
        # de-duplicate: one message can hit several signals of the same type
        uniq = {(q["ts"], q["text"][:40]): q for q in pool}
        quotes = list(uniq.values())

        if len(quotes) < QUOTES_FOR_VERDICT:
            qs.append({
                "id": "probe_%s" % tid,
                "kind": "probe",
                "type": tid,
                "why": ("The corpus produced %d quote(s) for %s; a verdict needs %d."
                        % (len(quotes), t["label_en"] or tid, QUOTES_FOR_VERDICT)),
                "ask": probes.get(tid, "Show me this aptitude in one concrete answer."),
                "observe": observe.get(tid, ""),
                "answer_format": "pass | fail  + one line on what you observed",
                "blocking": t["signals"] is not None,
            })

        for q in quotes:
            if q["paste"] or q["chars"] >= cfg["paste_min_chars"]:
                qs.append({
                    "id": "auth_%s_%s" % (tid, q["ts"].replace(":", "").replace("-", "")),
                    "kind": "authorship",
                    "type": tid,
                    "why": "Long enough to have been pasted from somewhere else (%d chars%s)."
                           % (q["chars"], ", flagged " + q["paste"] if q["paste"] else ""),
                    "ask": "Did you write this yourself? — %s" % q["text"][:120],
                    "observe": "",
                    "answer_format": "yes | no",
                    "blocking": True,
                    # answering "no" revokes this quote in water_divination.py -- the question
                    # has to be able to point at what it disqualifies
                    "quote_ref": {"type": tid, "ts": q["ts"]},
                })

        for name, s in (t["signals"] or {}).items():
            if s["n"] == 0:
                qs.append({
                    "id": "occ_%s_%s" % (tid, name),
                    "kind": "occasion",
                    "type": tid,
                    "why": "`%s` is zero. Zero means no ability or no opportunity, and only "
                           "you know which." % name,
                    "ask": "In this period, did the work ever call for %s (%s)?"
                           % (name, t["gloss"][:60]),
                    "observe": "",
                    "answer_format": "had-occasion | no-occasion",
                    "blocking": False,
                })

    if result["authorship"]["paste_suspect"]["n"]:
        qs.append({
            "id": "auth_corpus",
            "kind": "authorship",
            "type": None,
            "why": "%d message(s) look pasted and were excluded from every count."
                   % result["authorship"]["paste_suspect"]["n"],
            "ask": "Were those exclusions right? Anything there that was actually yours?",
            "observe": "",
            "answer_format": "ok | list the ones that were mine",
            "blocking": False,
        })
    return qs


def provisional_ranking(result):
    """Order the types by how much evidence exists, so the interview knows where the stakes are.
    Explicitly not a verdict: it ranks regex hits, and regex hits are candidates."""
    scored = []
    for t in result["types"]:
        if t["signals"] is None:
            continue
        n = sum(s["n"] for s in t["signals"].values())
        strongest = max(t["signals"].items(), key=lambda kv: kv[1]["n"])[0] if t["signals"] else ""
        scored.append({"id": t["id"], "label": t["label"], "label_en": t["label_en"],
                       "hits": n, "strongest": strongest})
    scored.sort(key=lambda s: -s["hits"])
    return scored


# ---------------------------------------------------------------- self-test

def _self_test():
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pats = load_patterns(["patterns/en.json", "patterns/ja.json"], base=here)
    check("both shipped pattern files load", len(pats) == 2)
    check("every type in one file exists in the other",
          set(pats[0]["types"]) == set(pats[1]["types"]),
          str(set(pats[0]["types"]) ^ set(pats[1]["types"])))
    check("every type has a probe in every language",
          all(set(ps["types"]) <= set(ps["probes"]) for ps in pats))

    cfg = corpus.load_config()

    def msg(text, ts, session="s1", paste=None):
        return {"ts": ts, "session": session, "text": text, "source": "fixture", "paste": paste}

    msgs = [
        msg("from now on, always add the evidence line", "2026-08-01T10:00"),
        msg("no, that's wrong -- i meant the other one", "2026-08-02T10:00"),
        msg("think of it as a funnel, the way a mail client does it", "2026-08-03T10:00"),
        msg("the goal is one clean pass; you must not drop the constraint", "2026-08-04T10:00"),
        msg("please fix the parser; it's done when the tests pass", "2026-08-05T10:00"),
        msg("i want it to end up feeling like a single page", "2026-08-06T10:00"),
        msg("## Verdict\n**NOT READY**\n" + "body. " * 80, "2026-08-07T10:00", paste="structured"),
    ]
    r = measure(msgs, pats, cfg)
    check("pasted message is out of the denominator", r["own"] == 6 and r["scanned"] == 7,
          "own=%s scanned=%s" % (r["own"], r["scanned"]))

    def sig(tid, name):
        return next(t for t in r["types"] if t["id"] == tid)["signals"][name]["n"]

    check("EN rulemaking is detected", sig("sousa", "rulemaking") >= 1)
    check("EN correction is detected", sig("sousa", "correction") >= 1)
    check("EN metaphor is detected", sig("henka", "metaphor") >= 1)
    check("EN constraint is detected", sig("kyouka", "constraint") >= 1)
    check("EN finished image is detected", sig("houshutsu", "finished_image") >= 1)
    check("Specialist carries no detector",
          next(t for t in r["types"] if t["id"] == "tokushitsu")["signals"] is None)
    check("acceptance-in-request is borrowed both ways",
          r["borrowed"]["acceptance_in_request"]["own"]["n"] == 1,
          str(r["borrowed"]["acceptance_in_request"]))

    ja = [msg("今後は毎回、証拠行を書くルールにして", "2026-08-01T10:00"),
          msg("そうじゃなくて、こっちのファイルの話", "2026-08-02T10:00"),
          msg("スライムみたいにボヨンと潰れる感じにしたい", "2026-08-03T10:00")]
    rja = measure(ja, pats, cfg)

    def sja(tid, name):
        return next(t for t in rja["types"] if t["id"] == tid)["signals"][name]["n"]

    check("JA and EN patterns coexist in one regex",
          sja("sousa", "rulemaking") == 1 and sja("houshutsu", "finished_image") == 1,
          "rule=%d img=%d" % (sja("sousa", "rulemaking"), sja("houshutsu", "finished_image")))

    qs = open_questions(r, pats, cfg)
    kinds = {q["kind"] for q in qs}
    check("a thin type produces a probe question", "probe" in kinds)
    check("probe questions carry the language's own wording",
          any(q["ask"] and q["kind"] == "probe" for q in qs))
    check("a zero signal produces an occasion question, non-blocking",
          any(q["kind"] == "occasion" and not q["blocking"] for q in qs))
    check("Specialist's probe never blocks a verdict",
          all(q["blocking"] is False for q in qs
              if q["kind"] == "probe" and q["type"] == "tokushitsu"))

    long_own = [msg("i want " + "the same shape repeated, " * 30, "2026-08-01T10:00")]
    qs2 = open_questions(measure(long_own, pats, cfg), pats, cfg)
    check("a long quote triggers an authorship question",
          any(q["kind"] == "authorship" and q["blocking"] for q in qs2))

    check("ranking is by evidence, and says so",
          provisional_ranking(r)[0]["hits"] >= provisional_ranking(r)[-1]["hits"])

    check("empty corpus measures to nothing, not to zeros", measure([], pats, cfg) is None)

    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="signal counts for the water divination")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    cfg = corpus.load_config(args.config)
    base = cfg.get("_base") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pats = load_patterns(cfg["patterns"], base)
    attrib = corpus.build_attribution_rx(pats)
    msgs, report = corpus.collect(cfg, args.since, args.until, attrib)
    r = measure(msgs, pats, cfg)

    print("[nen-signals] alive: scanned=%d own=%d version=%s"
          % (len(msgs), r["own"] if r else 0, SIGNALS_VERSION))
    print(corpus.format_scan_report(report))
    if r is None:
        print("nothing to read in that window (exit 2)")
        return 2
    if args.json_out:
        with io.open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
    for t in r["types"]:
        print("\n[%s / %s] %s" % (t["label"], t["label_en"], t["reaction"]))
        if t["signals"] is None:
            print("   no detector by design: %s" % t["reason"][:100])
        for name, s in (t["signals"] or {}).items():
            print("   %-16s %5s%%  (%d)" % (name, s["pct"], s["n"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
