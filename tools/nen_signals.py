# -*- coding: utf-8 -*-
"""nen_signals — count the six aptitudes' signals, and list what still has to be asked.

Two outputs, and the second one is the point.

**Signals.** For each of six types, how often the operator's own messages carry the marks of that
type, plus quotes to check. These are candidates. On the corpus this was built against, 40% of one
detector's hits were false positives -- fiction dialogue and spec text that happened to contain a
correction word. A number here is a reason to go read the original, not a finding.

**Effects.** Whether exercising an aptitude changed anything, on six axes that each have their own
outcome, denominator and unit -- see the comment above `measure_effects` for why one shared outcome
cannot work. Plus the rare-event catalogue, which is how Specialist is measured: not a rate, but
conjunctions that are hard to satisfy by accident.

**Open questions.** The gap between what a regex can see and what a verdict needs, written as
questions someone can actually answer:

- `probe` -- the corpus could not produce two quotes for this type, so ask directly and watch the
  shape of the answer
- `authorship` -- a quote heavy enough to carry a verdict is long enough to have been pasted
- `occasion` -- a signal or an axis sits at zero, and zero has two meanings: no ability, or no
  opportunity. Only the person can say which, and the difference decides whether it is a weakness.
- `attribution` -- an axis produced a rate; were the cases it counted the same kind of work?
- `rare` -- a rare event fired; was it deliberate?

Questions marked `blocking` are the ones a verdict may not be issued without. That gate lives in
water_divination.py, which refuses to print a verdict while any blocking question is unanswered.

特質系 (Specialist) has no *signal* detector on purpose. Its definition is "the combination the
other five cannot explain", so any regex scoring it would grant it to everybody; it is reached
through the rare-event catalogue instead.

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
    """Works for both shapes we carry: corpus messages and timeline events (which have no
    `source`/`paste` because the timeline reads whole sessions, not just your messages)."""
    return {"ts": m["ts"][:16], "session": m["session"], "source": m.get("source", ""),
            "chars": len(m["text"]), "paste": m.get("paste"), "text": m["text"][:limit]}


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


# ---------------------------------------------------------------- effect

MIN_N = 4             # observations an axis needs before it reports a rate at all
LOOKAHEAD_TOOLS = 60  # cap on tool calls counted between two of your messages

# Each aptitude gets its **own outcome variable**, with its own denominator and its own unit.
#
# The first version of this layer scored all five detectable types against one shared outcome --
# whether your next message was a correction -- and split the population by which vocabulary the
# request carried. Every type then came out within a few points of every other, all in the same
# direction, because that design measures one thing five times: longer requests carry more of
# every vocabulary and are harder. Adjusting for length would have papered over a structural
# fault. Six aptitudes need six quantities that can move independently, or the profile has no
# shape to read.
#
#   Enhancer     sessions that stated a constraint early -> ran to the end without a correction
#   Emitter      your requests -> the agent started work instead of asking you what you meant
#   Transmuter   session topics that began vague -> a checkable criterion appeared later
#   Conjurer     requests carrying a finish line -> the agent actually showed it had verified
#   Manipulator  rules you declared -> written into a rule file, and not repeated afterwards
#   Specialist   no machine axis, same as its signal: it is the combination the others can't
#                explain, so any quantity invented for it would grant it to everyone.


def measure_effects(events, pattern_sets, cfg, blind_sources=()):
    """Six independent axes, plus the rare-event catalogue.

    Every axis has its own outcome, its own denominator and its own unit, so they can move
    independently of each other. An axis with fewer than MIN_N observations reports `None` and
    says how many it had, rather than a rate computed from three data points.
    """
    rx = {name: shared_rx(pattern_sets, name)
          for name in ("request", "correction", "acceptance")}
    for name in ("vague", "concrete_criterion"):
        rx[name] = _alt(pattern_sets, lambda ps, n=name: ps.get("axes", {}).get(n))
    rx["constraint"] = _alt(pattern_sets, lambda ps: (ps.get("types", {}).get("kyouka") or {})
                            .get("signals", {}).get("constraint"))
    rx["rulemaking"] = _alt(pattern_sets, lambda ps: (ps.get("types", {}).get("sousa") or {})
                            .get("signals", {}).get("rulemaking"))
    if rx["correction"] is None:
        rx["correction"] = _alt(pattern_sets, lambda ps: (ps.get("types", {}).get("sousa") or {})
                                .get("signals", {}).get("correction"))

    by_session = defaultdict(list)
    for e in events:
        by_session[e["session"]].append(e)

    axes = {
        "kyouka": _axis_constraint_survival(by_session, rx),
        "houshutsu": _axis_started_without_asking(by_session, rx),
        "henka": _axis_vague_to_criterion(by_session, rx),
        "gugenka": _axis_finish_line_verified(by_session, rx),
        "sousa": _axis_rules_that_stuck(by_session, rx),
    }
    rare = _rare_events(by_session, rx)

    agent_turns = sum(1 for e in events if e["kind"] == "assistant")
    misreads = sum(1 for e in events if e["misread"])
    halves = _misread_halves(events)
    return {
        "axes": axes,
        "rare": rare,
        "assistant_turns": agent_turns,
        "misreads": {
            "n": misreads,
            "per_100_agent_turns": round(100.0 * misreads / agent_turns, 2)
            if agent_turns else None,
            "first_half": halves[0], "second_half": halves[1],
            "note": "Counted from the agent admitting it read something wrong. It cannot see a "
                    "misread nobody noticed, so a fall can mean fewer misreads or less candour.",
        },
        "blind_sources": list(blind_sources),
        "caveat": "Each axis is an association inside your own corpus, not a cause and not a "
                  "comparison with anyone else. The interview asks, per axis, whether the two "
                  "sides were the same kind of work.",
    }


# One place the axes are described, so the diagram generator and the report cannot drift from
# what the code actually counts.
AXES = {
    "kyouka": ("sessions that held their constraint", "sessions",
               "A constraint you stated, and no correction in the rest of that session."),
    "houshutsu": ("requests the agent could act on directly", "requests",
                  "No clarifying question from the agent before it started."),
    "henka": ("fuzzy starts that became checkable", "vague openings",
              "'Something is off' followed, in the same session, by a criterion someone else "
              "could apply."),
    "gugenka": ("finish lines the agent actually checked against", "requests with a finish line",
                "You said what done means, and the agent came back with evidence rather than "
                "a claim."),
    "sousa": ("rules that became machinery", "rules declared",
              "Followed, in the same session, by a write into a rule file, hook or config."),
}


def axis_catalogue():
    """[(type id, label, unit, detail)] -- what each axis counts, for anything that documents it."""
    return [(tid,) + AXES[tid] for tid in AXES]


def _axis(tid, hits, total, evidence=None):
    label, unit, detail = AXES[tid]
    return {"label": label, "unit": unit, "n": total, "hits": hits,
            "pct": round(100.0 * hits / total, 1) if total >= MIN_N else None,
            "enough": total >= MIN_N, "detail": detail,
            "evidence": evidence or []}


def _users(evs):
    """Indices of messages that are yours. Pasted text is skipped here for the same reason the
    signal layer skips it: an effect credited to someone else's words is credited to the wrong
    person, and the rare-event catalogue is where that mistake would be loudest."""
    return [i for i, e in enumerate(evs) if e["kind"] == "user" and not e.get("paste")]


def _axis_constraint_survival(by_session, rx):
    """Enhancer: you named a constraint early; did the session then run without a correction?

    Denominator is sessions, not messages -- holding a constraint is a property of a stretch of
    work, and nothing else here is measured per session."""
    total = clean = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        if len(idx) < 3:
            continue
        # The constraint has to be stated with enough of the session left for holding it to mean
        # anything, but requiring the *first third* threw away most sessions -- constraints often
        # arrive once the work has started. Anything before the final third counts, and what is
        # measured is the stretch after it.
        cutoff = len(idx) - max(1, len(idx) // 3)
        stated = next((p for p in range(cutoff)
                       if rx["constraint"] and rx["constraint"].search(evs[idx[p]]["text"])), None)
        if stated is None:
            continue
        total += 1
        rest = idx[stated + 1:]
        if not any(rx["correction"] and rx["correction"].search(evs[i]["text"]) for i in rest):
            clean += 1
            if len(ev) < 3:
                ev.append(quote(evs[idx[stated]], 160))
    return _axis("kyouka", clean, total, ev)


def _axis_started_without_asking(by_session, rx):
    """Emitter: after your request, did the agent get to work, or ask you what you meant?

    A clarifying question is the agent telling you the finished picture did not arrive."""
    total = started = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        for pos, i in enumerate(idx):
            if not (rx["request"] and rx["request"].search(evs[i]["text"])):
                continue
            nxt = idx[pos + 1] if pos + 1 < len(idx) else len(evs)
            span = evs[i + 1:nxt]
            total += 1
            if not any(e["kind"] == "assistant" and e["question"] for e in span):
                started += 1
            elif len(ev) < 3:
                ev.append(quote(evs[i], 160))
    return _axis("houshutsu", started, total, ev)


def _axis_vague_to_criterion(by_session, rx):
    """Transmuter: a topic that began as a feeling -- did you turn it into something checkable?

    Denominator is stretches that started vague, so it cannot be raised by never being vague."""
    total = converted = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        for pos, i in enumerate(idx):
            if not (rx["vague"] and rx["vague"].search(evs[i]["text"])):
                continue
            total += 1
            later = [evs[j]["text"] for j in idx[pos + 1:]]
            if any(rx["concrete_criterion"] and rx["concrete_criterion"].search(t)
                   for t in later):
                converted += 1
                if len(ev) < 3:
                    ev.append(quote(evs[i], 160))
    return _axis("henka", converted, total, ev)


def _axis_finish_line_verified(by_session, rx):
    """Conjurer: you wrote what done looks like -- did the agent then show it had checked?

    This tests the prescription this whole tool argues for, against the tool's own corpus."""
    total = verified = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        for pos, i in enumerate(idx):
            t = evs[i]["text"]
            if not (rx["request"] and rx["request"].search(t)
                    and rx["acceptance"] and rx["acceptance"].search(t)):
                continue
            nxt = idx[pos + 1] if pos + 1 < len(idx) else len(evs)
            total += 1
            if any(e["kind"] == "assistant" and e["verify"] for e in evs[i + 1:nxt]):
                verified += 1
                if len(ev) < 3:
                    ev.append(quote(evs[i], 160))
    return _axis("gugenka", verified, total, ev)


