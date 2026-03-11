# CLAUDE.md

## プロジェクト概要

プロンプト最適化のautoresearchループ。
Claude Codeがエージェントとして `prompts/working_prompt.md` を編集し、評価・keep/revertを繰り返してプロンプトを改善する。

## 編集可能ファイル

- `prompts/working_prompt.md` — 唯一の最適化対象

## 編集禁止ファイル

- `prepare.py`, `evaluate.py`, `generate.py` およびそのライブラリ群（`src/autotone/`）
- `prompts/best_prompt.md` — 直接編集しない。working_prompt がベストを超えたときのみ上書きコピー

## 評価コマンド

```bash
uv run python evaluate.py --prompt prompts/working_prompt.md
```

評価結果:
- `artifacts/latest_eval.json` — スコアデータ
- `artifacts/latest_report.md` — 人間向けレポート

## 開始方法

「program.mdを見て実験を始めてください」で開始。
