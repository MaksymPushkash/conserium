# Live Retrieval Validation

Live retrieval validation seeds temporary production data through the public API and verifies that scoped retrieval still works after deploy.

It validates:

- per-collection source recall against real chunk embeddings
- synthetic noise rejection
- follow-up query rewrite behavior
- API-level abstention for questions outside the selected collection

Run manually:

```bash
python3 scripts/run_live_eval.py \
  --base-url https://cortexx.me \
  --email "$LIVE_EVAL_EMAIL" \
  --password "$LIVE_EVAL_PASSWORD" \
  --dataset evals/live/seed.json \
  --output artifacts/live-retrieval-eval-report.json
```

The script deletes seeded documents and collections unless `--keep-seed` is passed.

GitHub Actions deploy runs this validation after VPS deploy when these production environment values are configured:

- `PRODUCTION_API_BASE_URL` environment variable
- `LIVE_EVAL_EMAIL` environment secret
- `LIVE_EVAL_PASSWORD` environment secret
- optional `LIVE_EVAL_CREATE_USER=true` environment variable
