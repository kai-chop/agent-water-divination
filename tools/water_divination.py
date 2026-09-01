# -*- coding: utf-8 -*-
"""water_divination — give it a date, get your reading.

Two commands, because a reading has two halves and only the first one is mechanical.

    python tools/water_divination.py measure --since 2026-08-01
        Finds your transcripts, keeps the messages you actually typed inside that window,
        counts the six types' signals, and writes three files: the result JSON, a provisional
        HTML page, and an answers template listing everything the numbers could not settle.

    python tools/water_divination.py verdict --result out/divination.json --answers out/answers.json
        Checks that every blocking question was answered, applies the answers, and only then
        writes the confirmed reading.

**The gate is the design.** `verdict` refuses while a blocking question is unanswered, and it
means it: answering "no, I pasted that" removes the quote from the evidence, and if that drops a
type below the two quotes a verdict requires, the verdict is refused until a probe replaces them.
Without that, the interview would be decoration on a number the tool had already decided.

Windows:
    --since 2026-08-01                  from that date
    --since 2026-08-01 --until 2026-08-31
    --on 2026-08-15                     one day
    --last 30d                          30 days back from now (also 12h, 8w)

Self-test: python tools/water_divination.py --self-test
"""
import argparse
import datetime
import glob
import io
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nen_corpus as corpus      # noqa: E402
import nen_report as report      # noqa: E402
import nen_signals as signals    # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOOL_VERSION = "1"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = {"h": "hours", "d": "days", "w": "weeks"}


def parse_last(spec, now=None):
    m = re.fullmatch(r"(\d+)([hdw])", (spec or "").strip())
    if not m:
        raise SystemExit("--last wants a number and one of h/d/w, e.g. 30d")
    now = now or datetime.datetime.now()
    delta = datetime.timedelta(**{UNITS[m.group(2)]: int(m.group(1))})
    return (now - delta).strftime("%Y-%m-%dT%H:%M")


def resolve_window(args, now=None):
    if args.last:
        return parse_last(args.last, now), None
    if args.on:
        return args.on, args.on
    return args.since, args.until


# ---------------------------------------------------------------- measure

