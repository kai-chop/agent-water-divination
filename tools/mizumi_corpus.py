# -*- coding: utf-8 -*-
"""mizumi_corpus — carry the operator's prompts into a readable corpus (v3: scripts carry, a judge reads).

Layer 1: history.jsonl            one line per prompt the operator sent (display text, paste placeholders)
Layer 2: projects/**/*.jsonl      transcripts, where they still exist: what was written afterwards

Outputs (into --out):
  corpus.jsonl   every prompt: kind (command / short / substantive / non_self), tiers, authorship, after
  map.json       projects x months x chars, counts
  chunk_A..C.txt chronological thirds of the substantive prompts, coder format
  heavy.txt      substantive prompts >= HEAVY_CHARS (the judgment-layer read)

Authorship: another AI's text lands in the operator's prompt slot in three shapes — a labelled
inline paste (「codexから　…」), a bare inline paste of a ruling/report, or a label + paste
placeholder. `classify_authorship()` names them attributed / suspect_ai / relay and the corpus
drops attributed + suspect_ai from every count. A sidecar written at capture time by a
UserPromptSubmit hook (`prompt-authorship.jsonl`) overrides the retro classification when present.

Self-test: python mizumi_corpus.py --self-test
"""
import argparse
import collections
import datetime
import glob
import io
import json
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CORPUS_VERSION = "3"
SHORT_CHARS = 15            # below this a prompt is an ack/command, not an utterance worth coding
HEAVY_CHARS = 120           # above this the operator is spending words: judgment-layer read
DORMANT_DAYS = 7            # a return = first prompt in a project after this many quiet days
TS_MATCH_SEC = 20           # history <-> transcript join tolerance
ATTRIBUTED_MIN_BODY = 150   # a label followed by this much inline text = someone else's words
SUSPECT_MIN_CHARS = 400     # style-based suspicion needs length + >=2 style hits
VERDICT_MIN_CHARS = 200     # a "ruling voice" opener is enough at this length

CMD_RX = re.compile(r"^\s*(!|/[a-z]|pip |cd |py |python|git |ls\b|dir\b|cat |npm |dotnet |pwsh|powershell|claude\b)", re.I)
PLACEHOLDER_RX = re.compile(r"\[Pasted text #\d+")
# A label naming another AI, used as a label (whitespace right after it), not as a grammatical subject.
LABEL_RX = re.compile(r"^\s*(?:(?:sol|codex|gpt|gemini|chatgpt|別ai|他ai)\s*(?:から|より)(?:贈り物|の返答|の回答|の裁定|の査読|の指摘|返信)?|返答来た|返事来た)[\s　]", re.I)
AI_STYLE = [
    (re.compile(r"裁定します|裁定：|VERDICT|GO-WITH|承ります|受領しました"), "verdict_voice"),
    (re.compile(r"(^|\n)#{1,4} |\*\*[^*\n]{2,40}\*\*"), "markdown_headings_bold"),
    (re.compile(r"\[\d+\]: https?://|\(\[[^\]\n]+\]\[\d+\]\)"), "footnote_refs"),
    (re.compile(r"(^|\n)\s*[-*] .+\n\s*[-*] .+\n\s*[-*] "), "bullet_list_3"),
    (re.compile(r"私の側でも|私は[^\n]{0,30}します|こちらで[^\n]{0,20}しました|実装しました|反映済み"), "first_person_ai"),
    (re.compile(r"§\d|\bexit 0\b|sha256|toolu_|<task-notification>|<local-command"), "machine_tokens"),
]
SECRET_RX = re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gho_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}")
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
WRITE_CMD_RX = re.compile(r"Set-Content|Out-File|Add-Content|New-Item|sed\s+-i|>>|(?<![0-9\-<])>(?![=>])")


