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

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv/), an OpenAI-compatible API endpoint (or Ollama for local inference).

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

# 7. (Optional) Generate human-readable report with raw text
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
data/private/raw_posts.jsonl — your writing samples (gitignored)
```

## Design choices

- **Single file to modify.** The agent only touches `prompts/working_prompt.md`. This keeps the scope manageable and diffs reviewable.
- **Fixed time budget.** Each experiment runs for 5 minutes. This means roughly 12 experiments/hour, ~100 experiments overnight. Results are directly comparable regardless of what the agent changes in the prompt.
- **Self-contained.** No external dependencies beyond OpenAI client and dotenv. No fine-tuning, no embeddings, no vector databases. One prompt, one evaluator, one metric.
- **Public-safe by default.** Ships with synthetic sample data only. Your real posts live under `data/private/` (gitignored). `.gitignore` excludes `.env`, generated artifacts, and run logs.

## Model backends

This repo uses the OpenAI Python client against any **OpenAI-compatible** endpoint.

| Backend | `OPENAI_BASE_URL` | Example models |
|---------|-------------------|----------------|
| OpenAI | `https://api.openai.com/v1` | gpt-5-mini, gpt-5 |
| Ollama | `http://localhost:11434/v1` | qwen2.5:14b |

Reasoning models (GPT-5, o-series, etc.) are supported. The LLM client automatically handles `max_completion_tokens` and `temperature` restrictions.

## Data tips

For the first pass, use around **20–60 posts**.

- Only `text` is required — topics and metadata are auto-generated
- Remove URLs if they dominate your corpus
- Remove repost boilerplate
- Keep language consistent if possible

## Safety

**Sandbox mode:** When running the agent autonomously, restrict permissions so that it can only write to `prompts/working_prompt.md` and read `artifacts/`. Disable network access and git push from the agent session.

**API privacy:** All writing samples and generated text are sent to your configured API provider (OpenAI, Ollama, etc.) for generation and judging. If using a cloud API, your data leaves your machine. For maximum privacy, use a local model via Ollama.

**Cost awareness:** Each experiment cycle makes multiple API calls (generation + judging per validation example). With cloud APIs, costs can accumulate during overnight runs. Set `MAX_EXPERIMENTS` in `.env` to cap the total number of evaluations — the evaluator enforces this as a hard stop at the code level, regardless of how it is invoked.

**Recommended setup for overnight runs:**
- Set `MAX_EXPERIMENTS` to a reasonable limit (e.g., 50–200)
- Use a model with predictable pricing
- Monitor the first few cycles manually before leaving unattended

## Acknowledgments

This project is directly inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — an AI agent autonomously improves `train.py` overnight, and [miolini/autoresearch-macos](https://github.com/miolini/autoresearch-macos) — the same idea adapted for Apple Silicon. This repo applies the same shape (single mutable target, fixed evaluator, keep/revert cycle) but swaps model training for prompt optimization.

## License

MIT