def run_measure(args):
    cfg = corpus.load_config(args.config)
    base = cfg.get("_base") or REPO_ROOT
    pats = signals.load_patterns(cfg["patterns"], base)
    attrib = corpus.build_attribution_rx(pats)
    since, until = resolve_window(args)

    msgs, scan = corpus.collect(cfg, since, until, attrib)
    print("[water-divination] alive: scanned=%d window=%s..%s version=%s"
          % (len(msgs), since or "-", until or "-", TOOL_VERSION))
    print(corpus.format_scan_report(scan))

    result = signals.measure(msgs, pats, cfg)
    if result is None:
        print("\nNo messages of yours in that window. Widen the dates, or check the roots above.")
        return 2

    result["asked_window"] = {"since": since, "until": until}

    # the effect layer: what the agent did after you spoke. Needs the turns the signal layer
    # throws away, so it is a second pass over the same stores.
    # flag name -> the key it is written under in patterns/*.json
    flag_keys = {"misread": "misread", "verify": "verification", "question": "agent_question",
                 "assumption": "agent_assumption", "options": "agent_options"}
    flag_rx = {name: signals._alt(pats, lambda ps, k=key: ps.get("effects", {}).get(k))
               for name, key in flag_keys.items()}
    mech_rx = signals._alt(pats, lambda ps: ps.get("effects", {}).get("mechanism_path"))
    # count the same marks in the agent's own turns as we read them: the reference is the other
    # writer in the room, not a pile of documentation
    ref_counts = {}
    flag_rx["_ref"] = {tid: signals._alt(pats, lambda ps, t=tid: "|".join(
        v for v in ((ps.get("types", {}).get(t) or {}).get("signals") or {}).values()))
        for tid in signals.type_order(pats) if signals.signal_names(pats, tid)}
    flag_rx["_ref_out"] = ref_counts
    tl, blind = corpus.collect_timeline(cfg, since, until, flag_rx, mech_rx, attrib)
    result["effects"] = signals.measure_effects(tl, pats, cfg, blind)

    result["open_questions"] = signals.open_questions(result, pats, cfg)
    result["provisional"] = signals.provisional_ranking(result)
    # the reading always names something; the basis and the confidence carry the rigour
    result["reading"] = signals.reading(result)
    result["next_move"] = signals.next_move(result)
    # The comparison that makes a profile mean something. Default: the agent's own turns from the
    # same conversations -- the other writer in the room. Not other operators; there is no such
    # corpus here, and inventing one would be fabrication.
    ref_n = ref_counts.pop("_n", 0)
    ref_chars = ref_counts.pop("_chars", 0)
    reference = ({k: round(1000.0 * v / ref_chars, 2) for k, v in ref_counts.items()}
                 if ref_chars else {})
    reference["_n"] = ref_n
    reference["_chars"] = ref_chars
    reference["_what"] = "the agent's own turns in the same conversations"
    if getattr(args, "reference", None):
        texts = _reference_texts(corpus.resolve(args.reference))
        reference = signals.reference_rates(pats, texts)
        reference["_what"] = "prose in %s" % args.reference
    result["reference"] = reference
    result["profile"] = signals.profile(result, reference)

    os.makedirs(args.out, exist_ok=True)
    result_path = os.path.join(args.out, "divination.json")
    html_path = os.path.join(args.out, "water-divination.html")
    answers_path = os.path.join(args.out, "answers.json")
    _write_json(result_path, result)
    with io.open(html_path, "w", encoding="utf-8") as f:
        f.write(report.render(result))
    if not os.path.exists(answers_path):
        _write_json(answers_path, _answers_template(result))

    blocking = [q for q in result["open_questions"] if q["blocking"]]
    print("\n%d message(s) of yours across %d session(s)." % (result["own"], result["sessions"]))

    eff = result["effects"]
    label_of = {t["id"]: t["label_en"] for t in result["types"]}
    showed = [a for a in eff["axes"].values() if a["direction"] == "for"]
    against = [a for a in eff["axes"].values() if a["direction"] == "against"]
    quiet = [a for a in eff["axes"].values() if a["direction"] == "none"]
    showed.sort(key=lambda a: -(a["lift"] if a["lift"] is not None else 0))

    print("\n--- what the water did (%d agent turns) ---" % eff["assistant_turns"])
    if showed:
        for ax in showed:
            _print_axis({"label_en": label_of.get(ax["type"], ax["type"])}, ax)
    else:
        print("  nothing separated from its own baseline in this window.")
        # a refusal with no route out is where a reading dies -- name the nearest one and
        # what it would take
        near = [a for a in eff["axes"].values()
                if a.get("would_settle_at_n") and a.get("lift") is not None]
        near.sort(key=lambda a: -(a["lift"] or 0))
        for ax in near[:2]:
            print("  closest: %s — %s %s%% vs %s%% (%d %s so far; ~%d would settle it)"
                  % (label_of.get(ax["type"], ax["type"]), ax["label"], ax["pct"],
                     ax["base_pct"], ax["n"], ax["unit"], ax["would_settle_at_n"]))
    for ax in against:
        print("  ! went the other way:")
        _print_axis({"label_en": label_of.get(ax["type"], ax["type"])}, ax)
    if quiet:
        # named, not itemised: these are reactions the glass did not have, and a reading that
        # lists them turns into a survey of everything the operator failed to do
        print("  (%d axes did not show: %s — too thin, or level with their baseline. Their "
              "numbers are in the JSON.)"
              % (len(quiet), ", ".join(sorted({label_of.get(a["type"], a["type"])
                                               for a in quiet}))))

    res = eff["residual"]
    print("\n  Specialist — what the five do not explain")
    print("    recall: the five explain %s%% of your %d substantive messages (floor %s%%)"
          % (res["recall_pct"], res["substantive"], res["recall_floor"]))
    if not res["usable"]:
        print("    %s" % res["why_unusable"])
        print("    (the leftover is still listed below, as material — not as evidence)")
    print("    %d of the leftover were followed by work" % res["residual_that_did_something"])
    for c in res["candidates"]:
        marks = "".join([" +mechanism" if c["left_a_mechanism"] else "",
                         " +verified" if c["agent_verified"] else ""])
        print("    * %s  (unusualness %.2f, %d tool calls%s)"
              % (c["ts"], c["unusualness"], c["tool_calls"], marks))
        print("      %s" % c["text"][:96].replace("\n", " / "))
    if not res["candidates"]:
        print("    nothing left over that did anything -- the five cover this window")

    mr = eff["misreads"]
    if mr["per_100_agent_turns"] is not None:
        trend = ""
        if mr["first_half"] and mr["second_half"]:
            trend = "  (%s -> %s across the window)" % (mr["first_half"]["per_100"],
                                                        mr["second_half"]["per_100"])
        print("\n  agent-admitted misreads %d = %s per 100 agent turns%s"
              % (mr["n"], mr["per_100_agent_turns"], trend))
    if eff["blind_sources"]:
        print("  no agent side in: %s (nothing measurable there)"
              % ", ".join(eff["blind_sources"]))

    # The reading comes first and it comes with a name. The questions are what would settle it,
    # not homework standing between you and an answer.
    if showed:
        lead = showed[0]
        print("\n--- it looks like %s ---" % label_of.get(lead["type"], lead["type"]))
        print("  %s, %s%% against %s%% — the widest separation in this window."
              % (lead["label"], lead["pct"], lead["base_pct"]))
        print("  Not settled yet: %d thing(s) below would confirm or move it." % len(blocking))

    print("\n--- what would settle it (%d, plus %d optional) ---"
          % (len(blocking), len(result["open_questions"]) - len(blocking)))
    for q in sorted(result["open_questions"], key=lambda x: not x["blocking"]):
        print("\n[%s]%s %s" % (q["kind"], "" if q["blocking"] else " optional", q["id"]))
        print("  why : %s" % q["why"])
        print("  ask : %s" % q["ask"])
        for it in (q.get("items") or [])[:8]:
            print("      - %s  %s" % (it.get("ts", ""), (it.get("text") or "")[:78]))
        if q.get("observe"):
            print("  watch: %s" % q["observe"])
        print("  answer: %s" % q["answer_format"])
    print("\nwrote %s, %s, %s" % (result_path, html_path, answers_path))
    print("Fill in the answers file, then run: water_divination.py verdict "
          "--result %s --answers %s" % (result_path, answers_path))
    return 0


