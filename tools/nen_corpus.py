# -*- coding: utf-8 -*-
"""nen_corpus — read your own utterances out of agent transcripts, within a time window.

Every other tool in this repo reads the corpus through here. Three jobs:

1. **Find the transcripts.** Several agent CLIs keep local logs in known places. A store that
   isn't installed is skipped silently -- nobody has all of them -- but the scan report always
   names what was actually read, so "configured" is never mistaken for "ran".

2. **Keep only what the human typed.** Agent transcripts store harness-injected text in the same
   "user" slot as real typing: slash-command output, continuation summaries, environment blocks.
   Counting those as the operator's words corrupts every number downstream.

3. **Separate pasted text from written text.** The measured failure that motivated this module:
   in one real corpus, 4.8% of "user messages" were another AI's review pasted in. That share is
   small; its effect was not. Those pastes are dense in correction words, so the operator's
   one-shot correction rate read 26.9% (7/26) with them and 100% (6/6) without. Reporting the
   first number would have described a collapse that never happened.

   Detection is deliberately shallow and always reported as *suspicion*: a long message carrying
   markdown structure (headings, bold, tables), or a long message that names its source in the
   first characters ("according to X", "here's what it said"). Pasted plain prose that names no
   source still gets through -- a stated, permanent limit, not a bug to be tuned away.

Self-test: python tools/nen_corpus.py --self-test
"""
import argparse
import glob
import io
import json
import os
import re
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CORPUS_VERSION = "1"

# Relative paths in a config resolve against the repo root, never the working directory and never
# the config's own folder. One rule, so `--config examples/demo.json` behaves the same from
# anywhere -- CI runs from the root, a user runs from wherever they happen to be.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve(path):
    path = os.path.expanduser(os.path.expandvars(path or ""))
    return path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)

# Stores that keep local transcripts. Absent ones are skipped; the scan report lists what ran.
DEFAULT_SOURCES = [
    {"format": "claude-code", "root": "~/.claude/projects"},
    {"format": "codex", "root": "~/.codex/sessions"},
]

# Harness-injected text that lands in the "user" slot. Prefix match, case-sensitive.
DEFAULT_SKIP_PREFIXES = [
    "<command-name>", "<local-command", "<environment_context", "<user_instructions",
    "Caveat:", "This session is being continued", "[Request interrupted",
    # hook output is delivered in the user slot and reads exactly like something you typed
    "Stop hook feedback", "PreToolUse:", "PostToolUse:", "SessionStart",
    "<system-reminder>", "Tool ran without output",
]

DEFAULTS = {
    "sources": DEFAULT_SOURCES,
    # Order matters twice: signals are OR-ed across every file, but the *wording* a reader sees
    # -- glosses, probe questions, what to watch for -- comes from the first file listed.
    "patterns": ["patterns/en.json", "patterns/ja.json"],
    "skip_prefixes": DEFAULT_SKIP_PREFIXES,
    # Tuned on a Japanese corpus. Japanese packs ~2x the meaning per character, so an English
    # corpus wants roughly double both of these. They are keys, not constants, for that reason.
    "short_chars": 40,
    "paste_min_chars": 300,
    "attribution_head_chars": 40,
}

PASTE_STRUCTURE_RX = re.compile(r"(^|\n)#{2,}\s|\*\*[^*\n]{1,60}\*\*|(^|\n)\s*\|[^\n]*\|")


def load_config(path=None):
    """Config is optional. Without one, the known stores are auto-discovered."""
    cfg = dict(DEFAULTS)
    cfg["config_path"] = None
    if path:
        with io.open(path, encoding="utf-8") as f:
            user = json.load(f)
        cfg.update(user)
        cfg["config_path"] = os.path.abspath(path)
        cfg["_base"] = os.path.dirname(os.path.abspath(path))
    return cfg


# ---------------------------------------------------------------- readers
# Each reader yields (timestamp, session_id, text). Unknown timestamps yield "".

def _text_blocks(content, keys=("text",)):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") in ("text", "input_text", "output_text", None):
                for k in keys:
                    if isinstance(b.get(k), str):
                        out.append(b[k])
        return "\n".join(out).strip()
    return ""


