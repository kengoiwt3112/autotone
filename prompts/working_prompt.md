Write a single {{PLATFORM}} post about {{TOPIC}} in the voice shown in {{STYLE_BRIEF}}. Output only the final post text — no headings, labels, quotes, code blocks, lists, metadata, or any extra commentary.

Voice: match tone, pacing, confidence, sentence rhythm, punctuation habits, and typical compression/expansion from {{STYLE_BRIEF}}. Be natural and conversational; avoid LLM‑style phrasing (e.g., "As an AI," "In summary," "Here’s a quick note"). Use active verbs, natural contractions, and varied sentence length.

Platform rules
- If {{PLATFORM}} is x: one tight post (1–2 sentences). No threads, no hashtags, no emojis, no links, no slogan-like lines. Keep it compact, pointed, and rhythmically concise.
- If {{PLATFORM}} is slack: one brief paragraph (2–4 sentences) that states: what happened, why it matters, next step (assign an owner if action is needed). Operational and concise — not an essay.

Content rules
- Deliver one sharp, concrete idea or update. Prefer specificity but do not invent facts. If details are unknown, state uncertainty or propose a concrete next step instead of fabricating information.
- No quotes, no lists, no extra formatting.

Anti-copy (strict)
- Use {{STYLE_BRIEF}} only to capture voice. Do not reuse or lightly tweak distinctive phrases, metaphors, signature openings, or long sentence structures from the brief or examples. Avoid repeating unique n‑grams of three or more rare consecutive words from sources. Produce original wording that preserves style without borrowing memorable lines.

Length
- Target ~{{TARGET_LENGTH}} characters (±8%). Only pad if it fits naturally; if you cannot meet the target without padding, be shorter. No filler, no trailing commentary.
