# GPT-6 Sol mailbox run

Use Azure OpenAI Responses with `gpt-6-sol`: medium reasoning for name extraction,
audit, and casting; high for the secret search. Set
`BENCHMARK_AZURE_OPENAI_ENDPOINT` and `BENCHMARK_AZURE_OPENAI_API_KEY`.
The paired `FOUNDRY_API_BASE` / `FOUNDRY_API_KEY` variables also work.

```sh
python scripts/parse_corpus.py
python scripts/build_mailbox.py --from sample --engine azure --preset gpt-6-sol --reasoning medium --workers 16
python scripts/clean_background.py --provider azure --models openai/gpt-6-sol --reasoning high --budget 100 --candidate-count 50 --cost-limit 50 --out results/clean_gpt6sol
```

Existing topic labels are reused. Azure responses are checkpointed under
`results/azure_cache`; reruns reuse completed prompts. Incomplete or empty answers
stop the stage. Checkpoints contain name extraction results: keep them private.

Review every residual-name audit finding before publishing. Publish the corpus,
aggregate audit, casting pools, sweep votes and conversations, settings, and
checksums. Never publish the source ID map, pseudonym map, extraction cache, or
raw name-audit rows.

The sweep reads full email bodies and reviews every index page before answering.
The release run allows 50 candidates so the default five cannot discard findings.
Reasoning helper calls receive sufficient output allowance. Inspect 0.3.260 uses a capability override to send GPT-6 reasoning
through Responses; the requested model remains `gpt-6-sol`.

One model supplies no cross-model consensus. The 100 investigation actions
exclude scan pages and helper model calls. No thread is removed without `--apply`. Empty output is not evidence
that no secrets remain.

The September 27 release additionally re-extracted 54 flagged emails at high
effort, merged newly detected aliases, and repeated the medium-effort audit.
The source maps and corrections remain private.

Reported costs use OpenAI Standard token rates; Azure billing can differ.

The published snapshot includes 11 reviewed corrections across 10 emails, followed
by another audit. Their private mapping is retained locally. Fresh model runs can
differ; exact replay requires the saved responses and corrections. The release
manifest states what was checked and which identifying context remains.