def classify_authorship(text):
    """-> (verdict, reasons). verdict in self / relay / attributed / suspect_ai.

    relay      = the operator's own framing around a paste placeholder (own words; the paste is not here)
    attributed = a label naming another AI followed by their inline text
    suspect_ai = no label, but the body reads like a ruling / report (>=2 style marks)
    """
    t = text or ""
    m = LABEL_RX.match(t)
    if m:
        body = t[m.end():]
        if PLACEHOLDER_RX.search(body):
            return "relay", ["label+placeholder"]
        if len(body.strip()) >= ATTRIBUTED_MIN_BODY:
            return "attributed", ["label+inline_body"]
        return "self", ["label+short_own_sentence"]
    hits = [name for rx, name in AI_STYLE if rx.search(t)]
    if len(t) >= SUSPECT_MIN_CHARS and len(hits) >= 2:
        return "suspect_ai", hits
    if "verdict_voice" in hits and len(t) >= VERDICT_MIN_CHARS:
        return "suspect_ai", hits
    return "self", []


def has_secret(text):
    return bool(SECRET_RX.search(text or ""))


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [x.get("text") or "" for x in content if isinstance(x, dict) and x.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def read_history(path):
    """Rows a corpus can be built from, in file order, timestamps normalised to ms.

    A live history.jsonl is appended to while it is read, so the last line can be half-written;
    older writers stored seconds. Skipping a line is the honest response to both -- the count in
    the alive line is of rows that were actually usable.
    """
    rows = []
    for line in io.open(path, encoding="utf-8", errors="replace"):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not isinstance(r, dict) or not isinstance(r.get("display"), str) or not r.get("sessionId"):
            continue
        try:
            ts = int(r.get("timestamp"))
        except (TypeError, ValueError):
            continue
        r["timestamp"] = ts * 1000 if ts < 10000000000 else ts
        rows.append(r)
    return rows


def parse_transcript(path, offset):
    """User turns in order: {dt, text, tools, wrote, ai_first, next_text, next_gap_min}."""
    turns, cur = [], None
    for l in io.open(path, encoding="utf-8", errors="replace"):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        t = r.get("type")
        if t not in ("user", "assistant") or r.get("isSidechain") or r.get("isMeta"):
            continue
        c = (r.get("message") or {}).get("content")
        ts = r.get("timestamp")
        if t == "user":
            if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
                continue
            txt = text_of(c).strip()
            if not txt:
                continue
            cur = {"dt": iso_to_dt(ts, offset) if ts else None, "text": txt, "tools": 0, "wrote": [], "ai_first": ""}
            turns.append(cur)
        elif cur is not None and isinstance(c, list):
            for x in c:
                if not isinstance(x, dict):
                    continue
                if x.get("type") == "text" and not cur["ai_first"]:
                    cur["ai_first"] = (x.get("text") or "").strip()[:220]
                elif x.get("type") == "tool_use":
                    cur["tools"] += 1
                    name, inp = x.get("name") or "", x.get("input") or {}
                    if name in WRITE_TOOLS and isinstance(inp, dict) and inp.get("file_path"):
                        cur["wrote"].append(os.path.basename(inp["file_path"]))
                    elif name in ("Bash", "PowerShell") and isinstance(inp, dict) and WRITE_CMD_RX.search(inp.get("command") or ""):
                        cur["wrote"].append("(shell)")
    for i, tr in enumerate(turns):
        nxt = turns[i + 1] if i + 1 < len(turns) else None
        tr["next_text"] = nxt["text"][:160] if nxt else ""
        tr["next_gap_min"] = round((nxt["dt"] - tr["dt"]).total_seconds() / 60, 1) if nxt and nxt["dt"] and tr["dt"] else None
        tr["wrote"] = sorted(set(tr["wrote"]))[:8]
    return turns


def iso_to_dt(s, offset):
    return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + offset


def ms_to_dt(ms, offset):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).replace(tzinfo=None) + offset