def _read_jsonl(path):
    try:
        fh = io.open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def read_claude_code(root):
    """Claude Code: <root>/<project>/<session>.jsonl. Sub-agent logs live one level deeper
    and are excluded by the glob -- a delegated agent's words are not the operator's."""
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        for d in _read_jsonl(path):
            if d.get("type") != "user" or d.get("isSidechain"):
                continue
            # Present in current versions; older logs omit both, so absence is not disqualifying.
            if d.get("promptSource") not in (None, "typed"):
                continue
            if (d.get("origin") or {}).get("kind") not in (None, "human"):
                continue
            yield (d.get("timestamp", ""), d.get("sessionId", os.path.basename(path)),
                   _text_blocks((d.get("message") or {}).get("content")))


def read_codex(root):
    """Codex CLI rollouts: <root>/YYYY/MM/DD/rollout-*.jsonl, one JSON object per line with
    payload.type == "message". Verified against a real 101-file store, 2026-09-01."""
    for path in sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)):
        session = os.path.basename(path)
        for d in _read_jsonl(path):
            p = d.get("payload")
            if not isinstance(p, dict) or p.get("type") != "message" or p.get("role") != "user":
                continue
            yield (d.get("timestamp", ""), session, _text_blocks(p.get("content")))


def read_chatgpt_export(root):
    """ChatGPT data export: conversations.json, a list of conversations whose `mapping` holds
    message nodes. Covered by a fixture built to the documented shape; see README for the limit."""
    for path in sorted(glob.glob(os.path.join(root, "**", "conversations.json"), recursive=True)):
        try:
            with io.open(path, encoding="utf-8") as f:
                convs = json.load(f)
        except (OSError, ValueError):
            continue
        for conv in convs if isinstance(convs, list) else []:
            session = str(conv.get("id") or conv.get("title") or os.path.basename(path))
            for node in (conv.get("mapping") or {}).values():
                msg = (node or {}).get("message")
                if not isinstance(msg, dict):
                    continue
                if ((msg.get("author") or {}).get("role")) != "user":
                    continue
                parts = (msg.get("content") or {}).get("parts") or []
                text = "\n".join(p for p in parts if isinstance(p, str)).strip()
                ts = msg.get("create_time")
                yield (_epoch_to_iso(ts), session, text)


def read_jsonl_generic(root):
    """Bring your own corpus: one JSON object per line, `text` required, `ts`/`session` optional.
    This is the escape hatch for any agent whose format has no reader here."""
    for path in sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)):
        for d in _read_jsonl(path):
            text = d.get("text") or d.get("content") or ""
            if isinstance(text, (list, dict)):
                text = _text_blocks(text)
            yield (str(d.get("ts") or d.get("timestamp") or ""),
                   str(d.get("session") or os.path.basename(path)), str(text).strip())


def read_text(root):
    """Plain text: one utterance per blank-line-separated block. No timestamps, so a window
    filter cannot apply -- these are read whole or not at all."""
    for path in sorted(glob.glob(os.path.join(root, "**", "*.txt"), recursive=True)):
        try:
            with io.open(path, encoding="utf-8", errors="replace") as f:
                blob = f.read()
        except OSError:
            continue
        for block in re.split(r"\n\s*\n", blob):
            if block.strip():
                yield ("", os.path.basename(path), block.strip())


READERS = {
    "claude-code": read_claude_code,
    "codex": read_codex,
    "chatgpt-export": read_chatgpt_export,
    "jsonl": read_jsonl_generic,
    "text": read_text,
}


def _epoch_to_iso(value):
    try:
        import datetime
        dt = datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
        return dt.replace(tzinfo=None).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


# ---------------------------------------------------------------- window

def in_window(ts, since, until):
    """Compare at the precision the bound was written with.

    `--since 2026-08-01` compares dates; `--since 2026-08-01T14:00` compares to the minute.
    An utterance with no timestamp is kept only when no window was asked for -- silently
    dropping undated text would make a text-file corpus look empty for no visible reason.
    """
    if not since and not until:
        return True
    if not ts:
        return False
    if since and ts[:len(since)] < since:
        return False
    if until and ts[:len(until)] > until:
        return False
    return True


