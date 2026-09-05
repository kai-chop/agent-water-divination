---
name: water-divination
description: Read a person's own Claude Code history back to them and name which of the six 系統 (強化系・放出系・変化系・具現化系・操作系・特質系) from the article "AIに自分の水見式をさせてみた" their work actually shows. Scripts carry the text; a judge model reads it and writes the reading in ウイング's voice, with every quote machine-verified. Trigger on "water divination", "水見式", "read my history", "which type am I", "系統診断", "what's my main weapon".
---

# water-divination — v3 (the judge reads; the instruments only carry)

The deliverable is **a reading a person wants to re-read**: a self-portrait as someone who directs
an AI, with depth, and the thrill of an actual 水見式. A metrology report is a failure even when
every number in it is right.

## Why v3 replaced the v1/v2 verdict engine

v1 and v2 were a scoring engine: pattern files, per-type signals, a computed 主武器. Across nine
rounds in three days, eight of the nine changed the instrument rather than reading the person, and
the named type swung five different ways — every swing caused by an edit to the engine, none by
anything the person did. The last round of it read the history raw and counted `pip install x` as a
founding utterance, `cd project` as 変化系, and its own build run as a top 放出系 instance. About
4,500 lines of Python produced a reading five statistics sentences long. The article's own central
finding — *the analysing AI's habits leak into the verdict* — had become the record.

So v3 keeps no verdict engine. The scripts only carry text; a judge model (a strong one) reads it
and names the types; and because a judge can be fluent and wrong, every quotation on the page is
machine-verified against the raw history before anyone sees it.

## Inputs

