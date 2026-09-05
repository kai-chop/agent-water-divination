# agent-water-divination

[![test](https://github.com/kai-chop/agent-water-divination/actions/workflows/test.yml/badge.svg)](https://github.com/kai-chop/agent-water-divination/actions/workflows/test.yml)

A 水見式 — a water divination — for the person steering an AI agent, rather than for the agent.
Model evaluations are everywhere; the other half of the pair, the one writing the instructions, is
measured by nobody. This carries your own Claude Code history into a readable corpus, and a judge
model reads it and names which of six 系統 your work actually shows: 強化系 (holding the goal),
放出系 (getting the finished picture out), 変化系 (turning a feeling into a criterion), 具現化系
(turning an ideal into a finish line), 操作系 (steering the rules, not just the output), 特質系
(a combination the other five cannot account for). The six are from the article this repository
implements: [AIに自分の水見式をさせてみた](https://note.com/aicreatekun/n/n3992b9080059). The
reading is written in the voice of ウイング — the teacher who explains the test — and the tools
here do not write it. They only carry the text.

> 🇯🇵 **日本語**: [README.ja.md](README.ja.md)

## Why v3 replaced the v1/v2 verdict engine

v1 and v2 scored you: pattern files, per-type signals, a computed main type. Over nine rounds it
kept measuring its own revisions — eight of the nine changed the instrument, and the named type
swung five different ways, every swing caused by an edit to the engine rather than by anything the
person did. The last version of it counted `pip install x` as a founding utterance and its own
build run as top evidence of 放出系. The article's own central finding is that *the analysing AI's
habits leak into the verdict*, and the engine had become an example of it. So v3 removes the engine
entirely: a judge model reads the raw text and names the types, and because a judge can be fluent
and wrong, every quotation on the page is machine-verified against the raw history before anyone
reads it.

## How to run

```
python tools/mizumi_corpus.py --out out
python tools/measure_setup.py --corpus out/corpus.jsonl
python tools/verify_quotes.py page.html
```

| | writes |
|---|---|
| `mizumi_corpus.py` | `out/corpus.jsonl` (every prompt, classified), `out/map.json` (projects × months × chars), `out/chunk_A..C.txt` (chronological thirds, in coder format), `out/heavy.txt` (the prompts ≥ 120 chars — the judge's own read) |
| `measure_setup.py` | setup depth against the reference table below, plus tempo, autonomy-run lengths, hour-of-day, and correction / question / rule / image / metaphor proxies |
| `verify_quotes.py` | `PASS`/`FAIL` per blockquote and `scanned=N matched=M`; exit 1 on any miss **and on zero quotes** |

Defaults are `~/.claude/history.jsonl`, `~/.claude/projects`, and `~/.claude/ledgers/prompt-authorship.jsonl`;
override with `--history`, `--projects`, `--sidecar`, `--claude-dir`, `--out`. Python 3.9+, no
dependencies. Every script has `--self-test`.

Then **give `skill/en/SKILL.md` to your agent** (or `skill/ja/SKILL.md`). That file is the actual
procedure: what the judge reads, how types get named, what may never become evidence, and the shape
of the page.

## What it excludes, and why

A reading is only worth re-reading if the words in it are yours. Four things are dropped before the
corpus is written, and none of them are evidence of anything about you:

- **Commands.** `pip install`, `cd`, `git`, slash commands — you typed them, but they are operating
  a machine, not directing one.
- **Pastes.** `history.jsonl` keeps what you typed and what you pasted in separate fields, so the
  paste never enters the text at all.
- **Other AIs' text.** The hard case: another model's ruling pasted inline into your own prompt.
  `classify_authorship()` names three shapes — `attributed` (a label naming another AI, followed by
  a long inline body), `relay` (your own framing around a paste placeholder: your words, so kept),
  and `suspect_ai` (no label, but the body reads like a ruling or a report — a verdict opener,
  markdown headings, footnote references, three-bullet lists, first-person agent register). The
  first and the third are dropped from every count. Optionally a `UserPromptSubmit` hook can write a
  sidecar at capture time — one JSON object per prompt,
  `{"ts_ms","session","verdict","reasons","chars","secret"}` — and it overrides the retrospective
  guess, because at capture time the answer is known rather than inferred.
- **Secrets.** Tokens and keys are matched and replaced with `[SECRET REDACTED]` in the corpus, and
  the count of redactions is printed.

## 偏差値

Exactly one axis has a real reference population, so exactly one is computed:
偏差値 = 50 + 10·Φ⁻¹(1 − p), where p is the share of the population at or above your level.

| Feature | Share of the sample | 偏差値 if this is all you have |
|---|---|---|
| CLAUDE.md | 84.9 % | 40 |
| settings.json | 41.0 % | 52 |
| skills | 28.1 % | 56 |
| custom commands | 25.6 % | 57 |
| custom subagents | 24.6 % | 57 |
| MCP | 17.0 % | 60 |
| hooks | 13.3 % | 61 |

Source: Build This Now, 2,500 public Claude Code repositories, 2026-06.

**No public per-user distribution exists for the five types themselves.** Any number attached to
them is the judge's estimate, has to be labelled as an estimate on the page, and is not produced by
anything in this repository.

## Privacy

Everything runs locally; nothing is uploaded, and there is no network call anywhere in these three
scripts. The corpus is your own words, so treat it as such: `out/` is gitignored, and you should
read a page yourself before showing it to anybody. Before publishing a reading, run
`tools/verify_quotes.py` against it — a page that quotes you has to quote you exactly, and a page
with no quotes at all fails the check rather than passing it.

---

This repository is not affiliated with, endorsed by, or licensed from the rights holders of
*HUNTER × HUNTER*. Only the six-way framing is borrowed, as a reading of a published work.
MIT licensed — see [LICENSE](LICENSE).
