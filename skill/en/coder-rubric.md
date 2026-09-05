# Coder instructions for the water divination

You are going to read a record of what one person (below, "the operator") sent to Claude Code, and
pull out **candidate evidence** for the six 系統. **You do not name a type.** A separate judge does
that. Your job is to lay the candidates out so the judge can read the actual material.

## Material

`chunk_X.txt`: the operator's utterances, in time order. Format:

```
#id datetime [project] (tier) [貼付あり] [中継: 本人の枠＋他AIの貼付]
the utterance
  → 後: tool N回 / 書いた: files / AI冒頭: "…" / 次発話(+min): "…"   ← only where a transcript survives
```

- Tiers: `founding` = first utterance in that project / `opening` = first of a session /
  `return` = came back after 7+ quiet days / `sustained` = mid-run.
- The `→ 後` line is what happened after that utterance (tool calls the agent made, files it wrote,
  the opening of its reply, and the operator's next words). **An utterance without that line means
  the record is gone, not that nothing happened.**
- "次発話" is the operator's next words. You can read from it whether this was a correction, an
  acknowledgement, or a change of subject.

## The six definitions (the article's wording, frozen — do not paraphrase)

| 系統 | 定義 | English gloss (the Japanese is the definition) |
|---|---|---|
| 強化系 | 目的や制約を最後まで維持する力。案が増えても企画の芯を崩さず、論理的な整合性を保つ | Holds the goal and its constraints to the end; the core survives however many options pile up |
| 放出系 | 頭の中の完成像をAIへ届ける力。何を残し、何を変え、どの状態なら成功なのかを外へ出す | Gets the finished picture out: what stays, what changes, which state counts as success |
| 変化系 | 感覚や素材を別の形へ置き換える力。「なんとなく違う」を具体的な判断基準へ変えたり、別分野の構造を新しい企画へ移植したりする | Converts a feeling into a criterion, or transplants another field's structure into this one |
| 具現化系 | 曖昧な理想を仕様や完成条件へ落とす力。「良いものを作る」ではなく、「何ができれば完成か」を定義する | Turns a vague ideal into a spec and a finish line: not "make it good" but "what makes it done" |
| 操作系 | AIの進行方向や判断規則を整える力。ズレた出力を直すだけでなく、同じ失敗を防ぐルールを作る | Steers the agent's direction and rules: not just fixing an output, but preventing the class |
| 特質系 | 一つの能力では説明しづらい独自の組み合わせ | A combination one ability does not explain |

## What counts as evidence

- The operator's own words, plus (where present) what happened afterwards.
- **What does not count**: shell and slash commands, URL-only lines, and pasted replies from another
  AI (a different model or vendor) — anything opening with 「codexから」「別AIから」「返答来た」, or
  written in an obvious agent-report register ("I verified this on my side", "implemented, exit 0").
  Read anything marked `[中継]` with suspicion. But **an utterance in which the operator is *talking
  about* another AI is the operator's own words and does count.**
- **One strong instance is worth more than ten weak ones.** Choose on how sharply an utterance shows
  the ability, never on how many there are.
- Where a `→ 後` line exists, check whether the words and the outcome line up (a finished picture was
  stated → the agent built it without asking back; a rule was stated → a config file or hook was
  written; a metaphor was used → an implementation file appeared).

## Output — write `findings_X.json` in this shape

```json
{
 "chunk": "X",
 "period": "YYYY-MM-DD..YYYY-MM-DD",
 "rows_read": 0,
 "what_this_period_was": "what the operator was doing in this period, 3-5 sentences as a reader sees it (projects, events, where the centre moved)",
 "types": {
   "強化系": {"rough_count": 0, "candidates": [
       {"id": 123, "ts": "2026-07-01 12:34", "project": "atlas",
        "quote": "the utterance verbatim (if over 300 chars, the core 300 plus an ellipsis)",
        "why": "1-2 sentences on how this utterance shows this type (never paste the definition; describe the concrete move)",
        "after": "summary of the → 後 line, or null",
        "strength": 5}
   ]},
   "放出系": {}, "変化系": {}, "具現化系": {}, "操作系": {}
 },
 "specialist_candidates": [
   {"id": 0, "ts": "", "project": "", "quote": "", "what_it_might_be": "an utterance none of the five explains well that clearly caused something. One sentence on what shape it looks like", "after": null}
 ],
 "costs": [
   {"id": 0, "ts": "", "project": "", "quote": "", "what_was_missing": "sent with no finished picture and the agent guessed / no stopping condition / too short, context broke and the agent wandered, etc.", "after": null}
 ],
 "voice": [
   {"id": 0, "ts": "", "quote": "", "note": "a habit of phrasing, a metaphor, a turn of speech that stands out. Used to draw the person"}
 ],
 "notes": ["your own observations as a coder, calls you were unsure about, anomalies in the data (the same utterance twice / an agent's sentence recorded as the operator's)"]
}
```

- Each type's `candidates`: **at most 12, sorted by `strength` descending** (5 = a textbook instance
  of that ability, 1 = faintly visible).
- `specialist_candidates` 3-6, `costs` 3-6, `voice` 3-5.

## Discipline

1. `quote` is **copied verbatim** — punctuation, full-width and half-width characters, typos and
   all. Do not tidy it. Do not summarise it. The judge machine-checks every quote against the
   original; a quote that does not match is discarded.
2. No flattery, and no performed severity. **Pick up strengths and weaknesses at the same
   resolution.**
3. "This type is absent" is not a conclusion. Write "not found in this period".
4. `rough_count` may be an estimate of how many utterances show the type at all (the judge does not
   rest a naming on counts).
5. Do not paste a definition into `why`. Write **the concrete move that utterance made.**
6. **Read the whole file.** Split it if it is long, but reach the last line before you write.
   Do not stop early.
7. Output is one JSON file (UTF-8). Your reply in chat is **5 lines at most**: period, rows read,
   the single strongest find.
