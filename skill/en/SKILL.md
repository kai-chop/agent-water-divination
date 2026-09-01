---
name: water-divination
description: Run a water divination on the person directing the AI — measure their own past messages in a date window, interview them about what the numbers cannot settle, and only then name which of six aptitudes their instructions actually show. Use when someone asks to be measured rather than the model ("read me", "what am I good at with AI", "water divination", "which type am I", "run my divination"), or when a periodic self-assessment is due. Not for evaluating a model's output quality.
---

# water-divination — reading the operator, not the model

Six aptitudes, after the Water Divination in *HUNTER × HUNTER*: you hold the glass, and which way
the water changes tells you what you are. Here the glass is a month of your own messages.

The tools count and ask. **You do the judging**, under the rules below.

## Sequence

### 1. Measure

```
python tools/water_divination.py measure --since 2026-08-01 [--until 2026-08-31]
python tools/water_divination.py measure --last 30d
python tools/water_divination.py measure --on 2026-08-15
```

Writes `out/divination.json`, a provisional `out/water-divination.html`, and `out/answers.json`
with one empty slot per open question.

Read the scan report before anything else. `read N, kept M` per source is how you tell a store
that was empty from a store that was never there. Fewer than ~50 of the operator's own messages
is too thin to judge — say so and widen the window rather than producing a confident reading of
almost nothing.

### 2. Interview — after the reading, and kept short

**The reading comes first.** `measure` names what it looks like, then lists what would settle it.
Piling questions in front of an answer turns a divination into paperwork, and nobody comes back
to paperwork. Questions of the same shape are already folded into one by the tool, with the cases
listed under `items` — **do not unfold them**, and leave the optional ones alone unless the
operator asks.

The tool lists what a regex could not settle. Ask them **in conversation, one at a time**, in the
operator's own language. Three kinds:

- **authorship** — a quote long enough to have been pasted. Show it and ask if they wrote it.
  Answering "no" *revokes* that quote; the tool enforces it.
- **probe** — the corpus produced fewer than two quotes for a type, so ask its probe question and
  watch **the shape of the answer**, not whether it is correct. Each probe ships with what to
  watch for.
- **occasion** — a signal or an axis sits at zero, or has too few observations to rate. Zero means
  no ability or no opportunity, and only they know which. This decides whether it is a weakness.
- **attribution** — an axis produced a rate. Ask whether the cases it counted were the same kind
  of work as the rest. A number that only holds on easy work is not an aptitude.
- **rare** — a rare event fired. Show them the moment and ask whether it was deliberate.

Record each answer in `out/answers.json` as `{"answer": "...", "note": "what you observed"}`.
For a probe, `answer` is `pass` or `fail` and the note says what you saw in their reply.

Before quoting anything in the final reading, pull it back with its context:

```
python tools/nen_context.py "a distinctive fragment"
```

Exit 1 means the quote is not in the corpus — then it cannot be used, no matter how good it sounds.

#### The route, and the questions you should expect

Whoever is holding the glass, the shape is the same. Two questions usually stand between a
reading and a name, and both are folded — ask each once, with the cases listed.

```
measure ──► a name ──► two questions ──► verdict ──► the ledger row
            (widest      attribution      refuses      the only thing that
             separation)  authorship      until both   survives the corpus
                                          are answered
```

| Question | What it settles | What a "no" does |
|---|---|---|
| `attribution` | Whether the cases an axis counted were the same kind of work as the rest | "the easier ones" — say so in the reading; the axis stops being an aptitude claim |
| `authorship` | Whether the quotes behind the reading are the operator's own words | naming one drops exactly that quote, and a type can lose its verdict with it |
| `probe` *(optional)* | A type the corpus could not show — ask its probe and watch the shape of the reply | fail: the type is not named this time |
| `occasion` *(optional)* | Whether a zero means no ability or no opportunity | "no occasion" — it is not a weakness |
| `residual` *(optional)* | Whether the leftover holds something the five do not describe | "nothing here" is the ordinary answer |

Do not invent questions beyond these, and do not unfold the folded ones. If the operator answers
"same kind" and "all mine", you are one command from a name — go there rather than asking more.

