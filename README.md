# autotone

The idea: give an AI agent a writing style corpus and let it experiment overnight. It modifies the prompt, generates text in your voice, checks if the result matches your tone, keeps or discards, and repeats. You wake up in the morning to a log of experiments and (hopefully) a prompt that writes like you. This is [autoresearch](https://github.com/karpathy/autoresearch) applied to **prompt optimization** instead of model training — same shape, different domain.

## How it works

The repo is deliberately kept small and only really has four files that matter:

- **`prepare.py`** — one-time data prep (splits your posts into train/validation, builds a style profile, infers topics). Not modified.
- **`evaluate.py`** — the fixed evaluator. Generates text from the prompt, scores it against your real writing style using LLM judges and local stylometrics. Not modified.
- **`prompts/default_prompt.md`** — the starter template shipped with the repo. Auto-copied to `working_prompt.md` on first run. Not modified after that.
- **`prompts/working_prompt.md`** — the single file the agent edits. Contains the full system prompt that tells the LLM how to write like you. **This file is edited and iterated on by the agent.** (gitignored)
- **`program.md`** — instructions for the agent. Point Claude Code here and let it go. **This file is edited and iterated on by the human.**

By design, each experiment runs for a **fixed 5-minute time budget**. The metric is **overall_score** — higher is better. It combines LLM judge assessments (style similarity, same-author likelihood, topic fidelity) with local stylometric features (punctuation patterns, rhythm, compression) and an anti-copy penalty to prevent memorization.

## Quick start

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv/), an LLM API endpoint (OpenAI, Gemini, Anthropic, or Ollama for local inference).

```bash
# 1. Install uv (if you don't already have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Set up your API credentials
cp .env.example .env
# Edit .env with your model backend

# 4. Add your posts
#    Put your writing samples in data/private/raw_posts.jsonl
#    One JSON object per line, only "text" is required:
#    {"text":"Your post goes here."}

# 5. Prepare the dataset (one-time)
uv run python prepare.py

# 6. Run a single evaluation
uv run python evaluate.py --prompt prompts/working_prompt.md

# 7. (Optional) Generate human-readable report + raw JSON with raw text
uv run python evaluate.py --prompt prompts/working_prompt.md --report
```

If the above commands all work ok, your setup is working and you can go into autonomous research mode.

Smoke-test mode (no API needed): `MOCK_LLM=1`

## Running the agent

Simply spin up Claude Code in this repo, then prompt something like:

```
Have a look at program.md and kick off a new experiment. Start with the setup.
```

The agent then autonomously iterates — editing the prompt, evaluating, keeping improvements — in 5-minute experiment cycles until you stop it.

## Project structure

```
prepare.py                  — data prep + style profiling (do not modify)
evaluate.py                 — evaluator + scoring (do not modify)
generate.py                 — generate a post from the optimized prompt
prompts/default_prompt.md   — starter prompt template (shipped with repo)
prompts/working_prompt.md   — system prompt (agent modifies this, gitignored)
prompts/best_prompt.md      — best prompt so far (auto-updated, gitignored)
program.md                  — agent instructions
src/autotone/               — library code (do not modify)
tests/                      — minimal regression tests
data/private/raw_posts.jsonl — your writing samples (gitignored)
```

## Artifacts

The evaluator writes a few different files under `artifacts/`. They are meant for different audiences:

- `latest_eval.json` — **redacted by default**. Safe summary of scores, lengths, and structured metrics. No raw reference text, generated text, or judge free-text comments.
- `latest_agent_input.json` — safe structured input for the autonomous agent. This is the file the agent should read when deciding what to try next.
- `latest_eval_raw.json` — raw evaluation output including reference text and generated text. Only created when you pass `--report`.
- `latest_report.md` — human-readable markdown report with raw text examples. Only created when you pass `--report`.
- `style_profile.json` / `style_brief.md` / `dataset.json` — outputs from `prepare.py`.

## Design choices