def _axis_rules_that_stuck(by_session, rx):
    """Manipulator: of the rules you declared, how many stopped depending on memory?

    Written into a rule file, hook or config later in the same session. A rule that lives only
    in the transcript has to be said again next time, which is the thing steering is supposed
    to end."""
    total = mechanised = 0
    ev = []
    for evs in by_session.values():
        for i in _users(evs):
            if not (rx["rulemaking"] and rx["rulemaking"].search(evs[i]["text"])):
                continue
            total += 1
            if any(e["kind"] == "tool" and e["mechanism"] for e in evs[i + 1:]):
                mechanised += 1
                if len(ev) < 3:
                    ev.append(quote(evs[i], 160))
    return _axis("sousa", mechanised, total, ev)


# ---------------------------------------------------------------- rare events
# 特質系 is the type you cannot train into. Measuring it as a rate would hand it to everyone, so
# it is not a rate: it is a catalogue of conjunctive events that are hard to satisfy by accident.
# Each one needs three or four separate things to line up in the right order. Finding one is the
# point -- the report names it and shows the moment, because that is the interesting part of a
# reading, not another percentage.
#
# Honest limit: "rare" here means rare **by construction**, not rare compared with other people.
# There is no cross-operator baseline in this repo and inventing one would be a fabrication.