def _print_axis(t, ax):
    """One line per axis. A type may have more than one -- steering is both making a rule stick
    and making a correction land, and those can disagree."""
    if not ax["enough"]:
        # the comparison side still carries the diagnosis: it says whether the outcome varies
        # at all, which is what tells a thin axis from a pointless one
        base = ("  (the %s ran %s%%)" % (ax["against"], ax["base_pct"])
                if ax["base_pct"] is not None else "")
        print("  %-12s %-40s  only %d %s%s"
              % (t["label_en"], ax["label"], ax["n"], ax["unit"], base))
        return
    base = ("vs %5s%% (%d %s)" % (ax["base_pct"], ax["base_n"], ax["against"])
            if ax["base_pct"] is not None else "no baseline (%s: %d)"
            % (ax["against"], ax["base_n"]))
    lift = "  %+.1f pts" % ax["lift"] if ax["lift"] is not None else ""
    print("  %-12s %-40s %5s%% (%d/%d)  %s%s%s"
          % (t["label_en"], ax["label"], ax["pct"], ax["hits"], ax["n"], base, lift,
             "  <- says nothing" if ax["undiscriminating"] else ""))



def _reference_texts(root, cap=4000):
    """Paragraphs of ordinary prose to compare against. Documentation by default -- writing, but
    not writing aimed at an agent. Point --reference at anything you would rather be compared to."""
    out = []
    for path in sorted(glob.glob(os.path.join(root, "**", "*.*"), recursive=True)):
        if os.path.splitext(path)[1].lower() not in (".md", ".txt"):
            continue
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                out += [p.strip() for p in re.split(r"\n\s*\n", f.read()) if p.strip()]
        except OSError:
            continue
        if len(out) >= cap:
            break
    return out[:cap]