# ---------------------------------------------------------------- authorship

def build_attribution_rx(patterns):
    """Attribution markers come from the pattern files, so a new language needs no code change."""
    alts = [p["shared"]["attribution"] for p in patterns
            if p.get("shared", {}).get("attribution")]
    return re.compile("|".join("(?:%s)" % a for a in alts)) if alts else None


def classify_paste(text, cfg, attribution_rx):
    """None = the operator's own words. Otherwise the shape of the suspicion.

    'structured' -- long and carrying markdown structure (an agent's output shape)
    'attributed' -- long and naming a source in its opening characters

    The opening-characters restriction is load-bearing. Searching the whole message for source
    names also catches messages that merely *talk about* another agent, which are some of the
    most characteristic things an operator writes.
    """
    if len(text) < cfg["paste_min_chars"]:
        return None
    if PASTE_STRUCTURE_RX.search(text):
        return "structured"
    if attribution_rx and attribution_rx.search(text[:cfg["attribution_head_chars"]]):
        return "attributed"
    return None


# ---------------------------------------------------------------- collect

def collect(cfg, since=None, until=None, attribution_rx=None):
    """Return (utterances, scan_report). Utterances carry `paste` = None or the suspicion kind."""
    skip = tuple(cfg["skip_prefixes"])
    seen, out, report = set(), [], []

    for src in cfg["sources"]:
        fmt = src.get("format")
        if not fmt:
            continue                      # a commented-out block in the example config
        root = resolve(src.get("root", ""))
        reader = READERS.get(fmt)
        entry = {"format": fmt, "root": root, "exists": os.path.isdir(root),
                 "read": 0, "kept": 0}
        if reader is None:
            entry["error"] = "unknown format"
        elif entry["exists"]:
            for ts, session, text in reader(root):
                entry["read"] += 1
                if not text or text.startswith(skip):
                    continue
                if not in_window(ts, since, until):
                    continue
                key = (session, ts, text[:80])
                if key in seen:
                    continue
                seen.add(key)
                entry["kept"] += 1
                out.append({"ts": ts, "session": session, "text": text, "source": fmt,
                            "paste": classify_paste(text, cfg, attribution_rx)})
        report.append(entry)

    out.sort(key=lambda m: (m["ts"], m["session"]))
    return out, report


# ---------------------------------------------------------------- timeline
# The signal layer asks what you wrote. The effect layer asks what happened next, which means
# reading the turns the signal layer deliberately throws away: the agent's replies and its tool
# calls. Kept deliberately thin -- an agent's prose is the bulk of a transcript and none of it is
# needed verbatim here, only whether it admits a misread, so it is reduced to a flag on the way in.

TIMELINE_FORMATS = ("claude-code", "codex")


def _mechanism_hit(path, mechanism_rx):
    return bool(path and mechanism_rx and mechanism_rx.search(path))


def _tool_events(blocks, ts, session, mechanism_rx, name_key="name"):
    for b in blocks if isinstance(blocks, list) else []:
        if not isinstance(b, dict) or b.get("type") not in ("tool_use", "custom_tool_call"):
            continue
        inp = b.get("input")
        if isinstance(inp, str):
            path = inp
        elif isinstance(inp, dict):
            path = str(inp.get("file_path") or inp.get("path") or "")
        else:
            path = ""
        yield _event(ts, session, "tool", tool=b.get(name_key) or "?",
                     mechanism=_mechanism_hit(path, mechanism_rx))


def _agent_flags(text, flags):
    """The agent's prose is the bulk of a transcript and none of it is needed verbatim -- only
    whether it admits a misread, asks the operator a question, or shows that it verified."""
    return {name: bool(rx and text and rx.search(text)) for name, rx in flags.items()}


AGENT_FLAGS = ("misread", "question", "verify")


def _event(ts, session, kind, text="", tool="", mechanism=False, flags=None):
    e = {"ts": ts, "session": session, "kind": kind, "text": text,
         "tool": tool, "mechanism": mechanism}
    e.update({name: False for name in AGENT_FLAGS})
    if flags:
        e.update(flags)
    return e