RARE_EVENTS = [
    ("mechanised_lesson", "A lesson that became machinery",
     "A correction, then a rule, then that rule written into a file, hook or config -- all in "
     "one session. The failure stopped depending on anyone remembering it."),
    ("externalised_sense", "A feeling turned into a check",
     "'Something is off', then a criterion someone else could apply, then the agent verifying "
     "against it. The whole path from taste to test, in one stretch."),
    ("confluence", "Separate sources woven into one thing",
     "Material you pasted from elsewhere, your own instruction, and a write into a durable "
     "artifact -- combined in a single session rather than handled one at a time."),
    ("invited_refutation", "Asking to be proven wrong before starting",
     "You asked for a counter-example or an objection to your own framing before the work "
     "began, rather than after it failed."),
]

REFUTATION_RX = r"(反例|反証|否定側|逆に言うと.{0,10}おかしい|穴があれば|間違っていたら教えて|" \
                r"counter-?example|argue against|prove me wrong|poke holes|what would break)"


STEP_GAP = 6      # messages of yours the next step must land within, or the chain is not one act


def _rare_events(by_session, rx):
    """Return the rare events that actually fired, each with the moment it happened.

    Two rules keep these rare instead of merely frequent. The steps must land **in order and
    close together** -- a correction on Monday and a rule on Friday are two things that happened,
    not one act -- and a session may contribute **at most one** of each, so a long session cannot
    manufacture a streak. The first version of this ignored both and reported 41 "rare" events in
    a month, which is a counter, not a find.
    """
    import re as _re
    refute = _re.compile(REFUTATION_RX)
    found = {key: {"key": key, "label": label, "definition": defn, "n": 0, "evidence": []}
             for key, label, defn in RARE_EVENTS}

    for evs in by_session.values():
        idx = _users(evs)
        pos_of = {i: p for p, i in enumerate(idx)}

        def step(pred, after_pos=-1):
            """First of your messages matching pred, within STEP_GAP messages of the last step."""
            for p in range(after_pos + 1, len(idx)):
                if after_pos >= 0 and p - after_pos > STEP_GAP:
                    return None
                if pred(evs[idx[p]]["text"]):
                    return p
            return None

        def tool_after(p, pred):
            start = idx[p]
            stop = idx[p + STEP_GAP] if p + STEP_GAP < len(idx) else len(evs)
            return any(pred(e) for e in evs[start + 1:stop])

        c = step(lambda t: bool(rx["correction"] and rx["correction"].search(t)))
        if c is not None:
            r = step(lambda t: bool(rx["rulemaking"] and rx["rulemaking"].search(t)), c)
            if r is not None and tool_after(r, lambda e: e["kind"] == "tool" and e["mechanism"]):
                _hit(found["mechanised_lesson"], evs[idx[r]])

        v = step(lambda t: bool(rx["vague"] and rx["vague"].search(t)))
        if v is not None:
            k = step(lambda t: bool(rx["concrete_criterion"]
                                    and rx["concrete_criterion"].search(t)), v)
            if k is not None and tool_after(k, lambda e: e["kind"] == "assistant" and e["verify"]):
                _hit(found["externalised_sense"], evs[idx[v]])

        # confluence needs material you brought in from elsewhere AND your own instruction close
        # to it AND something durable written -- all three inside one stretch, not one session
        for p, i in enumerate(idx):
            if not (rx["request"] and rx["request"].search(evs[i]["text"])):
                continue
            near = evs[max(0, i - 3):i]
            brought_in = any(e["kind"] == "user" and e.get("paste") for e in near)
            if brought_in and tool_after(p, lambda e: e["kind"] == "tool" and e["mechanism"]):
                _hit(found["confluence"], evs[i])
                break

        rf = step(lambda t: bool(refute.search(t)))
        if rf is not None:
            _hit(found["invited_refutation"], evs[idx[rf]])

    return [f for f in found.values() if f["n"]]