| What | Where |
|---|---|
| Layer 1: every prompt the operator sent | `~/.claude/history.jsonl` (display text, paste placeholders, project, session, ms timestamp) |
| Layer 2: what happened afterwards, where a transcript survives | `~/.claude/projects/**/*.jsonl` (joined by session id + timestamp within 20 s) |
| The six definitions (frozen, the article's wording) | `skill/nen-types.md` |
| Coder instructions | `skill/en/coder-rubric.md` |
| Previous rounds, if any | whatever ledger the operator keeps them in |

## Procedure

### 0. Connect
If there is a record of a previous round, read its last entry. Note the previous 主武器 and any
standing advice. Do not re-run an older version's scoring.

### 1. Carry the text (scripts, mechanical)
```
python tools/mizumi_corpus.py --out out
python tools/measure_setup.py --corpus out/corpus.jsonl
```
Outputs into `out/`: `corpus.jsonl` (every prompt classified command / short / substantive /
non_self, tiers founding / return / opening / sustained, transcript-derived `after`), `map.json`
(projects × months × chars), `chunk_A..C.txt` (chronological thirds of the substantive prompts, in
coder format), `heavy.txt` (substantive prompts ≥ 120 chars). `measure_setup.py` prints setup depth
against the public adoption table, plus tempo, uninterrupted autonomy runs, hour-of-day, and
correction / question / rule / image / metaphor proxies. On Windows run `py -3 file`, never a
multi-line `-c`.

### 2. The judge reads (not delegated)
Read **all of `out/heavy.txt`** yourself, in order. This is the part no summary can stand in for.
Everything the reading claims must trace back to a line you read, or to a coder line you then
verified.

### 3. Coders carry candidates (delegated, 3–4 in parallel)
One agent per chronological chunk (split the transcript-rich tail in two). Each reads
`skill/en/coder-rubric.md`, then its chunk **to the last line**, then writes `findings_X.json`: per
type ≤ 12 candidates ranked by strength with a verbatim quote, why, and what followed; 特質系
candidates; costs; voice; notes. Coders extract; they never name a type. Their quotes are verbatim
by contract and are re-verified in step 6.

### 4. Name the types (judge)
- Name from **what happened**, not from vocabulary: the signature of each type is an event (a rule
  became machinery; a metaphor became a file; a constraint survived weeks; an image was delivered
  and built without a question; a vague wish became a completion condition).
- **One strong, verified instance outranks ten weak ones.** Counts are context, never the ground.
- Three states, never merged: 立った (named, with quotes) / 沈黙 (looked for, did not occur) /
  測れなかった (no transcript — not zero).
- 特質系 is **additive**: name the five first, then ask what the five do not explain. Naming it
  requires the negative argument, one line per excluded type. Not finding it is the ordinary result.
- Costs get the same rigour as strengths; each strength's cost is its own reverse side.
- Exclude from evidence: shell and slash commands, URL-only lines, pasted replies from other AIs,
  UI strings, and anything containing a secret, a money figure, a third party's name, or family
  matters.

### 5. 偏差値 (encouragement, with the method shown)
One axis is computable: **setup depth** against the public adoption table below,
偏差値 = 50 + 10·Φ⁻¹(1 − p), where p is the share of the reference population at or above the
operator's level. Every other axis is the judge's estimate and is **labelled as one** on the page
(a hatched bar), with its basis in one line. Never present an estimate as a measurement.

Reference table (refresh when newer public data exists; cite source + date on the page).
Source: Build This Now, 2,500 public Claude Code repositories, 2026-06.

| Feature | Share of the sample | 偏差値 if this is all you have |
|---|---|---|
| CLAUDE.md | 84.9 % | 40 |
| settings.json | 41.0 % | 52 |
| skills | 28.1 % | 56 |
| custom commands | 25.6 % | 57 |
| custom subagents | 24.6 % | 57 |
| MCP | 17.0 % | 60 |
| hooks | 13.3 % | 61 |

**No public per-user distribution exists for the five types themselves.** Say so on the page.

### 6. Write the reading — the voice is ウイング
Order of the page; each section is load-bearing, not decoration:
1. **前口上** — the judge's own habits, declared; what earlier rounds got wrong, in one paragraph.
2. **地図** — window, prompts, sessions, active days, hour band, months × projects, when the centre
   moved. The half the person can check against their own memory; naming comes after it.
3. **六つのコップ** — per type: 反応 (立った / 沈黙 / 測れなかった), signature, 2–4 verbatim quotes
   with date and (when known) what was written afterwards, what the move makes possible, what it
   costs. 主武器 first, 特質系 last with the negative argument.
4. **偏差値** — the computed axis with its table, the estimated axes hatched, basis lines.
5. **代償** — three at most, each the reverse side of a named strength, with the measured proxies.
6. **言葉の癖** — the voice items; readers remember these.
7. **明日から** — at most three 修行, concrete and small. Propose; never edit the person's config.
8. **奥付** — judge, window, corpus counts, coder count, sources, the judge's own habits, what was
   left out, and the quote-verification line.

Voice rules (ウイング of *HUNTER × HUNTER*), kept in the original Japanese because they are the
instruction: 丁寧語で順を追う（「いいですか」「よく聞いてください」）; 誇張しない; 分からないことは
分からないと言う; 代償を褒め言葉より先に置く; 相手を子ども扱いしない; 禁止＝占い師めいた断定・
能力バトル的な誇張・「あなたは特別です」型のお世辞. Definitions are never pasted as a verdict;
quotes are never smoothed. Write in the speaker's language.

### 7. Verify before anyone sees it
```
python tools/verify_quotes.py page.html
```
Every `<blockquote><p>…</p>` must be a verbatim substring of a history.jsonl line; the script prints
`scanned=N matched=M` and exits 1 on any miss **and on zero quotes**. Put that line in the 奥付.

### 8. Publish and record
- Publish the page privately first. Read it yourself before sharing it: it contains the person's
  own words.
- Append **one row** to whatever ledger the operator keeps: window, corpus counts, per-type verdict
  with the anchor quotes' ids, 偏差値 with basis, coder set, the judge's own habits, what was
  excluded. Never edit past rows.

## Hard gates

- **No metrology report.** A page whose spine is denominators and confidence intervals is a failed
  reading regardless of correctness.
- **No name without a verbatim, machine-verified quote.** `verify_quotes.py` must pass.
- Commands, pastes, other AIs' text, secrets, money, third parties, family: never evidence, never
  on the page.
- 偏差値 estimates are labelled as estimates; only the setup axis is called computed.
- 特質系 is additive; naming it requires the negative argument; absence is normal.
- The judge writes the reading. Coders extract only.
- The judge declares their own habits in the 奥付, and where those could have leaned on the reading.
- Past ledger rows are immutable.
- **Do not resurrect a verdict engine.** If a count is wanted, add a proxy to `measure_setup.py`
  and show it as a proxy.
