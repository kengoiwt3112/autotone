# autoresearch-tone-macos

An autonomous AI research system for **writing tone optimization**, built on the autoresearch pattern.

## Acknowledgments

This project is directly inspired by:

- [**karpathy/autoresearch**](https://github.com/karpathy/autoresearch) — the original autoresearch: an AI agent autonomously improves `train.py` overnight, training for fixed 5-minute budgets, evaluating via val_bpb, and keeping only improvements. One mutable file, one fixed metric, one keep/revert loop.
- [**miolini/autoresearch-macos**](https://github.com/miolini/autoresearch-macos) — the same idea adapted for Apple Silicon Macs with MPS support.

This repo applies the same **shape** — single mutable target, fixed evaluator, keep/revert cycle, and a human-written `program.md` — but swaps model training for **prompt optimization**. Instead of improving a training loop, the agent improves a prompt file so an LLM can better reproduce your writing tone.

## Core concept

Give an AI agent (Claude Code) a writing style corpus and let it experiment overnight. The agent modifies the prompt, generates text, evaluates against your real writing style, and either keeps or discards each change before repeating the cycle.

## Key files

| File | Role | Modified by |
|------|------|-------------|
| `prepare.py` | One-time data prep (splits data, builds style profile) | Nobody |
| `evaluate.py` | Fixed evaluator (generates text, scores against your style) | Nobody |
| `prompts/working_prompt.md` | **The single file the agent edits** | Agent |
| `program.md` | Research brief + experiment loop instructions | Human |

## Requirements

- Apple Silicon Mac (M1 and later) or any machine with Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- An OpenAI-compatible API endpoint (or Ollama for local inference)

## Getting started

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
cp .env.example .env
```

### Configure a model backend

This repo uses the OpenAI Python client against any **OpenAI-compatible** endpoint.

Example `.env` for OpenAI API:

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

Smoke-test mode (no API needed): `MOCK_LLM=1`

### Add your posts

```text
data/private/raw_posts.jsonl
```

One JSON object per line. Only `text` is required:

```json
{"text":"Small posts go here."}
{"text":"Longer internal message goes here."}
```

`prepare.py` automatically infers topics and other metadata from your text.

### Prepare and run

```bash
uv run python prepare.py
uv run python evaluate.py --prompt prompts/working_prompt.md
```

### Start the optimization loop

Point Claude Code at `program.md`:

```
Have a look at program.md and kick off a new experiment. Start with the setup.
```

The agent then autonomously iterates — editing the prompt, evaluating, keeping improvements — in 5-minute experiment cycles until you stop it. Just like the original autoresearch, but for writing style instead of training loss.

### Generate a new post

```bash
uv run python generate.py --topic "why small evaluation loops beat big rewrites"
```

## Scoring

The evaluator combines:

- LLM judge scores (style similarity, same-author likelihood)
- Local stylometric similarity (punctuation, rhythm, compression)
- Length / structure similarity
- Anti-copy penalty (prevents memorization)

The metric is `overall_score` — higher is better. The goal is not to clone any one post, but to find a prompt that makes the model feel like **the same writer** across unseen topics.

## Public-safe by default

- Ships with **synthetic sample data only**
- Your real posts live under `data/private/` (gitignored)
- `.gitignore` excludes `.env`, generated artifacts, and run logs

Do **not** commit private content or personal exports into a public repository.

## Data tips

For the first pass, use around **20–60 posts**.

- Remove URLs if they dominate your corpus
- Remove repost boilerplate
- Keep language consistent if possible

## Notes

- This is not a perfect authorship system. It is best treated as an **iterative taste loop**.
- The judge model matters a lot. A stronger judge gives better gradients for optimization.
- **Reasoning models** (GPT-5, o-series, etc.) are supported. The LLM client automatically handles `max_completion_tokens` and `temperature` restrictions.
- If your personal corpus is sensitive, keep `data/private/` out of version control.

## License

MIT
