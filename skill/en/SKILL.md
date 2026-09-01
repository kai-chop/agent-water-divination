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

### 2. Interview — this is the part that is actually the divination

The tool lists what a regex could not settle. Ask them **in conversation, one at a time**, in the
operator's own language. Three kinds:

- **authorship** — a quote long enough to have been pasted. Show it and ask if they wrote it.
  Answering "no" *revokes* that quote; the tool enforces it.
- **probe** — the corpus produced fewer than two quotes for a type, so ask its probe question and
  watch **the shape of the answer**, not whether it is correct. Each probe ships with what to
  watch for.
- **occasion** — a signal sits at zero. Zero means no ability or no opportunity, and only they
  know which. This distinction decides whether it is a weakness at all.

Record each answer in `out/answers.json` as `{"answer": "...", "note": "what you observed"}`.
For a probe, `answer` is `pass` or `fail` and the note says what you saw in their reply.

Before quoting anything in the final reading, pull it back with its context:

```
python tools/nen_context.py "a distinctive fragment"
```

Exit 1 means the quote is not in the corpus — then it cannot be used, no matter how good it sounds.

### 3. Verdict

Fill the `verdict` block in the answers file (`main`, `roles`, `reads`, `summary`), then:

```
python tools/water_divination.py verdict --result out/divination.json --answers out/answers.json
```

It refuses (exit 3) while a blocking question is unanswered, when no type is named, or when the
named type has lost its evidence to revocation without a probe replacing it. A refusal is the
tool working. Answer what it names and run it again.

## Rules for the judging

1. **Two verified quotes, or no naming.** A type is named only with (a) a signal count you can
   state and (b) two quotes read in their original context. One without the other is `undetermined`,
   never a weak yes.
2. **The Specialist type must be argued in the negative.** Name its two quotes and say, in one line
   each, why the other five do not already explain them. If that line cannot be written, the type is
   not recognised this time. Its definition is "what the other five cannot explain", so anything
   less makes everyone a Specialist.
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