### 3. Verdict

Fill the `verdict` block in the answers file (`main`, `roles`, `reads`, `summary`), then:

```
python tools/water_divination.py verdict --result out/divination.json --answers out/answers.json
```

It refuses (exit 3) while a blocking question is unanswered, when no type is named, or when the
named type has lost its evidence to revocation without a probe replacing it. A refusal is the
tool working. Answer what it names and run it again.

## Rules for the judging

0. **A divination names what showed. It does not enumerate what could not be measured.** The
   glass gives one reaction. An axis that did not show is **not a weakness and not homework** —
   it is simply not part of this reading. Its numbers stay in the result JSON and the ledger; the
   verdict and the interview leave it alone. Writing "cannot be compared" over and over produces
   a measurement report, not a reading. The tools take the same shape: only axes that reacted are
   drawn into a type's card, and the rest are summarised in one line. **A separation the other way
   is different** — name it as having gone the other way, never folded in with the strengths.
1. **Two verified quotes, or no naming.** A type is named only with (a) a signal count you can
   state and (b) two quotes read in their original context. One without the other is `undetermined`,
   never a weak yes.
2. **Where a type has an axis, the axis outranks the vocabulary.** Counting the words tells you the
   aptitude was exercised; the axis is the only thing that says it worked. A type with a strong
   signal and a weak axis is a habit, not an aptitude — say exactly that. A type whose axis had too
   few observations falls back to the vocabulary, and the reading says which one it rested on.
3. **Specialist is you reading the residual, and saying why.** All the tool does is isolate the
   messages none of the five explain that the agent nonetheless acted on. It claims nothing about
   them — the order is "wording unusual for your own corpus", which is a reading order, not a
   score. Your job is to read that residual and state, with reasons, one of:
   - **there is a Specialist element** — what it is, and one line on why each of the other five
     does not already describe it
   - **there is not** — and what the residual turned out to be instead

   Show the operator the quotes and confirm them. **"There is not" is the ordinary outcome**, not
   a gap. Never argue Specialist from a count: the moment you decide what to count, it stops being
   a residual and becomes another pattern.
3. **Never fold ambiguity into a weakness.** When evidence points both ways, give both readings and
   say which way it leans. Rewriting a neutral or forced move as a flaw to look rigorous makes the
   reading worthless, and it is the most common way this goes wrong.
4. **Main type = the most verified evidence, not the highest percentage.** A big number on a loose
   pattern is not an aptitude.
5. **Zero is a finding with a cause, never an absence.** Report it as "no occasion" or "no attempt"
   based on their answer, or as "the vocabulary may have missed it" — and widening a pattern until
   it matches quotes you already chose is fitting the instrument to the answer. Don't.
6. **Do not raise the bar between readings.** A type falls only when the numbers fell or a real
   defect appeared in behaviour — not because this round's reader is stricter.
7. **Declare your own bias, in one line, about this reading.** Whoever chose the patterns decided
   what counts as evidence; if you have just read this person's rules and style guide, you will tend
   to find the things those documents talk about. Say where that could have landed in *this*
   verdict, concretely. When the main type changes, when a type is recognised for the first time, or
   when you built or edited the instrument in the same session, get a second opinion from a model
   that has not seen this conversation.

## Hard gates

- Never name a type on regex counts alone.
- Never quote a line that `nen_context.py` cannot find.
- Never issue a verdict past a refusal by editing the answers to satisfy the gate — answer the
  question that was asked.
- Keep the six definitions in `patterns/*.json` frozen. Reword them and no past reading can be
  compared with a future one; if one truly must change, add a version and say so in the reading.
- Anything you publish from a reading contains the operator's private words. Ask before it leaves
  the machine, and never include credentials, client names, or third parties' words.

## Repeat readings

Keep the numbers somewhere durable. Transcripts get rotated and deleted — the corpus a reading was
made from is often gone by the next one, and then the recorded numbers are the only surviving
record. State plainly when two readings cover different windows, different instrument versions, or
different corpora; they are not comparable just because they used the same six names.