def _answers_template(result):
    return {
        "_howto": "Fill `answer` for every question. Blocking ones gate the verdict. "
                  "Then complete `verdict`: main is required, roles/reads/summary are the reading.",
        "_portrait": "The one field a reader actually keeps. Two or three sentences describing "
                     "this person, built from the quotes above and written in their language -- "
                     "not the type's definition pasted in. Say what they do, in their words, and "
                     "one thing it costs them. No flattery and no certainty you do not have.",
        "_reads": "One per type, in their language, about THEM -- never the definition restated. "
                  "The strong ones are asserted plainly; the quiet ones say what they did not "
                  "reach for this period, which is not the same as a weakness. Every type gets "
                  "a line: a reading that only discusses its winner is a scoreboard.",
        "answers": {q["id"]: {"answer": "", "note": ""} for q in result["open_questions"]},
        "verdict": {"main": "", "portrait": "",
                    "roles": {}, "summary": "", "title": "",
                    "reads": {t["id"]: "" for t in result["types"]}},
    }


# ---------------------------------------------------------------- verdict

def revoke_disowned(result, answers):
    """A quote its author disowns stops being evidence. Returns the list of revocations.

    The authorship question is asked once for all the quotes at once, so the answer names which
    ones are not yours: "all mine" revokes nothing, anything else is matched against the quotes
    by timestamp or by text.
    """
    revoked = []
    for q in result["open_questions"]:
        a = answers.get(q["id"]) or {}
        said = (str(a.get("answer", "")) + " " + str(a.get("note", ""))).strip()
        refs = q.get("quote_refs") or ([q["quote_ref"]] if q.get("quote_ref") else [])
        if not refs or not said:
            continue
        if said.strip().lower() in ("all mine", "yes", "mine", "all"):
            continue
        disowned = [r for r in refs
                    if r["ts"] in said
                    or any(r["ts"] == it["ts"] and it["text"][:24] in said
                           for it in (q.get("items") or []))]
        # a bare "no" on a single-quote question still means that one
        if not disowned and said.strip().lower() in ("no", "n", "false") and len(refs) == 1:
            disowned = refs
        for ref in disowned:
            for t in result["types"]:
                if t["id"] != ref["type"]:
                    continue
                for name, quotes in (t["quotes"] or {}).items():
                    keep = [x for x in quotes if x["ts"] != ref["ts"]]
                    if len(keep) != len(quotes):
                        revoked.append({"type": t["id"], "signal": name, "ts": ref["ts"]})
                    t["quotes"][name] = keep
    return revoked


def evidence_count(t):
    uniq = {(q["ts"], q["text"][:40]) for qs in (t["quotes"] or {}).values() for q in qs}
    return len(uniq)


def probe_passed(result, answers, tid):
    a = answers.get("probe_%s" % tid) or {}
    return str(a.get("answer", "")).strip().lower() in ("pass", "yes", "y", "ok")


def run_verdict(args):
    with io.open(args.result, encoding="utf-8") as f:
        result = json.load(f)
    with io.open(args.answers, encoding="utf-8") as f:
        raw = json.load(f)

    answers = raw.get("answers", raw if "verdict" not in raw else {})
    verdict = dict(raw.get("verdict") or {})
    answers = {k: v for k, v in answers.items()
               if isinstance(v, dict) and str(v.get("answer", "")).strip()}

    refusals = []
    unanswered = [q["id"] for q in result["open_questions"]
                  if q["blocking"] and q["id"] not in answers]
    if unanswered:
        refusals.append("blocking questions unanswered: " + ", ".join(unanswered))

    revoked = revoke_disowned(result, answers)
    main = (verdict.get("main") or "").strip()
    if not main:
        refusals.append("`verdict.main` is empty -- name the type the evidence supports")
    else:
        t = next((x for x in result["types"] if x["id"] == main), None)
        if t is None:
            refusals.append("`verdict.main` = %r is not one of the six types" % main)
        elif t["signals"] is None and not probe_passed(result, answers, main):
            refusals.append("%s has no detector, so it needs its probe to pass" % main)
        elif (t["signals"] is not None
              and evidence_count(t) < signals.QUOTES_FOR_VERDICT
              and not probe_passed(result, answers, main)):
            refusals.append("%s has %d quote(s) left after revocations, needs %d or a passing probe"
                            % (main, evidence_count(t), signals.QUOTES_FOR_VERDICT))

    if revoked:
        print("revoked as not the operator's own words:")
        for r in revoked:
            print("  - %s / %s @ %s" % (r["type"], r["signal"], r["ts"]))

    if refusals:
        # A refusal is one step short of a name, not a rejection. Saying it the other way makes
        # the tool feel like an auditor, and nobody comes back to an auditor.
        print("\nOne step short of a name:")
        for r in refusals:
            print("  - %s" % r)
        print("\nSettle that and run this again. (exit 3)")
        return 3

    verdict["confirmed"] = True
    verdict.setdefault("title", "Water Divination")
    result["verdict"] = verdict
    result["answers"] = answers
    result["revoked"] = revoked

    out_dir = args.out or os.path.dirname(os.path.abspath(args.result))
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, "water-divination.html")
    _write_json(os.path.join(out_dir, "divination.json"), result)
    with io.open(html_path, "w", encoding="utf-8") as f:
        f.write(report.render(result))

    main_t = next(x for x in result["types"] if x["id"] == main)
    print("\nVERDICT — main type: %s / %s" % (main_t["label"], main_t["label_en"]))
    for tid, role in (verdict.get("roles") or {}).items():
        print("  %-12s %s" % (tid, role))
    if verdict.get("summary"):
        print("\n%s" % verdict["summary"])
    print("\nwrote %s" % html_path)
    return 0