def _hit(entry, event):
    entry["n"] += 1
    if len(entry["evidence"]) < 3:
        entry["evidence"].append(quote(event, 200))


def _misread_halves(events):
    """Direction of travel. Split by position, not by date: a corpus is rarely evenly spread."""
    agent = [e for e in events if e["kind"] == "assistant"]
    if len(agent) < 20:
        return (None, None)
    mid = len(agent) // 2
    out = []
    for part in (agent[:mid], agent[mid:]):
        hits = sum(1 for e in part if e["misread"])
        out.append({"n": hits, "per_100": round(100.0 * hits / len(part), 2)})
    return tuple(out)


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

    for tid, ax in (result.get("effects", {}).get("axes") or {}).items():
        t = next((x for x in result["types"] if x["id"] == tid), None)
        label = (t or {}).get("label_en") or tid
        if not ax["enough"]:
            qs.append({
                "id": "occ_axis_%s" % tid,
                "kind": "occasion",
                "type": tid,
                "why": "The %s axis had only %d observation(s), too few to rate."
                       % (label, ax["n"]),
                "ask": "Did this period simply not call for %s, or did you not reach for it?"
                       % ax["label"],
                "observe": "",
                "answer_format": "no occasion | did not reach for it",
                "blocking": False,
            })
            continue
        qs.append({
            "id": "attr_%s" % tid,
            "kind": "attribution",
            "type": tid,
            "why": "%s: %d of %d %s (%s%%). %s"
                   % (label, ax["hits"], ax["n"], ax["unit"], ax["pct"], ax["detail"]),
            "ask": "Were those %s the same kind of work as the rest — or the ones you already "
                   "understood well?" % ax["unit"],
            "observe": "A number that only holds on easy work is not an aptitude.",
            "answer_format": "same kind | the easier ones | the harder ones",
            "blocking": True,
        })

    for r in (result.get("effects", {}).get("rare") or []):
        qs.append({
            "id": "rare_%s" % r["key"],
            "kind": "rare",
            "type": "tokushitsu",
            "why": "%s — fired %d time(s). %s" % (r["label"], r["n"], r["definition"]),
            "ask": "Was this deliberate, or did it happen to fall out that way?",
            "observe": "Specialist is recognised on the deliberate ones. Confirm it with the "
                       "moment shown, not with the count.",
            "answer_format": "deliberate | accident | not what happened",
            "blocking": True,
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


def audit_patterns(pattern_sets, texts):
    """Fire every pattern at text that is *not* somebody instructing an agent, and count.

    Sensitivity -- does a pattern catch the thing it is named for -- can only be measured against
    a real corpus of the language in question. Specificity can be measured against any prose: a
    pattern that fires on ordinary writing will also fire on ordinary messages, and its count then
    means nothing. This is how a pattern set written for a language nobody has measured can still
    be held to something.

    Returns hits per pattern over the supplied texts. High is bad, except for the one pattern
    whose job is to match broadly: `concrete` exists to notice that a message contains *any*
    identifier or number, and it is used as a negative guard, so matching everywhere is correct.
    """
    rows = []
    for ps in pattern_sets:
        lang = ps.get("language", "?")
        groups = [("types.%s" % tid, (t or {}).get("signals") or {})
                  for tid, t in (ps.get("types") or {}).items()]
        groups += [("shared", ps.get("shared") or {}), ("axes", ps.get("axes") or {}),
                   ("effects", ps.get("effects") or {})]
        for where, table in groups:
            for name, pat in table.items():
                if name.startswith("_") or not isinstance(pat, str):
                    continue
                try:
                    rx = re.compile("(?i:%s)" % pat if ps.get("case_insensitive") else pat)
                except re.error as exc:
                    rows.append({"lang": lang, "where": where, "name": name,
                                 "hits": None, "error": str(exc)})
                    continue
                hits = sum(1 for t in texts if rx.search(t))
                rows.append({"lang": lang, "where": where, "name": name, "hits": hits,
                             "broad_by_design": name in BROAD_BY_DESIGN,
                             "pct": round(100.0 * hits / len(texts), 1) if texts else None})
    return rows


BROAD_BY_DESIGN = {"concrete"}


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

    # -- the effect layer: six axes that have to be able to disagree with each other -------
    def ev(kind, text="", **kw):
        e = {"ts": "2026-08-01T10:00", "session": kw.pop("s", "e1"), "kind": kind,
             "text": text, "tool": "", "mechanism": False,
             "misread": False, "question": False, "verify": False, "paste": None}
        e.update(kw)
        return e

    tl = []
    # a session that names a constraint early and never gets corrected
    tl += [ev("user", "you must not drop the constraint", s="s1"), ev("assistant", s="s1"),
           ev("user", "please continue", s="s1"), ev("user", "please finish it", s="s1")]
    # a session that names one and does get corrected
    tl += [ev("user", "this is a requirement, always", s="s2"), ev("assistant", s="s2"),
           ev("user", "keep going", s="s2"), ev("user", "no, that's wrong", s="s2")]
    # a request the agent acted on, and one it asked about
    tl += [ev("user", "please build the loader", s="s3"), ev("assistant", s="s3"),
           ev("user", "please build the parser", s="s3"),
           ev("assistant", question=True, s="s3")]
    # a finish line the agent verified, and one it did not
    tl += [ev("user", "please fix it, done when tests pass", s="s4"),
           ev("assistant", verify=True, s="s4"),
           ev("user", "please ship it, done when tests pass", s="s4"),
           ev("assistant", s="s4")]
    # a declared rule that reached a rule file, and one that did not
    tl += [ev("user", "from now on print the diff", s="s5"),
           ev("tool", tool="Edit", mechanism=True, s="s5"),
           ev("user", "from now on ask first", s="s6"), ev("assistant", s="s6")]
    eff = measure_effects(tl, pats, cfg)
    ax = eff["axes"]
    check("Enhancer axis counts sessions, not messages",
          ax["kyouka"]["n"] == 2 and ax["kyouka"]["hits"] == 1, str(ax["kyouka"]))
    # every "please ..." in the fixture is a request, across all four sessions; exactly one of
    # them is followed by the agent asking what was meant
    check("Emitter axis counts requests the agent did not have to ask about",
          ax["houshutsu"]["n"] == 6 and ax["houshutsu"]["hits"] == 5, str(ax["houshutsu"]))
    check("Conjurer axis counts only requests that carried a finish line",
          ax["gugenka"]["n"] == 2 and ax["gugenka"]["hits"] == 1, str(ax["gugenka"]))
    check("Manipulator axis counts rules that reached a file",
          ax["sousa"]["n"] == 2 and ax["sousa"]["hits"] == 1, str(ax["sousa"]))
    check("an axis below the minimum reports its count instead of a rate",
          ax["henka"]["enough"] is False and ax["henka"]["pct"] is None, str(ax["henka"]))
    check("the axes disagree with each other, which one shared outcome could not",
          len({ax[k]["hits"] for k in ("kyouka", "houshutsu", "gugenka", "sousa")}) > 1)

    pasted_rule = [ev("user", "from now on print the diff", s="p1", paste="structured"),
                   ev("tool", tool="Edit", mechanism=True, s="p1")]
    check("a rule you pasted from somewhere else is not your steering",
          measure_effects(pasted_rule, pats, cfg)["axes"]["sousa"]["n"] == 0)

    # -- rare events: order and proximity are the whole definition ------------------------
    chain = [ev("user", "no, that's wrong", s="r1"),
             ev("user", "from now on print the diff", s="r1"),
             ev("tool", tool="Edit", mechanism=True, s="r1")]
    got = {r["key"]: r for r in measure_effects(chain, pats, cfg)["rare"]}
    check("a correction, then a rule, then a rule file = one rare find",
          got.get("mechanised_lesson", {}).get("n") == 1, str(list(got)))
    check("the rare find carries the moment, not just a count",
          bool(got["mechanised_lesson"]["evidence"][0]["text"]))

    far = ([ev("user", "no, that's wrong", s="r2")]
           + [ev("user", "please carry on", s="r2") for _ in range(STEP_GAP + 2)]
           + [ev("user", "from now on print the diff", s="r2"),
              ev("tool", tool="Edit", mechanism=True, s="r2")])
    check("the same steps far apart are two events, not one act",
          not any(r["key"] == "mechanised_lesson"
                  for r in measure_effects(far, pats, cfg)["rare"]))

    reversed_order = [ev("user", "from now on print the diff", s="r3"),
                      ev("tool", tool="Edit", mechanism=True, s="r3"),
                      ev("user", "no, that's wrong", s="r3")]
    check("the steps out of order do not count",
          not any(r["key"] == "mechanised_lesson"
                  for r in measure_effects(reversed_order, pats, cfg)["rare"]))

    long_session = chain * 4
    check("one session contributes at most one of each rare event",
          measure_effects(long_session, pats, cfg)["rare"][0]["n"] == 1)

    # -- pattern audit: specificity is measurable even where sensitivity is not ------------
    rows = audit_patterns(pats, ["the quick brown fox", "nothing here matches anything"])
    check("the audit reports every pattern in every language",
          len(rows) >= 40 and {r["lang"] for r in rows} == {"en", "ja"}, str(len(rows)))
    check("a pattern that matches nothing scores zero",
          any(r["hits"] == 0 for r in rows))
    loose = audit_patterns(pats, ["you must not do that", "you must not do that either"])
    con = next(r for r in loose if r["name"] == "constraint" and r["lang"] == "en")
    check("a pattern that fires on ordinary prose is caught by the audit",
          con["hits"] == 2 and con["pct"] == 100.0, str(con))
    check("the one deliberately broad pattern is marked, not reported as a fault",
          all(r["broad_by_design"] for r in rows if r["name"] == "concrete"))

    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="signal counts for the water divination")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--audit-patterns", metavar="DIR",
                    help="fire every pattern at ordinary prose (.md/.txt) and report what sticks; "
                         "a pattern that matches writing nobody aimed at an agent is too loose")
    ap.add_argument("--config")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if args.audit_patterns:
        import glob as _glob
        cfg = corpus.load_config(args.config)
        pats = load_patterns(cfg["patterns"])
        paras = []
        for path in sorted(_glob.glob(os.path.join(corpus.resolve(args.audit_patterns),
                                                   "**", "*.*"), recursive=True)):
            if os.path.splitext(path)[1].lower() not in (".md", ".txt"):
                continue
            with io.open(path, encoding="utf-8", errors="replace") as f:
                paras += [p.strip() for p in re.split(r"\n\s*\n", f.read()) if p.strip()]
        if not paras:
            print("[audit] alive: paragraphs=0 -- nothing to audit (exit 2)")
            return 2
        rows = sorted(audit_patterns(pats, paras), key=lambda r: -(r["hits"] or 0))
        print("[audit] alive: paragraphs=%d patterns=%d" % (len(paras), len(rows)))
        print("hits on prose that was never aimed at an agent (high = too loose):")
        for r in rows:
            if r.get("error"):
                print("  %-4s %-22s %-22s BAD REGEX %s"
                      % (r["lang"], r["where"], r["name"], r["error"]))
            else:
                print("  %-4s %-22s %-22s %4d  %5s%%%s"
                      % (r["lang"], r["where"], r["name"], r["hits"], r["pct"],
                         "  (broad by design)" if r["broad_by_design"] else ""))
        return 0

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
