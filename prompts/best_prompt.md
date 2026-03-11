Write a post about {{TOPIC}} in the voice described in {{STYLE_BRIEF}}. Output only the final post text — no headings, labels, quotes, code blocks, lists, metadata, or any extra commentary.

Match the author's voice: mirror tone, pacing, confidence, sentence rhythm, punctuation habits, and typical compression/expansion. Be natural and conversational; avoid LLM‑style phrasing (e.g., "As an AI," "In summary," "Here's a quick note"). Use active verbs, natural contractions, and varied sentence length.

Content rules
- Deliver one sharp, concrete idea or update. Frame it as an observation or realization, not as advice or a command — avoid imperatives. Prefer specificity but do not invent facts. If details are unknown, state uncertainty or an explicit next step instead of fabricating information.
- No quotes, no lists, no extra formatting.

Anti-copy (strict)
- Use {{STYLE_BRIEF}} only to capture voice. Do not reuse or lightly tweak distinctive phrases, metaphors, signature openings, or long sentence structures from the brief or examples. Avoid repeating unique n‑grams of three or more rare consecutive words from sources. Produce original wording that preserves style without borrowing memorable lines.

Length
- Target ~{{TARGET_LENGTH}} characters (±8%). Only pad if it fits naturally; if you cannot meet the target without padding, be shorter. No filler, no trailing commentary.
