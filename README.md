# autoresearch-tone-macos

A tiny, public-safe, Mac-friendly **autoresearch loop for prompt optimization**.

It is **conceptually inspired by**:

- `karpathy/autoresearch` — single mutable target, fixed evaluator, keep/revert loop, and a human-written `program.md` that steers the research org.
- `miolini/autoresearch-macos` — the same autoresearch idea adapted to Apple Silicon / macOS.

Instead of training a model, this repo optimizes **one prompt file** so an LLM can better reproduce **your writing tone** from a small corpus of your past posts.

## What it does

1. You prepare a small dataset of your own posts.
2. `prepare.py` builds:
   - a train/validation split
   - a style brief
   - a stylometric profile
3. `evaluate.py` uses the current prompt to generate held-out posts from neutral topic hints.
4. The generated text is scored for:
   - style similarity
   - same-author feel
   - local stylometric similarity
   - copy risk / overfitting
5. **Claude Code** reads `program.md`, edits `prompts/working_prompt.md`, evaluates, and keeps only improvements — acting as an autonomous optimization agent.

This is intentionally simple and small.

## Why this works well on Apple Silicon Macs

The original `karpathy/autoresearch` is built around a fixed budget, one mutable file (`train.py`), and a fixed metric. The macOS fork in `miolini/autoresearch-macos` keeps the same general autoresearch shape while adapting it to Apple Silicon / macOS. This repo reuses that **shape**, but swaps model training for **prompt optimization**, so it runs comfortably on any Apple Silicon Mac (M1 and later).

## Public-safe by default

This repo is designed to be safely published on GitHub:

- it ships with **synthetic sample data only**
- your real posts live under `data/private/`
- `.gitignore` excludes your real datasets, `.env`, generated artifacts, and run logs

Do **not** commit private content or personal exports into a public repository.

## Repository layout

```text
prepare.py                # fixed prep pipeline
evaluate.py               # fixed evaluator
generate.py               # use best prompt on a new topic

program.md                # human-written research brief + experiment loop procedure
CLAUDE.md                 # project instructions for Claude Code
prompts/working_prompt.md # the single file the optimizer edits
prompts/best_prompt.md    # current best prompt

data/sample_raw_posts.jsonl
data/private/README.md

src/tone_autoresearch/
```

## Quick start

### 1) Install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2) Create the environment

```bash
uv sync
cp .env.example .env
```

### 3) Choose a model backend

This repo uses the OpenAI Python client against any **OpenAI-compatible** endpoint.

You can use:

- a hosted API
- a local OpenAI-compatible server
- **Ollama**, via its OpenAI-compatible endpoint at `http://localhost:11434/v1`.

Example `.env` for OpenAI API (recommended):

```bash
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-api-key-here

GENERATOR_MODEL=gpt-5-mini
JUDGE_MODEL=gpt-5
PREP_MODEL=gpt-5-mini
```

Example `.env` for Ollama (local, free):

```bash
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama

GENERATOR_MODEL=qwen2.5:14b
JUDGE_MODEL=qwen2.5:14b
PREP_MODEL=qwen2.5:14b
```

You can also run the repo in a no-API smoke-test mode:

```bash
MOCK_LLM=1
```

That mode is only for checking the loop, not for good style matching.

### 4) Add your posts

Put your real data in:

```text
data/private/raw_posts.jsonl
```

Each line is JSON:

```json
{"text":"Small posts go here.","topic":"what the post is about"}
{"text":"Longer internal message goes here.","topic":"project update on eval quality"}
```

Fields:

- `text`: your original post
- `topic`: optional but **recommended**. A neutral topic hint improves evaluation quality.

If `topic` is missing, `prepare.py` will infer one heuristically, or with `PREP_MODEL` if configured.

### 5) Prepare the dataset

```bash
uv run python prepare.py
```

This creates:

- `artifacts/dataset.json`
- `artifacts/style_profile.json`
- `artifacts/style_brief.md`

### 6) Inspect / edit the research brief

Open `program.md` and adjust the rules if you want a different optimization behavior.

### 7) Run a baseline evaluation

```bash
uv run python evaluate.py --prompt prompts/working_prompt.md
```

Outputs:

- `artifacts/latest_eval.json`
- `artifacts/latest_report.md`

### 8) Start the optimization loop with Claude Code

Launch Claude Code in this directory and say:

```
Have a look at program.md and kick off a new experiment. Start with the setup.
```

Claude Code will read `program.md`, run the evaluation loop, edit `prompts/working_prompt.md`, and keep only improvements. The loop runs **continuously** with 5-minute experiment budgets until you stop it.

### 9) Generate a fresh post

```bash
uv run python generate.py --topic "why small evaluation loops beat big rewrites"
```

## Data tips

For the first pass, use around **20–60 posts**.

Recommended:

- remove URLs if they dominate your corpus
- remove repost boilerplate
- keep language consistent if possible
- supply `topic` manually for the cleanest evaluation
- hold out enough validation examples so the prompt cannot overfit too easily

## Scoring

The evaluator combines:

- LLM judge scores (if configured)
- local stylometric similarity
- length / structure similarity
- anti-copy penalty

The goal is not to clone any one post, but to find a prompt that makes the model feel like **the same writer** across unseen topics.

## A simple workflow for real use

```bash
# 1. add your private dataset
cp data/sample_raw_posts.jsonl data/private/raw_posts.jsonl

# 2. prepare artifacts
uv run python prepare.py

# 3. baseline
uv run python evaluate.py --prompt prompts/working_prompt.md

# 4. start Claude Code and tell it to run program.md
# (runs continuously, Ctrl-C to stop)

# 5. generate a new post
uv run python generate.py --topic "why evals should be productized earlier"
```

## Notes

- This is not a perfect authorship system.
- It is best treated as an **iterative taste loop**.
- The judge model matters a lot.
- Local models are fine for cheap iteration, but a stronger judge usually gives better gradients for optimization.
- **Reasoning models** (GPT-5, o-series, etc.) are supported. The LLM client automatically handles `max_completion_tokens` and `temperature` restrictions.
- If your personal corpus is sensitive, keep `data/private/` out of version control.
- **Claude Code agent design**: The optimization loop is driven by Claude Code itself, not by a Python script. See `CLAUDE.md` and `program.md` for details.

## License

MIT