def timeline_claude_code(root, flag_rx, mechanism_rx, skip):
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        for d in _read_jsonl(path):
            if d.get("isSidechain"):
                continue
            ts = d.get("timestamp", "")
            session = d.get("sessionId", os.path.basename(path))
            content = (d.get("message") or {}).get("content")
            text = _text_blocks(content)
            if d.get("type") == "user":
                if (d.get("promptSource") in (None, "typed")
                        and (d.get("origin") or {}).get("kind") in (None, "human")
                        and text and not text.startswith(skip)):
                    yield _event(ts, session, "user", text=text)
            elif d.get("type") == "assistant":
                yield _event(ts, session, "assistant", flags=_agent_flags(text, flag_rx))
                for e in _tool_events(content, ts, session, mechanism_rx):
                    yield e


def timeline_codex(root, flag_rx, mechanism_rx, skip):
    for path in sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)):
        session = os.path.basename(path)
        for d in _read_jsonl(path):
            p = d.get("payload")
            if not isinstance(p, dict):
                continue
            ts = d.get("timestamp", "")
            if p.get("type") == "message":
                text = _text_blocks(p.get("content"))
                if p.get("role") == "user":
                    if text and not text.startswith(skip):
                        yield _event(ts, session, "user", text=text)
                elif p.get("role") == "assistant":
                    yield _event(ts, session, "assistant", flags=_agent_flags(text, flag_rx))
            elif p.get("type") == "custom_tool_call":
                for e in _tool_events([p], ts, session, mechanism_rx):
                    yield e


TIMELINE_READERS = {"claude-code": timeline_claude_code, "codex": timeline_codex}


def collect_timeline(cfg, since=None, until=None, flag_rx=None, mechanism_rx=None,
                     attribution_rx=None):
    """Return (events, sources_without_an_agent_side).

    The second value matters: a plain-text or generic-JSONL corpus holds only your half of the
    conversation, so no effect can be measured from it. Saying so is the difference between
    "the agent never changed" and "this corpus cannot see the agent at all".
    """
    skip = tuple(cfg["skip_prefixes"])
    events, blind = [], []
    for src in cfg["sources"]:
        fmt = src.get("format")
        if not fmt:
            continue
        root = resolve(src.get("root", ""))
        if not os.path.isdir(root):
            continue
        reader = TIMELINE_READERS.get(fmt)
        if reader is None:
            blind.append(fmt)
            continue
        for e in reader(root, flag_rx or {}, mechanism_rx, skip):
            if not in_window(e["ts"], since, until):
                continue
            # the same authorship split the signal layer uses: text you pasted is not your
            # behaviour, and an effect credited to it would be credited to the wrong person
            if e["kind"] == "user":
                e["paste"] = classify_paste(e["text"], cfg, attribution_rx)
            events.append(e)
    events.sort(key=lambda e: (e["session"], e["ts"]))
    return events, sorted(set(blind))


def format_scan_report(report):
    lines = []
    for e in report:
        if e.get("error"):
            state = "ERROR %s" % e["error"]
        elif not e["exists"]:
            state = "absent (skipped)"
        else:
            state = "read %d, kept %d" % (e["read"], e["kept"])
        lines.append("  %-16s %-44s %s" % (e["format"], e["root"], state))
    return "\n".join(lines)


# ---------------------------------------------------------------- self-test

