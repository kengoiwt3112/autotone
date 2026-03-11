# program.md

You are the research brief for a tiny autoresearch loop that optimizes exactly one file:

- `prompts/working_prompt.md`

## Goal

Maximize the evaluator's `overall_score` on held-out examples so the generated text feels like it was written by the same author.

## What matters most

1. **Same-author feel**
   - tone
   - pacing
   - level of confidence
   - sentence rhythm
   - typical compression / expansion
   - punctuation habits

2. **Generalization**
   - the prompt should work across unseen topics
   - do not optimize for one example only

3. **Anti-copy behavior**
   - the generated text should not reuse distinctive phrases
   - the prompt should encourage style transfer, not memorization

## Hard constraints

- Preserve all required placeholders:
  - `{{STYLE_BRIEF}}`
  - `{{TOPIC}}`
  - `{{TARGET_LENGTH}}`
- Output must remain a single prompt template.
- No XML wrappers, no JSON schema, no explanations to the end user.
- The prompt should cause the model to output only the final post text.

## Preferred optimization moves

- tighten the instructions
- make the anti-copy rule explicit
- clarify length control
- make the writing feel more natural, less "LLM-ish"
- avoid generic motivational or corporate language unless it actually appears in the corpus

## Avoid

- overly rigid style rules that flatten the voice
- direct mention of "imitating" or "copying" a specific person
- adding lots of formatting constraints that do not help score
- turning outputs into essay-like prose or slogan spam

---

## Experiment loop procedure

Claude Code follows these steps as an autonomous agent.

### Step 1: Baseline

1. Copy `prompts/best_prompt.md` → `prompts/working_prompt.md`
2. Run evaluation:
   ```bash
   uv run python evaluate.py --prompt prompts/working_prompt.md
   ```
3. Read `artifacts/latest_eval.json` and `artifacts/latest_report.md`
4. Record the baseline `overall_score`
5. Record the experiment start time:
   ```bash
   date +%s
   ```

### Step 2: Rounds (repeat within 5-minute budget)

For each round:

1. **Analyze** — Read `artifacts/latest_report.md` and identify the weakest dimension
2. **Edit** — Directly edit `prompts/working_prompt.md` to address the weakness
3. **Evaluate** — Run:
   ```bash
   uv run python evaluate.py --prompt prompts/working_prompt.md
   ```
4. **Compare** — Read `artifacts/latest_eval.json` and compare `overall_score` to best so far
5. **Decision**:
   - **KEEP** if score improved → copy `prompts/working_prompt.md` → `prompts/best_prompt.md`, update best score
   - **REVERT** if score did not improve → copy `prompts/best_prompt.md` → `prompts/working_prompt.md`
6. **Report** — Print a 1-line summary: `Round N: score X.XX → Y.YY [KEEP/REVERT]`
7. **Time check** — Run `date +%s` and compare to start time. If 300+ seconds elapsed, end the experiment.

### Step 3: Experiment end

1. Print a summary of the experiment: rounds completed, best score achieved, key changes kept
2. Start the next experiment immediately (go back to Step 1)
3. This loop runs **forever** until the user stops it manually

## Acceptance rule

A candidate prompt is only accepted if it improves the measured score.

## Time management

Use `date +%s` at the start of each experiment and before each new round to check elapsed time. Each experiment has a **5-minute (300 second) wall-clock budget**.

## NEVER STOP

Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — re-read the latest report for new angles, try combining previous near-misses, try more radical prompt rewrites, revisit dimensions you haven't targeted yet. The loop runs until the human interrupts you, period.

## Human note

Edit this file if you want the optimization loop to chase a different notion of voice.
