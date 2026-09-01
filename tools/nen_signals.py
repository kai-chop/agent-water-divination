# -*- coding: utf-8 -*-
"""nen_signals — count the six aptitudes' signals, and list what still has to be asked.

Two outputs, and the second one is the point.

**Signals.** For each of six types, how often the operator's own messages carry the marks of that
type, plus quotes to check. These are candidates. On the corpus this was built against, 40% of one
detector's hits were false positives -- fiction dialogue and spec text that happened to contain a
correction word. A number here is a reason to go read the original, not a finding.

**Effects.** Whether exercising an aptitude changed anything, on six axes that each have their own
outcome, denominator and unit -- see the comment above `measure_effects` for why one shared outcome
cannot work. Plus **the residual**: the messages none of the five explain, which is where
Specialist is looked for. Nothing scores the residual; it is handed over for a reader to judge.

**Open questions.** The gap between what a regex can see and what a verdict needs, written as
questions someone can actually answer:

- `probe` -- the corpus could not produce two quotes for this type, so ask directly and watch the
  shape of the answer
- `authorship` -- a quote heavy enough to carry a verdict is long enough to have been pasted
- `occasion` -- a signal or an axis sits at zero, and zero has two meanings: no ability, or no
  opportunity. Only the person can say which, and the difference decides whether it is a weakness.
- `attribution` -- an axis produced a rate; were the cases it counted the same kind of work?
- `residual` -- here is what the five do not explain; is there anything characteristic in it?

Questions marked `blocking` are the ones a verdict may not be issued without. That gate lives in
water_divination.py, which refuses to print a verdict while any blocking question is unanswered.

特質系 (Specialist) has no detector, and gets no catalogue of "rare shapes" either -- a catalogue
would just be somebody's invented patterns wearing a different hat. Its definition is what the
other five cannot explain, so the machine isolates exactly that and stops. Whether the leftover
holds something characteristic, and why, is said by the reader.

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
                        for k in ("structured", "attributed", "machine")},
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
    rx["metacog"] = _alt(pattern_sets, lambda ps: (ps.get("types", {}).get("sousa") or {})
                         .get("signals", {}).get("metacog"))
    rx["finished_image"] = _alt(pattern_sets,
                                lambda ps: (ps.get("types", {}).get("houshutsu") or {})
                                .get("signals", {}).get("finished_image"))
    if rx["correction"] is None:
        rx["correction"] = _alt(pattern_sets, lambda ps: (ps.get("types", {}).get("sousa") or {})
                                .get("signals", {}).get("correction"))

    by_session = defaultdict(list)
    for e in events:
        by_session[e["session"]].append(e)

    axes = {
        "kyouka": _axis_constraint_survival(by_session, rx),
        "houshutsu": _axis_agent_did_not_fill_in(by_session, rx),
        "henka": _axis_vague_to_criterion(by_session, rx),
        "gugenka": _axis_finish_line_verified(by_session, rx),
        "sousa": _axis_rules_that_stuck(by_session, rx),
        "sousa_oneshot": _axis_correction_oneshot(by_session, rx),
    }
    type_rx = {tid: _alt(pattern_sets, lambda ps, t=tid: "|".join(
        v for v in ((ps.get("types", {}).get(t) or {}).get("signals") or {}).values()))
        for tid in type_order(pattern_sets) if signal_names(pattern_sets, tid)}
    # Stating a finish line lives in the shared `acceptance` pattern because the Conjurer axis
    # needs it as a denominator, but it is Conjurer behaviour and has to count as explained --
    # otherwise "done when the tests pass" lands in the residual as something unaccounted for.
    if "gugenka" in type_rx and rx["acceptance"]:
        type_rx["gugenka"] = re.compile("(?:%s)|(?:%s)" % (type_rx["gugenka"].pattern,
                                                           rx["acceptance"].pattern))
    residual = _residual(by_session, rx, type_rx)

    agent_turns = sum(1 for e in events if e["kind"] == "assistant")
    misreads = sum(1 for e in events if e["misread"])
    halves = _misread_halves(events)
    return {
        "axes": axes,
        "residual": residual,
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
# what the code actually counts. `against` names the comparison population -- every axis has a
# denominator that is a subset of something, and the same outcome measured over the rest of that
# something is the only way to tell "you are good at this" from "this number is always high".
AXES = {
    # axis id -> (type, label, unit, what it means, comparison population)
    "kyouka": ("kyouka", "sessions that held their constraint", "sessions",
               "A constraint you stated, and no correction in the rest of that session.",
               "sessions where you stated no constraint"),
    "houshutsu": ("houshutsu", "requests the agent did not have to fill in", "requests",
                  "No question back, no stated assumption, no menu of options -- the picture "
                  "arrived complete enough to act on.",
                  "requests carrying no finished-picture wording"),
    "henka": ("henka", "fuzzy starts that became checkable", "vague openings",
              "'Something is off' followed, in the same session, by a criterion someone else "
              "could apply.",
              "sessions that never started fuzzy"),
    "gugenka": ("gugenka", "finish lines the agent actually checked against",
                "requests with a finish line",
                "You said what done means, and the agent came back with evidence rather than "
                "a claim.",
                "requests with no finish line"),
    "sousa": ("sousa", "rules that became machinery", "rules declared",
              "Followed, before your next message, by a write into a rule file, hook or config.",
              "your other requests"),
    # Second axis for the same type. Steering is two things -- making a rule stick, and making a
    # correction land -- and a type can be strong at one and weak at the other.
    "sousa_oneshot": ("sousa", "corrections that landed in one go",
                      "corrections carrying a reason",
                      "You said what was wrong and why, or what rule should prevent it, and did "
                      "not have to correct the same thing again.",
                      "bare corrections, with no reason attached"),
}

CEILING = 95.0     # above this, a rate needs a baseline before it can mean anything
LIFT_FLOOR = 3.0   # below this much separation from the baseline, the axis is not discriminating


def axis_catalogue():
    """[(axis id, type, label, unit, detail)] -- for anything that documents what is counted."""
    return [(aid, AXES[aid][0]) + AXES[aid][1:4] for aid in AXES]


def axes_of(tid):
    return [aid for aid in AXES if AXES[aid][0] == tid]


def _axis(axis_id, hits, total, evidence=None, base_hits=0, base_total=0):
    tid, label, unit, detail, against = AXES[axis_id]
    pct = round(100.0 * hits / total, 1) if total >= MIN_N else None
    base_pct = round(100.0 * base_hits / base_total, 1) if base_total >= MIN_N else None
    lift = round(pct - base_pct, 1) if (pct is not None and base_pct is not None) else None
    # A number at the ceiling says nothing on its own: it may be you, or it may be that the
    # outcome almost always happens. Either the baseline separates them, or the axis is flagged.
    undiscriminating = (pct is not None
                        and (base_pct is None and pct >= CEILING
                             or lift is not None and abs(lift) < LIFT_FLOOR))
    return {"id": axis_id, "type": tid, "label": label, "unit": unit, "n": total, "hits": hits,
            "pct": pct, "enough": total >= MIN_N, "detail": detail,
            "against": against, "base_n": base_total, "base_pct": base_pct, "lift": lift,
            "undiscriminating": undiscriminating,
            "evidence": evidence or []}


def _users(evs):
    """Indices of messages that are yours. Pasted text is skipped here for the same reason the
    signal layer skips it: an effect credited to someone else's words is credited to the wrong
    person, and the residual is where that mistake would be loudest."""
    return [i for i, e in enumerate(evs) if e["kind"] == "user" and not e.get("paste")]


def _axis_constraint_survival(by_session, rx):
    """Enhancer: you named a constraint; did the session then run without a correction?

    Against: the sessions where you named none. Denominator is sessions, not messages -- holding
    a constraint is a property of a stretch of work."""
    hits = total = base_hits = base_total = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        if len(idx) < 3:
            continue
        cutoff = len(idx) - max(1, len(idx) // 3)
        stated = next((p for p in range(cutoff)
                       if rx["constraint"] and rx["constraint"].search(evs[idx[p]]["text"])), None)
        start = stated + 1 if stated is not None else 1
        clean = not any(rx["correction"] and rx["correction"].search(evs[i]["text"])
                        for i in idx[start:])
        if stated is None:
            base_total += 1
            base_hits += 1 if clean else 0
        else:
            total += 1
            if clean:
                hits += 1
                if len(ev) < 3:
                    ev.append(quote(evs[idx[stated]], 160))
    return _axis("kyouka", hits, total, ev, base_hits, base_total)


def _axis_agent_did_not_fill_in(by_session, rx):
    """Emitter: after your request, did the agent have to fill anything in?

    Filling in is three things, not one: asking you outright, stating an assumption, or handing
    back a menu of options. Counting only the first put this axis at 97% and it discriminated
    nothing -- agents almost never ask outright.

    Against: your requests that carried no finished-picture wording."""
    hits = total = base_hits = base_total = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        for pos, i in enumerate(idx):
            if not (rx["request"] and rx["request"].search(evs[i]["text"])):
                continue
            nxt = idx[pos + 1] if pos + 1 < len(idx) else len(evs)
            span = evs[i + 1:nxt]
            clean = not any(e["kind"] == "assistant"
                            and (e["question"] or e["assumption"] or e["options"])
                            for e in span)
            if rx["finished_image"] and rx["finished_image"].search(evs[i]["text"]):
                total += 1
                if clean:
                    hits += 1
                    if len(ev) < 3:
                        ev.append(quote(evs[i], 160))
            else:
                base_total += 1
                base_hits += 1 if clean else 0
    return _axis("houshutsu", hits, total, ev, base_hits, base_total)


def _axis_vague_to_criterion(by_session, rx):
    """Transmuter: a topic that began as a feeling -- did you turn it into something checkable?

    Against: sessions that never started fuzzy, where a criterion appeared anyway."""
    hits = total = base_hits = base_total = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        vague_at = [p for p, i in enumerate(idx)
                    if rx["vague"] and rx["vague"].search(evs[i]["text"])]

        def criterion_after(p):
            return any(rx["concrete_criterion"] and rx["concrete_criterion"].search(evs[j]["text"])
                       for j in idx[p + 1:])

        if vague_at:
            for p in vague_at:
                total += 1
                if criterion_after(p):
                    hits += 1
                    if len(ev) < 3:
                        ev.append(quote(evs[idx[p]], 160))
        elif len(idx) >= 2:
            base_total += 1
            base_hits += 1 if criterion_after(0) else 0
    return _axis("henka", hits, total, ev, base_hits, base_total)


def _axis_finish_line_verified(by_session, rx):
    """Conjurer: you wrote what done looks like -- did the agent then show it had checked?

    Against: your requests with no finish line, where the agent verified anyway. This is the
    axis that tests the prescription this whole tool argues for, against its own corpus."""
    hits = total = base_hits = base_total = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        for pos, i in enumerate(idx):
            t = evs[i]["text"]
            if not (rx["request"] and rx["request"].search(t)):
                continue
            nxt = idx[pos + 1] if pos + 1 < len(idx) else len(evs)
            verified = any(e["kind"] == "assistant" and e["verify"] for e in evs[i + 1:nxt])
            if rx["acceptance"] and rx["acceptance"].search(t):
                total += 1
                if verified:
                    hits += 1
                    if len(ev) < 3:
                        ev.append(quote(evs[i], 160))
            else:
                base_total += 1
                base_hits += 1 if verified else 0
    return _axis("gugenka", hits, total, ev, base_hits, base_total)


def _axis_rules_that_stuck(by_session, rx):
    """Manipulator: of the rules you declared, how many stopped depending on memory?

    Against: your other requests, which also sometimes end in a rule file being touched. A rule
    that lives only in the transcript has to be said again next time."""
    hits = total = base_hits = base_total = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        for pos, i in enumerate(idx):
            text = evs[i]["text"]
            is_rule = rx["rulemaking"] and rx["rulemaking"].search(text)
            is_req = rx["request"] and rx["request"].search(text)
            if not (is_rule or is_req):
                continue
            nxt = idx[pos + 1] if pos + 1 < len(idx) else len(evs)
            mech = any(e["kind"] == "tool" and e["mechanism"] for e in evs[i + 1:nxt])
            if is_rule:
                total += 1
                if mech:
                    hits += 1
                    if len(ev) < 3:
                        ev.append(quote(evs[i], 160))
            else:
                base_total += 1
                base_hits += 1 if mech else 0
    return _axis("sousa", hits, total, ev, base_hits, base_total)


def _axis_correction_oneshot(by_session, rx):
    """Manipulator, second axis: when you corrected, did it land the first time?

    This is the measure the published reading was built on -- 43 of 48 corrections converging on
    one pass. It came back with a comparison it did not have then: corrections that carried a
    reason or a rule, against bare ones. That is the claim worth testing, because explaining the
    cause is the thing this operator is said to do and the thing that would make it converge.

    Landed = you did not correct again within the next CORRECTION_CHAIN_GAP messages of yours.
    """
    hits = total = base_hits = base_total = 0
    ev = []
    for evs in by_session.values():
        idx = _users(evs)
        corr_at = [p for p, i in enumerate(idx)
                   if rx["correction"] and rx["correction"].search(evs[i]["text"])]
        for p in corr_at:
            landed = not any(0 < q - p <= CORRECTION_CHAIN_GAP for q in corr_at)
            text = evs[idx[p]]["text"]
            reasoned = ((rx["metacog"] and rx["metacog"].search(text))
                        or (rx["rulemaking"] and rx["rulemaking"].search(text)))
            if reasoned:
                total += 1
                if landed:
                    hits += 1
                    if len(ev) < 3:
                        ev.append(quote(evs[idx[p]], 160))
            else:
                base_total += 1
                base_hits += 1 if landed else 0
    return _axis("sousa_oneshot", hits, total, ev, base_hits, base_total)


# ---------------------------------------------------------------- the residual
# 特質系 is defined as what the other five cannot explain, so the machine's job here is not to
# recognise it. Any catalogue of "rare" shapes would be somebody's invented patterns wearing a
# different hat -- the exact mistake the five signals already risk, committed one level up.
#
# So this isolates the **residual**: your messages that none of the five types' signals account
# for, that nonetheless did something. Within that residual it ranks by how unusual the wording is
# *against your own corpus* -- not against a list, and not against other people. Nothing here
# decides that a message is special. It hands over what is left over, and the reader says whether
# there is anything characteristic in it.

MIN_RESIDUAL_CHARS = 24      # below this there is not enough to be distinctive about
MIN_RESIDUAL_TOKENS = 4
RESIDUAL_CANDIDATES = 6

_LATIN = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")
_CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def _tokens(text):
    """Latin words plus CJK character bigrams -- enough to compare wording across a corpus that
    mixes both, without a tokenizer dependency."""
    out = set(m.group(0).lower() for m in _LATIN.finditer(text))
    squeezed = re.sub(r"\s+", "", text)
    for i in range(len(squeezed) - 1):
        if _CJK.match(squeezed[i]):
            out.add(squeezed[i:i + 2])
    return out


def _residual(by_session, rx, type_rx):
    """What the five do not account for, ranked by how unusual it is against your own corpus."""
    import math

    mine, df, total = [], defaultdict(int), 0
    for evs in by_session.values():
        for p, i in enumerate(_users(evs)):
            e = evs[i]
            toks = _tokens(e["text"])
            total += 1
            for t in toks:
                df[t] += 1
            explained = sorted(tid for tid, r in type_rx.items() if r and r.search(e["text"]))
            nxt = _users(evs)[p + 1] if p + 1 < len(_users(evs)) else len(evs)
            span = evs[i + 1:nxt]
            mine.append({"event": e, "tokens": toks, "explained": explained,
                         "tools": sum(1 for x in span if x["kind"] == "tool"),
                         "mechanism": any(x["kind"] == "tool" and x["mechanism"] for x in span),
                         "verified": any(x["kind"] == "assistant" and x["verify"] for x in span)})

    leftover = [m for m in mine
                if not m["explained"]
                and len(m["event"]["text"]) >= MIN_RESIDUAL_CHARS
                and len(m["tokens"]) >= MIN_RESIDUAL_TOKENS
                and (m["tools"] or m["mechanism"])]

    for m in leftover:
        m["unusualness"] = round(
            sum(math.log(total / df[t]) for t in m["tokens"]) / len(m["tokens"]), 3)
    leftover.sort(key=lambda m: -m["unusualness"])

    return {
        "messages_examined": total,
        "explained_by_the_five": total - sum(1 for m in mine if not m["explained"]),
        "explained_pct": round(100.0 * (total - sum(1 for m in mine if not m["explained"]))
                               / total, 1) if total else None,
        "residual_that_did_something": len(leftover),
        "candidates": [{
            "ts": m["event"]["ts"][:16],
            "text": m["event"]["text"][:240],
            "unusualness": m["unusualness"],
            "tool_calls": m["tools"],
            "left_a_mechanism": m["mechanism"],
            "agent_verified": m["verified"],
        } for m in leftover[:RESIDUAL_CANDIDATES]],
        "note": "None of the five types' signals fire on these, and each was followed by the "
                "agent doing work. Ranked by wording unusual for your own corpus. The ranking "
                "does not claim they are special -- it decides what is worth your attention "
                "first.",
        "how_to_read": "Specialist is recognised only if you look at these and find something "
                       "characteristic that the other five genuinely do not describe. Finding "
                       "nothing is the ordinary outcome.",
    }


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

    for aid, ax in (result.get("effects", {}).get("axes") or {}).items():
        tid = ax["type"]
        t = next((x for x in result["types"] if x["id"] == tid), None)
        label = (t or {}).get("label_en") or tid
        if not ax["enough"]:
            qs.append({
                "id": "occ_axis_%s" % aid,
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
            "id": "attr_%s" % aid,
            "kind": "attribution",
            "type": tid,
            "why": "%s: %d of %d %s (%s%%), against %s%% for %s%s. %s"
                   % (label, ax["hits"], ax["n"], ax["unit"], ax["pct"],
                      ax["base_pct"], ax["against"],
                      " — a separation of %+.1f points, which is small enough that the number "
                      "may be the population rather than you" % ax["lift"]
                      if ax["undiscriminating"] and ax["lift"] is not None else "",
                      ax["detail"]),
            "ask": "Were those %s the same kind of work as the rest — or the ones you already "
                   "understood well?" % ax["unit"],
            "observe": "A number that only holds on easy work is not an aptitude.",
            "answer_format": "same kind | the easier ones | the harder ones",
            "blocking": True,
        })

    res = (result.get("effects") or {}).get("residual") or {}
    if res.get("candidates"):
        qs.append({
            "id": "residual",
            "kind": "residual",
            "type": "tokushitsu",
            "why": "The five types' signals account for %s%% of your messages. %d of the rest "
                   "were followed by the agent doing work; these are the %d whose wording is "
                   "least like the rest of your corpus."
                   % (res["explained_pct"], res["residual_that_did_something"],
                      len(res["candidates"])),
            "ask": "Read these. Is there something here the other five genuinely do not "
                   "describe — something that is characteristically you?",
            "observe": "Nothing in the tool says these are special; it only says the five do "
                       "not explain them. Finding nothing here is the ordinary outcome.",
            "answer_format": "name what it is | nothing here",
            "blocking": False,
            "items": res["candidates"],
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
        # built from corpus.AGENT_FLAGS so a new agent-side flag cannot be forgotten here
        e = {"ts": "2026-08-01T10:00", "session": kw.pop("s", "e1"), "kind": kind,
             "text": text, "tool": "", "mechanism": False, "paste": None}
        e.update({name: False for name in corpus.AGENT_FLAGS})
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
    # None of these requests state a finished picture, so they are all the comparison side --
    # which is the point of the axis: it rates the requests where you did paint one.
    check("Emitter axis puts requests with no finished picture on the comparison side",
          ax["houshutsu"]["n"] == 0 and ax["houshutsu"]["base_n"] == 6
          and ax["houshutsu"]["base_pct"] == 83.3, str(ax["houshutsu"]))
    check("Conjurer axis counts only requests that carried a finish line",
          ax["gugenka"]["n"] == 2 and ax["gugenka"]["hits"] == 1, str(ax["gugenka"]))
    check("Manipulator axis counts rules that reached a file",
          ax["sousa"]["n"] == 2 and ax["sousa"]["hits"] == 1, str(ax["sousa"]))
    check("an axis below the minimum reports its count instead of a rate",
          ax["henka"]["enough"] is False and ax["henka"]["pct"] is None, str(ax["henka"]))

    # -- baselines: a rate with nothing to compare against cannot mean anything ------------
    # Every axis's denominator is a subset of something; the same outcome over the rest of that
    # something is what separates "you are good at this" from "this number is always high".
    base_tl = []
    for i in range(6):      # you state a finish line: the agent verifies every time
        base_tl += [ev("user", "please fix it %d, done when tests pass" % i, s="b%d" % i),
                    ev("assistant", verify=True, s="b%d" % i)]
    for i in range(6):      # you do not: it verifies every time anyway
        base_tl += [ev("user", "please fix it plainly %d" % i, s="c%d" % i),
                    ev("assistant", verify=True, s="c%d" % i)]
    flat = measure_effects(base_tl, pats, cfg)["axes"]["gugenka"]
    check("an axis carries the same outcome measured over the comparison population",
          flat["base_n"] == 6 and flat["base_pct"] == 100.0, str(flat))
    check("a rate no different from its baseline is marked as saying nothing",
          flat["pct"] == 100.0 and flat["lift"] == 0.0 and flat["undiscriminating"] is True,
          str(flat))

    lift_tl = list(base_tl[:12])
    for i in range(6):      # same, but without a finish line it never verifies
        lift_tl += [ev("user", "please fix it plainly %d" % i, s="d%d" % i),
                    ev("assistant", s="d%d" % i)]
    lifted = measure_effects(lift_tl, pats, cfg)["axes"]["gugenka"]
    check("a rate that separates from its baseline is not marked",
          lifted["lift"] == 100.0 and lifted["undiscriminating"] is False, str(lifted))

    # -- Emitter's outcome: asking outright is only one of three ways to fill a gap ---------
    fill_tl = [ev("user", "i want it to end up like a single page, please build it", s="f1"),
               ev("assistant", assumption=True, s="f1"),
               ev("user", "i want it to feel finished, please build it", s="f2"),
               ev("assistant", options=True, s="f2"),
               ev("user", "i want it done, please build it", s="f3"),
               ev("assistant", question=True, s="f3"),
               ev("user", "i want it clean, please build it", s="f4"),
               ev("assistant", s="f4")]
    em = measure_effects(fill_tl, pats, cfg)["axes"]["houshutsu"]
    check("a stated assumption or a menu of options counts as filling in, like a question does",
          em["n"] == 4 and em["hits"] == 1, str(em))
    check("the axes disagree with each other, which one shared outcome could not",
          len({ax[k]["hits"] for k in ("kyouka", "houshutsu", "gugenka", "sousa")}) > 1)

    pasted_rule = [ev("user", "from now on print the diff", s="p1", paste="structured"),
                   ev("tool", tool="Edit", mechanism=True, s="p1")]
    check("a rule you pasted from somewhere else is not your steering",
          measure_effects(pasted_rule, pats, cfg)["axes"]["sousa"]["n"] == 0)

    # -- the residual: what the five do not account for -----------------------------------
    # Specialist is the leftover, so the tool must not decide anything about it. What is tested
    # here is that the leftover is isolated correctly and that nothing scores it.
    # Both explained messages are deliberately longer than MIN_RESIDUAL_CHARS, so that keeping
    # them out of the residual proves the five explained them rather than that they were too short
    # to consider -- the first version of this passed for exactly that wrong reason.
    leftover_msg = "work the unspecified parts out from what I already told you, quietly"
    explained_a = "you must not drop the constraint we agreed on"
    explained_b = "no, that is wrong, I meant the other file entirely"
    resid_tl = [ev("user", explained_a, s="q1"),
                ev("tool", tool="Edit", s="q1"),
                ev("user", leftover_msg, s="q1"),
                ev("tool", tool="Edit", mechanism=True, s="q1"),
                ev("user", explained_b, s="q1"),
                ev("tool", tool="Edit", s="q1")]
    res = measure_effects(resid_tl, pats, cfg)["residual"]
    texts = [c["text"] for c in res["candidates"]]
    check("a message no type's signal explains is isolated",
          leftover_msg in texts, str(texts))
    check("messages the five do explain stay out of the residual, despite being long enough",
          not any(t.startswith(explained_a[:20]) or t.startswith(explained_b[:20])
                  for t in texts)
          and len(explained_a) > MIN_RESIDUAL_CHARS and len(explained_b) > MIN_RESIDUAL_CHARS,
          str(texts))
    check("the residual reports how much of you the five account for",
          res["explained_pct"] == round(200.0 / 3, 1), str(res["explained_pct"]))
    check("what the agent did about it travels with the candidate",
          res["candidates"][0]["left_a_mechanism"] is True
          and res["candidates"][0]["tool_calls"] == 1, str(res["candidates"][0]))
    check("nothing in the residual is scored or named for you",
          not any(k in res["candidates"][0] for k in ("label", "definition", "score", "verdict")),
          str(sorted(res["candidates"][0])))

    finish_line = [ev("user", "please rewrite the loader, done when the tests pass", s="q5"),
                   ev("tool", tool="Edit", s="q5")]
    check("stating a finish line counts as explained, not as leftover",
          measure_effects(finish_line, pats, cfg)["residual"]["candidates"] == [],
          str(measure_effects(finish_line, pats, cfg)["residual"]["candidates"]))

    idle = [ev("user", "ok", s="q2"), ev("user", "thanks", s="q2")]
    check("leftovers that led to no work are not candidates",
          measure_effects(idle, pats, cfg)["residual"]["candidates"] == [])

    pasted_leftover = [ev("user", leftover_msg, s="q3", paste="machine"),
                       ev("tool", tool="Edit", mechanism=True, s="q3")]
    check("pasted machine output never reaches the residual",
          measure_effects(pasted_leftover, pats, cfg)["residual"]["candidates"] == [])

    common = "please fix the parser again"
    odd = "the unspecified parts should be derived from precedent, quietly and without asking"
    rank_tl = []
    for i in range(6):
        rank_tl += [ev("user", "%s %d" % (common, i), s="q4"), ev("tool", tool="Edit", s="q4")]
    rank_tl += [ev("user", odd, s="q4"), ev("tool", tool="Edit", s="q4")]
    ranked = measure_effects(rank_tl, pats, cfg)["residual"]["candidates"]
    check("wording unusual for your own corpus is offered first",
          ranked and ranked[0]["text"].startswith("the unspecified parts"),
          str([c["text"][:30] for c in ranked]))

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