- **Single file to modify.** The agent only touches `prompts/working_prompt.md`. This keeps the scope manageable and diffs reviewable.
- **Fixed time budget.** Each experiment runs for 5 minutes. This means roughly 12 experiments/hour, ~100 experiments overnight. Results are directly comparable regardless of what the agent changes in the prompt.
- **Self-contained.** No external dependencies beyond OpenAI/Anthropic clients and dotenv. No fine-tuning, no embeddings, no vector databases. One prompt, one evaluator, one metric.
- **Public-safe by default.** Ships with synthetic sample data only. Your real posts live under `data/private/` (gitignored). `.gitignore` excludes `.env`, generated artifacts, and run logs.

## Model backends

Set `LLM_PROVIDER` in `.env` to choose the backend. OpenAI, Gemini, and Ollama all use the OpenAI-compatible protocol (`LLM_PROVIDER=openai`). Anthropic uses its own SDK (`LLM_PROVIDER=anthropic`).

| Backend | `LLM_PROVIDER` | `OPENAI_BASE_URL` | Example models |
|---------|----------------|-------------------|----------------|
| OpenAI | `openai` | `https://api.openai.com/v1` | gpt-5-mini, gpt-5 |
| Gemini | `openai` | `https://generativelanguage.googleapis.com/v1beta/openai/` | gemini-2.5-flash, gemini-2.5-pro |
| Ollama | `openai` | `http://localhost:11434/v1` | qwen2.5:14b |
| Anthropic | `anthropic` | *(not used)* | claude-sonnet-4-20250514 |

Reasoning models (GPT-5, o-series, etc.) are supported. The LLM client automatically handles `max_completion_tokens` and `temperature` restrictions.

## Data tips

For the first pass, use around **20–60 posts**.

- Only `text` is required — topics and metadata are auto-generated
- Remove URLs if they dominate your corpus
- Remove repost boilerplate
- Keep language consistent if possible

## Safety

**Sandbox mode:** When running the agent autonomously, restrict permissions so that it can only write to `prompts/working_prompt.md` and read `artifacts/`. Disable network access and git push from the agent session.

**Artifact privacy:** By default, `artifacts/latest_eval.json` is redacted and excludes raw reference/generated text plus judge free-text comments. Raw text artifacts are only written when you pass `--report`, which creates `artifacts/latest_eval_raw.json` and `artifacts/latest_report.md` for human review.

**API privacy:** All writing samples and generated text are sent to your configured API provider (OpenAI, Gemini, Anthropic, Ollama, etc.) for generation and judging. If using a cloud API, your data leaves your machine. For maximum privacy, use a local model via Ollama.

**Cost awareness:** Each experiment cycle makes multiple API calls (generation + judging per validation example). With cloud APIs, costs can accumulate during overnight runs. Set `MAX_EVALUATIONS` in `.env` to cap the total number of evaluation runs — the evaluator enforces this as a hard stop at the code level, regardless of how it is invoked. The legacy name `MAX_EXPERIMENTS` is still accepted for compatibility.

**Terminology:** A 5-minute "experiment" in `program.md` may contain multiple evaluations (baseline + several rounds). `MAX_EVALUATIONS` limits evaluator invocations, not 5-minute experiment cycles.

**Recommended setup for overnight runs:**
- Set `MAX_EVALUATIONS` to a reasonable limit (e.g., 50–200)
- Use a model with predictable pricing
- Monitor the first few cycles manually before leaving unattended

## Testing

There is a small regression test suite under `tests/`. It is intentionally narrow and focuses on failure-prone plumbing such as:

- Anthropic JSON handling
- cache key isolation across provider settings
- empty-response fallback in topic inference
- redaction of default evaluation artifacts

Run it with:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

## Acknowledgments

This project is directly inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — an AI agent autonomously improves `train.py` overnight, and [miolini/autoresearch-macos](https://github.com/miolini/autoresearch-macos) — the same idea adapted for Apple Silicon. This repo applies the same shape (single mutable target, fixed evaluator, keep/revert cycle) but swaps model training for prompt optimization.

## License

MIT