def load_sidecar(path):
    """Capture-time verdicts: {(session, minute_key): verdict}. Missing file = empty."""
    out = {}
    if not path or not os.path.isfile(path):
        return out
    for l in io.open(path, encoding="utf-8", errors="replace"):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("session") and r.get("ts_ms") and r.get("verdict"):
            out[(r["session"], r["ts_ms"] // 1000)] = r["verdict"]
    return out


def sidecar_lookup(sidecar, session, ts_ms):
    sec = ts_ms // 1000
    for d in range(-5, 6):
        v = sidecar.get((session, sec + d))
        if v:
            return v
    return None


def build(history, projects, out_dir, offset, sidecar_path=None):
    rows = read_history(history)
    rows.sort(key=lambda r: r["timestamp"])
    tfiles = {os.path.basename(p)[:-6]: p for p in glob.glob(os.path.join(projects, "*", "*.jsonl"))} if projects else {}
    turns_by_session = {sid: parse_transcript(tfiles[sid], offset) for sid in {r["sessionId"] for r in rows} if sid in tfiles}
    sidecar = load_sidecar(sidecar_path)

    first_in_project, last_in_project, first_in_session = {}, {}, set()
    out, joined = [], 0
    for i, r in enumerate(rows):
        dt = ms_to_dt(r["timestamp"], offset)
        proj = os.path.basename((r.get("project") or "").rstrip("\\/")) or (r.get("project") or "?")
        disp = r.get("display") or ""
        verdict, reasons = classify_authorship(disp)
        cap = sidecar_lookup(sidecar, r["sessionId"], r["timestamp"])
        if cap:
            verdict, reasons = cap, ["sidecar"]
        if verdict in ("attributed", "suspect_ai"):
            kind = "non_self"
        elif CMD_RX.match(disp):
            kind = "command"
        elif len(disp) < SHORT_CHARS:
            kind = "short"
        else:
            kind = "substantive"
        tiers = []
        if proj not in first_in_project:
            first_in_project[proj] = dt
            tiers.append("founding")
        elif (dt - last_in_project[proj]).days >= DORMANT_DAYS:
            tiers.append("return")
        last_in_project[proj] = dt
        if r["sessionId"] not in first_in_session:
            first_in_session.add(r["sessionId"])
            tiers.append("opening")
        if not tiers:
            tiers.append("sustained")
        rec = {"id": i, "ts": dt.strftime("%Y-%m-%d %H:%M"), "project": proj, "session": r["sessionId"],
               "kind": kind, "tiers": tiers, "chars": len(disp), "paste": bool(r.get("pastedContents")),
               "authorship": verdict, "authorship_reasons": reasons, "secret": has_secret(disp),
               "text": "[SECRET REDACTED]" if has_secret(disp) else disp}
        turns = turns_by_session.get(r["sessionId"])
        if turns:
            best = None
            for tr in turns:
                if tr["dt"] and abs((tr["dt"] - dt).total_seconds()) <= TS_MATCH_SEC:
                    best = tr
                    break
            if best is None:
                head = disp.split("[Pasted")[0][:40]
                for tr in turns:
                    if head and tr["text"].startswith(head):
                        best = tr
                        break
            if best:
                joined += 1
                rec["after"] = {"tools": best["tools"], "wrote": best["wrote"], "ai_first": best["ai_first"],
                                "next_text": best["next_text"], "next_gap_min": best["next_gap_min"]}
        out.append(rec)

    os.makedirs(out_dir, exist_ok=True)
    with io.open(os.path.join(out_dir, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for rec in out:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    subst = [r for r in out if r["kind"] == "substantive"]
    by_proj = collections.defaultdict(lambda: {"utterances": 0, "chars": 0, "sessions": set(), "days": set(), "first": None, "last": None})
    by_month = collections.defaultdict(collections.Counter)
    for r in subst:
        p = by_proj[r["project"]]
        p["utterances"] += 1
        p["chars"] += r["chars"]
        p["sessions"].add(r["session"])
        p["days"].add(r["ts"][:10])
        p["first"] = p["first"] or r["ts"][:10]
        p["last"] = r["ts"][:10]
        by_month[r["ts"][:7]][r["project"]] += 1
    kinds = collections.Counter(r["kind"] for r in out)
    auth = collections.Counter(r["authorship"] for r in out)
    mp = {"corpus_version": CORPUS_VERSION,
          "window": [out[0]["ts"], out[-1]["ts"]] if out else None,
          "prompts_total": len(out), "kinds": dict(kinds), "authorship": dict(auth),
          "secrets_redacted": sum(1 for r in out if r["secret"]),
          "substantive": len(subst), "substantive_chars": sum(r["chars"] for r in subst),
          "median_chars_substantive": sorted(r["chars"] for r in subst)[len(subst) // 2] if subst else None,
          "heavy": sum(1 for r in subst if r["chars"] >= HEAVY_CHARS),
          "with_transcript": joined,
          "sessions": len({r["session"] for r in out}),
          "projects": {k: {"utterances": v["utterances"], "chars": v["chars"], "sessions": len(v["sessions"]),
                           "active_days": len(v["days"]), "first": v["first"], "last": v["last"]}
                       for k, v in sorted(by_proj.items(), key=lambda kv: -kv[1]["utterances"])},
          "months": {m: dict(c.most_common()) for m, c in sorted(by_month.items())}}
    with io.open(os.path.join(out_dir, "map.json"), "w", encoding="utf-8") as f:
        json.dump(mp, f, ensure_ascii=False, indent=1)

    def fmt(r):
        head = "#%04d %s [%s] (%s)%s%s" % (r["id"], r["ts"], r["project"], "/".join(r["tiers"]),
                                            " [貼付あり]" if r["paste"] else "",
                                            " [中継: 本人の枠＋他AIの貼付]" if r["authorship"] == "relay" else "")
        lines = [head, r["text"]]
        a = r.get("after")
        if a:
            w = ", ".join(a["wrote"]) if a["wrote"] else "なし"
            nxt = ("次発話(+%s分): 「%s」" % (a["next_gap_min"], a["next_text"])) if a["next_text"] else "次発話: (セッション終了)"
            lines.append("  → 後: tool %d回 / 書いた: %s / AI冒頭: 「%s」 / %s" % (a["tools"], w, a["ai_first"].replace("\n", " "), nxt.replace("\n", " ")))
        return "\n".join(lines)

    n = len(subst)
    cuts = [0, n // 3, 2 * n // 3, n]
    for name, (a, b) in zip("ABC", zip(cuts, cuts[1:])):
        with io.open(os.path.join(out_dir, "chunk_%s.txt" % name), "w", encoding="utf-8") as f:
            f.write("\n\n".join(fmt(r) for r in subst[a:b]))
    with io.open(os.path.join(out_dir, "heavy.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(fmt(r) for r in subst if r["chars"] >= HEAVY_CHARS))
    return mp


def default_offset():
    return datetime.timedelta(seconds=time.localtime().tm_gmtoff)


def _self_test():
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + label + ("  " + detail if detail else ""))

    # ~440 chars of filler: a real pasted ruling runs 2,000-7,000. Synthetic text throughout --
    # nothing in this file is taken from anybody's history.
    filler = "この判定は契約条項の読みに基づくもので、" * 20
    cases = [
        ("codexから　その捉え方が一番しっくりきます。" + filler, "attributed"),
        ("codexから贈り物　[Pasted text #7 +36 lines]　次はこれを収蔵して", "relay"),
        ("返答来た　[Pasted text #3]", "relay"),
        ("codexから返信来たけど別のPCへ投げればいい？", "self"),
        ("claudeからcodexに話しかける時は強いモデル同士で話せるし途中の状態も見えて生存が分かる", "self"),
        ("codexの裁定に対して書記みたいになってるけどこのまま進めても大丈夫だと思う？", "self"),
        ("裁定します。これは **公開範囲の ruling** であり、法的助言ではありません。\n## 1. 一つ目の論点\n**裁定: FAIL。**\n" + filler, "suspect_ai"),
        ("ある。**2010〜2017を本命にする**。\n- 一つ目\n- 二つ目\n- 三つ目\n([出典][1])\n\n[1]: https://example.org/x\n" + filler, "suspect_ai"),
        ("から見つかる気があまりしない。字面主義を除けばこれがベストという話だった実情からも", "self"),
        ("できてたのを確認しました。再配分時の数字は配分値合計以上は振れない機能をつけて。", "self"),
        ("矛盾指摘は示唆的だが強みを活かそうという根っこからは離れるな", "self"),
    ]
    for text, want in cases:
        got, why = classify_authorship(text)
        check("authorship %-11s %s" % (want, text[:28].replace("\n", " ")), got == want, "got=%s %s" % (got, why))
    check("secret pattern is recognised", has_secret("token ghp_" + "a" * 36 + " here") and not has_secret("普通の文"))

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        hist = os.path.join(tmp, "h.jsonl")
        base = 1750000000000
        recs = [
            {"display": "pip install x", "pastedContents": {}, "timestamp": base, "project": "/p/alpha", "sessionId": "s1"},
            {"display": "会場を新設するMODを作りたい。二階からのダイブも入れる。", "pastedContents": {}, "timestamp": base + 60000, "project": "/p/alpha", "sessionId": "s1"},
            {"display": "codexから　" + filler, "pastedContents": {}, "timestamp": base + 120000, "project": "/p/alpha", "sessionId": "s1"},
            {"display": "やって", "pastedContents": {}, "timestamp": base + 180000, "project": "/p/alpha", "sessionId": "s2"},
            {"display": "鍵 ghp_" + "b" * 36, "pastedContents": {}, "timestamp": base + 240000, "project": "/p/alpha", "sessionId": "s2"},
        ]
        with io.open(hist, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.write("{\"display\": \"a line that never closes\n")   # a live file is appended to while it is read
            f.write("\n")
        side = os.path.join(tmp, "side.jsonl")
        io.open(side, "w", encoding="utf-8").write(json.dumps({"ts_ms": base + 60000, "session": "s1", "verdict": "suspect_ai"}) + "\n")
        mp = build(hist, None, os.path.join(tmp, "out"), datetime.timedelta(0), side)
        check("half-written last line skipped, not fatal", mp["prompts_total"] == 5, str(mp["prompts_total"]))
        check("kinds counted", mp["kinds"] == {"command": 1, "non_self": 2, "short": 1, "substantive": 1}, str(mp["kinds"]))
        check("sidecar overrides retro classification", mp["authorship"].get("suspect_ai") == 1 and mp["authorship"].get("attributed") == 1, str(mp["authorship"]))
        check("secret redacted in corpus", mp["secrets_redacted"] == 1 and "ghp_b" not in io.open(os.path.join(tmp, "out", "corpus.jsonl"), encoding="utf-8").read())
        check("chunks written without non_self", os.path.isfile(os.path.join(tmp, "out", "chunk_A.txt")) and "codexから" not in io.open(os.path.join(tmp, "out", "chunk_C.txt"), encoding="utf-8").read())

    with tempfile.TemporaryDirectory() as tmp:
        hist = os.path.join(tmp, "sec.jsonl")
        io.open(hist, "w", encoding="utf-8").write(json.dumps(
            {"display": "秒で記録された古い行も同じ日付に落ちること", "pastedContents": {},
             "timestamp": 1750000000, "project": "/p/beta", "sessionId": "s9"}, ensure_ascii=False) + "\n")
        mp = build(hist, None, os.path.join(tmp, "out"), datetime.timedelta(0), None)
        check("second-precision timestamps land in the right year", mp["window"][0].startswith("2025-06"), str(mp["window"]))
    print("\n%s" % ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


def main():
    home = os.path.expanduser("~")
    ap = argparse.ArgumentParser(description="carry the operator's prompts into a readable corpus")
    ap.add_argument("--history", default=os.path.join(home, ".claude", "history.jsonl"))
    ap.add_argument("--projects", default=os.path.join(home, ".claude", "projects"))
    ap.add_argument("--sidecar", default=os.path.join(home, ".claude", "ledgers", "prompt-authorship.jsonl"))
    ap.add_argument("--out", default=os.path.join(".", "out"))
    ap.add_argument("--tz-offset", type=float, default=None, help="hours; default = this machine's local offset")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    offset = datetime.timedelta(hours=args.tz_offset) if args.tz_offset is not None else default_offset()
    mp = build(args.history, args.projects if os.path.isdir(args.projects) else None, args.out, offset, args.sidecar)
    print("[mizumi-corpus] alive: version=%s prompts=%d kinds=%s authorship=%s secrets_redacted=%d with_transcript=%d out=%s"
          % (CORPUS_VERSION, mp["prompts_total"], mp["kinds"], mp["authorship"], mp["secrets_redacted"], mp["with_transcript"], args.out))
    return 0 if mp["prompts_total"] else 1


if __name__ == "__main__":
    sys.exit(main())
