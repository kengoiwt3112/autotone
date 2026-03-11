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

2. **Platform fit**
   - `x` should usually be tighter and more compressed
   - `slack` can be slightly more contextual and operational

3. **Generalization**
   - the prompt should work across unseen topics
   - do not optimize for one example only

4. **Anti-copy behavior**
   - the generated text should not reuse distinctive phrases
   - the prompt should encourage style transfer, not memorization

## Hard constraints

- Preserve all required placeholders:
  - `{{STYLE_BRIEF}}`
  - `{{PLATFORM}}`
  - `{{TOPIC}}`
  - `{{TARGET_LENGTH}}`
- Output must remain a single prompt template.
- No XML wrappers, no JSON schema, no explanations to the end user.
- The prompt should cause the model to output only the final post text.

## Preferred optimization moves

- tighten the instructions
- improve platform-specific behavior
- make the anti-copy rule explicit
- clarify length control
- make the writing feel more natural, less “LLM-ish”
- avoid generic motivational or corporate language unless it actually appears in the corpus

## Avoid

- overly rigid style rules that flatten the voice
- direct mention of “imitating” or “copying” a specific person
- adding lots of formatting constraints that do not help score
- turning Slack outputs into essay-like prose
- turning X outputs into slogan spam

## Execution model

Each experiment runs for a **fixed 5-minute wall-clock budget**.
The outer loop runs **continuously** — there is no fixed number of experiments.
The loop keeps running until the user stops it manually.

## Acceptance rule

A candidate prompt is only accepted if it improves the measured score.

## Human note

Edit this file if you want the optimization loop to chase a different notion of voice.
