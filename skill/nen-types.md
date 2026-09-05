# 系統 canon — the six types, frozen from the published article

Source: note「AIに自分の水見式をさせてみた ―AIの能力ではなく、AIを率いる側の能力を測る」
<https://note.com/aicreatekun/n/n3992b9080059> (published 2026-08-28).

**Why frozen.** The article is public. A reading from a later run only carries meaning if it uses
the same six definitions the published one used — reworded definitions make every later run
incomparable with what has already been written and read. Never edit a definition in place. To
change one, append a version line at the bottom of this file and record the reason in your own
ledger.

The 系統 names, the article's wording, and quoted utterances stay in Japanese verbatim. Both
`skill/ja/SKILL.md` and `skill/en/SKILL.md` point at this one file; there is no translated copy,
because a translated definition is a reworded definition.

## The six (記事の文言)

| 系統 | 定義（記事より） | English gloss (not a definition — the Japanese above is) |
|---|---|---|
| 強化系 | 目的や制約を最後まで維持する力。案が増えても企画の芯を崩さず、論理的な整合性を保つ | Enhancer: holds the goal and its constraints all the way through |
| 放出系 | 頭の中の完成像をAIへ届ける力。何を残し、何を変え、どの状態なら成功なのかを外へ出す | Emitter: gets the finished picture out of their head and into the agent |
| 変化系 | 感覚や素材を別の形へ置き換える力。「なんとなく違う」を具体的な判断基準へ変えたり、別分野の構造を新しい企画へ移植したりする | Transmuter: turns a feeling, or another field's structure, into this one's |
| 具現化系 | 曖昧な理想を仕様や完成条件へ落とす力。「良いものを作る」ではなく、「何ができれば完成か」を定義する | Conjurer: turns a vague ideal into a spec and a finish line |
| 操作系 | AIの進行方向や判断規則を整える力。ズレた出力を直すだけでなく、同じ失敗を防ぐルールを作る | Manipulator: steers the agent's rules, not just its output |
| 特質系 | 一つの能力では説明しづらい独自の組み合わせ | Specialist: a combination the other five cannot account for |

特質系 deliberately has no signature of its own. Its definition is "the combination the other five
cannot explain", so any rule that could detect it would grant it to everybody. It has to be earned
with real quotes plus the negative argument below, or left unnamed.

## Recognition rules

1. **証拠なしの認定禁止.** A 系統 is named only with **two verified quotes** from the corpus —
   verbatim, and confirmed by `tools/verify_quotes.py` before anyone reads the page. Without them
   the entry is written as 未判定, not as a weak yes.
2. **特質系 needs the negative argument.** Name the two quotes and say, in one line each, why
   強化 / 放出 / 変化 / 具現化 / 操作 do not already explain them. If that line cannot be written,
   特質系 is not recognised this round. (The article's own 特質系 finding was 編集者・世界構築者型
   ＝ several candidate ideas rewoven into one world — that is the bar.)
3. **ディフォルメ採点の禁止.** Ambiguous evidence gets both readings and a statement of which way
   the evidence leans. Never fold "could be a strength or a weakness" into a weakness to look
   rigorous.
4. **主武器 = the type carrying the strongest verified evidence**, not the largest count. One
   sharp instance outranks ten faint ones; a high rate on a loose pattern is not a weapon.
5. **Absence is a finding, not a failure.** Three states, never merged: 立った (named, with quotes)
   / 沈黙 (looked for, did not occur) / 測れなかった (no transcript survives — not zero).
6. **Anti-ratchet.** Do not invent a stricter bar than the previous round used. A type may only
   fall if the evidence fell or a real defect appeared in the behaviour.

## Probes — only for a 系統 whose corpus evidence is thin

Fire a probe only when the corpus cannot produce two verified quotes for that 系統. One or two
questions, asked in the live conversation, and **what is observed is the shape of the answer**,
not whether the person "gets it right". Record that the evidence was probe-derived, because a probe
is a stated intention while the corpus is behaviour under no observation.

| 系統 | プローブ（そのまま尋ねる） | 観察するもの |
|---|---|---|
| 強化系 | 「今の作業の目的を、外せない制約3つと一緒に一文で言ってください」 | 制約が目的に従属しているか。制約が目的を押しのけていないか |
| 放出系 | 「完成した状態を、見た目・手ざわり・終わり方の3点で描写してください」 | 完成像が外へ出るか。どの状態を成功と呼ぶかが含まれるか |
| 変化系 | 「その"なんとなく違う"を、他人がそのまま判定できる観察項目に書き換えてください」 | 感覚が観察項目に変わるか。別分野からの移植が出るか |
| 具現化系 | 「これが完成したと**機械が**判定できる条件を1行で書いてください」 | 主観語なしで書けるか。例外が添えられるか |
| 操作系 | 「今のズレが二度と起きないためのルールを1行で書いてください」 | 個別の訂正で終わるか、クラスの規則になるか |
| 特質系 | 「今バラバラに出ている3案を、1つの世界か構造へ編んでください」 | 選別・編集・再構成が起きるか。単なる列挙で終わらないか |
