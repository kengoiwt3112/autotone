Put your real dataset here as:

- `data/private/raw_posts.jsonl`

One JSON object per line.

Example:

```json
{"platform":"x","text":"I think the eval problem is mostly a product problem now.","topic":"why evals are becoming a product problem"}
{"platform":"slack","text":"Quick update: the retrieval experiment is stable now. Next step is cleaning the labels.","topic":"retrieval experiment update and next step"}
```

Recommended fields:

- `platform`: `x` or `slack`
- `text`: your original post
- `topic`: optional but strongly recommended
