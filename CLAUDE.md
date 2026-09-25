# Rules for working in this repo

- **Paid API calls need an explicit yes, every time.** Before running anything that spends money
  (`scripts/generate.py` or `scripts/build_mailbox.py` with `--engine api`, the default; any script
  with `--engine api`; `build_engine("api", ...)`; `APIEngine`; any use of the OpenRouter, OpenAI,
  Anthropic or Gemini keys in `.env`), stop, state the model, the number of calls and a rough token
  volume, and wait for the user's yes. One yes covers one run: a rerun after a fix, a plots-only pass,
  or a run on a new state file each needs its own. Dry-run with a stub model first; that is free.
- Local GPUs are free: vLLM in `/work6/shuyant/.venv`, Qwen3-32B preset (`--engine vllm --preset
  qwen3-32b`). Use them for bulk work.
- Never hand-edit generated results to hide a problem; keep the problem visible and diagnose it.
- One version of everything: no `v2`, `_new`, `_old` names for prompts or scripts. Replace the file.