def _write_json(path, obj):
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- self-test

def _self_test():
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    now = datetime.datetime(2026, 8, 31, 12, 0)
    check("--last 30d resolves to a date 30 days back",
          parse_last("30d", now).startswith("2026-08-01"), parse_last("30d", now))
    check("--last 12h resolves within the day", parse_last("12h", now) == "2026-08-31T00:00")
    check("--on collapses to a single day",
          resolve_window(argparse.Namespace(last=None, on="2026-08-15", since=None, until=None))
          == ("2026-08-15", "2026-08-15"))

    with tempfile.TemporaryDirectory() as tmp:
        proj = os.path.join(tmp, "store", "proj")
        os.makedirs(proj)
        rows = []
        texts = [
            "from now on, always add the evidence line",
            "no, that's wrong -- i meant the other file",
            "think of it as a funnel, the way a mail client does it",
            "the goal is one clean pass and you must not drop the constraint",
            "please fix the parser; it's done when the tests pass",
            "i want it to end up feeling like a single page",
            "make it a rule: never skip the check again",
            "not that one -- rather than the cache, use the index",
        ]
        for i, t in enumerate(texts):
            rows.append({"type": "user", "promptSource": "typed", "origin": {"kind": "human"},
                         "timestamp": "2026-08-%02dT10:00:00Z" % (i + 1), "sessionId": "s1",
                         "message": {"content": [{"type": "text", "text": t}]}})
        rows.append({"type": "user", "promptSource": "typed", "origin": {"kind": "human"},
                     "timestamp": "2026-07-01T10:00:00Z", "sessionId": "s0",
                     "message": {"content": [{"type": "text",
                                              "text": "outside the window entirely"}]}})
        with io.open(os.path.join(proj, "a.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

        cfg_path = os.path.join(tmp, "cfg.json")
        _write_json(cfg_path, {
            "sources": [{"format": "claude-code", "root": os.path.join(tmp, "store")}],
            "patterns": [os.path.join(REPO_ROOT, "patterns", "ja.json"),
                         os.path.join(REPO_ROOT, "patterns", "en.json")]})

        out = os.path.join(tmp, "out")
        rc = run_measure(argparse.Namespace(config=cfg_path, out=out, since="2026-08-01",
                                            until=None, on=None, last=None))
        check("measure runs from a date alone", rc == 0)
        with io.open(os.path.join(out, "divination.json"), encoding="utf-8") as f:
            res = json.load(f)
        check("the window excludes what is outside it", res["own"] == len(texts),
              "own=%d" % res["own"])
        check("an HTML page is written by measure",
              os.path.getsize(os.path.join(out, "water-divination.html")) > 2000)
        check("the page names a type even before anything is settled",
              "水はこう動いた" in io.open(os.path.join(out, "water-divination.html"),
                                          encoding="utf-8").read())
        check("an answers template is written with one slot per question",
              set(json.load(io.open(os.path.join(out, "answers.json"), encoding="utf-8")
                            )["answers"]) == {q["id"] for q in res["open_questions"]})

        ans_path = os.path.join(out, "answers.json")
        empty = json.load(io.open(ans_path, encoding="utf-8"))
        rc = run_verdict(argparse.Namespace(result=os.path.join(out, "divination.json"),
                                            answers=ans_path, out=out))
        check("verdict is refused while blocking questions are unanswered", rc == 3)

        filled = dict(empty)
        filled["answers"] = {q["id"]: {"answer": "pass" if q["kind"] == "probe" else "yes",
                                       "note": "fixture"} for q in res["open_questions"]}
        filled["verdict"] = {"main": "sousa", "roles": {"sousa": "main"},
                             "reads": {"sousa": "held"}, "summary": "Manipulator."}
        _write_json(ans_path, filled)
        rc = run_verdict(argparse.Namespace(result=os.path.join(out, "divination.json"),
                                            answers=ans_path, out=out))
        check("verdict is issued once every blocking question is answered", rc == 0)
        page = io.open(os.path.join(out, "water-divination.html"), encoding="utf-8").read()
        check("the confirmed page asserts the type rather than hedging it",
              "CONFIRMED" in page and "あなたは " in page and "水はこう動いた" not in page)

        no_main = dict(filled)
        no_main["verdict"] = dict(filled["verdict"], main="")
        _write_json(ans_path, no_main)
        check("a verdict with no named type is refused",
              run_verdict(argparse.Namespace(result=os.path.join(out, "divination.json"),
                                             answers=ans_path, out=out)) == 3)

        # disowning the quotes must actually cost the type its verdict
        rc = run_measure(argparse.Namespace(config=cfg_path, out=out, since="2026-08-01",
                                            until=None, on=None, last=None))
        with io.open(os.path.join(out, "divination.json"), encoding="utf-8") as f:
            res2 = json.load(f)
        sousa = next(t for t in res2["types"] if t["id"] == "sousa")
        for name, quotes in sousa["quotes"].items():
            for q in quotes:
                res2["open_questions"].append({
                    "id": "auth_sousa_%s" % q["ts"].replace(":", "").replace("-", ""),
                    "kind": "authorship", "type": "sousa", "why": "fixture",
                    "ask": "yours?", "observe": "", "answer_format": "yes | no",
                    "blocking": True, "quote_ref": {"type": "sousa", "ts": q["ts"]}})
        _write_json(os.path.join(out, "divination.json"), res2)
        disown = {"answers": {q["id"]: {"answer": "no" if q["kind"] == "authorship" else "pass",
                                        "note": ""} for q in res2["open_questions"]},
                  "verdict": {"main": "sousa"}}
        # the probe for sousa is not among the questions, so nothing rescues the revocation
        disown["answers"].pop("probe_sousa", None)
        _write_json(ans_path, disown)
        rc = run_verdict(argparse.Namespace(result=os.path.join(out, "divination.json"),
                                            answers=ans_path, out=out))
        check("disowning the quotes revokes the verdict that rested on them", rc == 3)

    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(
        description="A water divination for the person directing an AI. Give it a date.")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    m = sub.add_parser("measure", help="read the window and list what must be asked")
    m.add_argument("--since", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    m.add_argument("--until")
    m.add_argument("--on", help="a single day")
    m.add_argument("--last", help="12h / 30d / 8w")
    m.add_argument("--config")
    m.add_argument("--reference", metavar="DIR",
                   help="prose to compare against (default: this repo's docs). Ordinary writing, "
                        "not other people -- there is no corpus of other operators here")
    m.add_argument("--out", default="out")

    v = sub.add_parser("verdict", help="apply the answers and, if they suffice, conclude")
    v.add_argument("--result", required=True)
    v.add_argument("--answers", required=True)
    v.add_argument("--out")

    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if args.cmd == "measure":
        if not (args.since or args.until or args.on or args.last):
            ap.error("give a window: --since / --on / --last")
        return run_measure(args)
    if args.cmd == "verdict":
        return run_verdict(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
