Put your real dataset here as:

- `data/private/raw_posts.jsonl`

One JSON object per line. Only `text` is required.

```json
{"text":"I think the eval problem is mostly a product problem now."}
{"text":"Quick update: the retrieval experiment is stable now. Next step is cleaning the labels."}
```

`prepare.py` will automatically infer topics and other metadata.