def _self_test():
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    cfg = load_config()
    attrib = re.compile(r"according to|said:|solから|によると")

    # -- paste classification -------------------------------------------------
    long_plain = "I kept going back to the same spot, " + "and it kept happening, " * 30
    structured = "## Verdict\n\n**NOT READY -- three holes.**\n" + "detail. " * 90
    attributed = "according to the reviewer, the framing is right. " + "more body text. " * 30
    about_other = ("codex and claude reviewing each other was never finished, and what I want "
                   "from the reviewer transcripts is " + "the part worth keeping, " * 25)
    check("long plain prose is the operator's own",
          classify_paste(long_plain, cfg, attrib) is None)
    check("markdown-structured long text is flagged structured",
          classify_paste(structured, cfg, attrib) == "structured")
    check("source named up front is flagged attributed",
          classify_paste(attributed, cfg, attrib) == "attributed")
    check("prose merely ABOUT another agent is not flagged",
          classify_paste(about_other, cfg, attrib) is None,
          str(classify_paste(about_other, cfg, attrib)))
    check("short text is never a paste",
          classify_paste("according to the reviewer, no.", cfg, attrib) is None)

    # -- window ---------------------------------------------------------------
    check("date bound compares by date", in_window("2026-08-15T10:00:00Z", "2026-08-01", None))
    check("date bound excludes earlier", not in_window("2026-07-31T23:59:00Z", "2026-08-01", None))
    check("minute bound compares by minute",
          not in_window("2026-08-01T09:59:00Z", "2026-08-01T10:00", None))
    check("undated text survives only without a window",
          in_window("", None, None) and not in_window("", "2026-08-01", None))

    # -- readers against fixtures of each real shape ---------------------------
    with tempfile.TemporaryDirectory() as tmp:
        cc = os.path.join(tmp, "claude", "proj")
        os.makedirs(cc)
        rows = [
            {"type": "user", "promptSource": "typed", "origin": {"kind": "human"},
             "timestamp": "2026-08-02T10:00:00Z", "sessionId": "s1",
             "message": {"content": [{"type": "text", "text": "mine"}]}},
            {"type": "user", "promptSource": "slash", "origin": {"kind": "human"},
             "timestamp": "2026-08-02T11:00:00Z", "sessionId": "s1",
             "message": {"content": [{"type": "text", "text": "slash output"}]}},
            {"type": "user", "isSidechain": True, "promptSource": "typed",
             "origin": {"kind": "human"}, "timestamp": "2026-08-02T12:00:00Z", "sessionId": "s1",
             "message": {"content": [{"type": "text", "text": "subagent"}]}},
            {"type": "assistant", "timestamp": "2026-08-02T13:00:00Z", "sessionId": "s1",
             "message": {"content": [{"type": "text", "text": "reply"}]}},
        ]
        with io.open(os.path.join(cc, "a.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

        cx = os.path.join(tmp, "codex", "2026", "08", "02")
        os.makedirs(cx)
        cxrows = [
            {"type": "response_item", "timestamp": "2026-08-02T10:30:00Z",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "codex mine"}]}},
            {"type": "response_item", "timestamp": "2026-08-02T10:31:00Z",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "codex reply"}]}},
            {"type": "event_msg", "timestamp": "2026-08-02T10:32:00Z",
             "payload": {"type": "token_count", "info": {}}},
        ]
        with io.open(os.path.join(cx, "rollout-x.jsonl"), "w", encoding="utf-8") as f:
            for r in cxrows:
                f.write(json.dumps(r) + "\n")

        gx = os.path.join(tmp, "gpt")
        os.makedirs(gx)
        conv = [{"id": "c1", "mapping": {
            "n1": {"message": {"author": {"role": "user"}, "create_time": 1785000000,
                               "content": {"parts": ["exported mine"]}}},
            "n2": {"message": {"author": {"role": "assistant"}, "create_time": 1785000001,
                               "content": {"parts": ["exported reply"]}}}}}]
        with io.open(os.path.join(gx, "conversations.json"), "w", encoding="utf-8") as f:
            json.dump(conv, f)

        gen = os.path.join(tmp, "gen")
        os.makedirs(gen)
        with io.open(os.path.join(gen, "c.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"ts": "2026-08-02T14:00:00Z", "text": "generic mine"}) + "\n")

        cfg2 = load_config()
        cfg2["sources"] = [
            {"format": "claude-code", "root": os.path.join(tmp, "claude")},
            {"format": "codex", "root": os.path.join(tmp, "codex")},
            {"format": "chatgpt-export", "root": gx},
            {"format": "jsonl", "root": gen},
            {"format": "text", "root": os.path.join(tmp, "nothing-here")},
        ]
        msgs, report = collect(cfg2, attribution_rx=attrib)
        texts = [m["text"] for m in msgs]
        check("claude-code reader keeps typed human messages only",
              "mine" in texts and "slash output" not in texts
              and "subagent" not in texts and "reply" not in texts, str(texts))
        check("codex reader keeps user messages only",
              "codex mine" in texts and "codex reply" not in texts)
        check("chatgpt export reader reads the documented shape", "exported mine" in texts)
        check("generic jsonl reader works", "generic mine" in texts)
        absent = [e for e in report if e["format"] == "text"][0]
        check("a store that isn't installed is skipped, not fatal", absent["exists"] is False)
        check("the scan report names every source it was given", len(report) == 5)

        windowed, _ = collect(cfg2, since="2026-08-02T10:31", attribution_rx=attrib)
        check("window filter applies across every reader",
              [m["text"] for m in windowed] == ["generic mine"],
              str([m["text"] for m in windowed]))

        # -- the timeline: the agent's side, which the signal layer throws away ---------
        tl_dir = os.path.join(tmp, "tl", "proj")
        os.makedirs(tl_dir)
        pasted = "## Review\n**Not ready.**\n" + "body text. " * 40
        tl_rows = [
            {"type": "user", "promptSource": "typed", "origin": {"kind": "human"},
             "timestamp": "2026-08-05T10:00:00Z", "sessionId": "t1",
             "message": {"content": [{"type": "text", "text": "fix the parser"}]}},
            {"type": "assistant", "timestamp": "2026-08-05T10:01:00Z", "sessionId": "t1",
             "message": {"content": [
                 {"type": "text", "text": "Should I start with the lexer? just to check"},
                 {"type": "tool_use", "name": "Edit",
                  "input": {"file_path": "/repo/rules/style.md"}}]}},
            {"type": "assistant", "timestamp": "2026-08-05T10:02:00Z", "sessionId": "t1",
             "message": {"content": [
                 {"type": "text", "text": "I misread that. Now tests pass, exit 0"},
                 {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]}},
            {"type": "user", "promptSource": "typed", "origin": {"kind": "human"},
             "timestamp": "2026-08-05T10:03:00Z", "sessionId": "t1",
             "message": {"content": [{"type": "text", "text": pasted}]}},
        ]
        with io.open(os.path.join(tl_dir, "t.jsonl"), "w", encoding="utf-8") as f:
            for r in tl_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        cfg3 = load_config()
        cfg3["sources"] = [{"format": "claude-code", "root": os.path.join(tmp, "tl")}]
        flags = {"misread": re.compile(r"misread"),
                 "question": re.compile(r"[Ss]hould I|just to check"),
                 "verify": re.compile(r"exit 0|tests pass")}
        evs, blind = collect_timeline(cfg3, flag_rx=flags,
                                      mechanism_rx=re.compile(r"rules?[/\\]"),
                                      attribution_rx=attrib)
        kinds = [e["kind"] for e in evs]
        check("the timeline carries your turns, the agent's, and its tool calls",
              kinds.count("user") == 2 and kinds.count("assistant") == 2
              and kinds.count("tool") == 2, str(kinds))
        check("an agent turn asking you a question is flagged",
              any(e["kind"] == "assistant" and e["question"] for e in evs))
        check("an agent turn admitting a misread is flagged",
              any(e["kind"] == "assistant" and e["misread"] for e in evs))
        check("an agent turn showing verification is flagged",
              any(e["kind"] == "assistant" and e["verify"] for e in evs))
        check("a write into a rules file is flagged as mechanism, a test run is not",
              [e["mechanism"] for e in evs if e["kind"] == "tool"] == [True, False],
              str([(e["tool"], e["mechanism"]) for e in evs if e["kind"] == "tool"]))
        check("pasted text is marked in the timeline too, not just in the signal layer",
              [bool(e.get("paste")) for e in evs if e["kind"] == "user"] == [False, True])

        cfg3["sources"] = [{"format": "jsonl", "root": gen}]
        _, blind = collect_timeline(cfg3, flag_rx=flags)
        check("a corpus with no agent side says so instead of reporting zero effect",
              blind == ["jsonl"], str(blind))

    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="corpus reader for the water divination")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--since")
    ap.add_argument("--until")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    cfg = load_config(args.config)
    msgs, report = collect(cfg, args.since, args.until)
    print("[nen-corpus] alive: version=%s kept=%d" % (CORPUS_VERSION, len(msgs)))
    print(format_scan_report(report))
    return 0 if msgs else 2


if __name__ == "__main__":
    sys.exit(main())
