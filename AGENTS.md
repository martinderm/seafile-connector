# AGENTS.md

- **Platform-neutral core:** `spec/` and `skills/` must stay free of
  Mistral-specific code and third-party dependencies (Python stdlib only).
  All Mistral-specific integration lives exclusively under `adapters/mistral/`.
- **Never commit credentials.** Scripts read `SEAFILE_API_TOKEN` /
  `MISTRAL_API_KEY` from the environment (or the Mistral Secrets Manager at
  runtime); dry-run output must redact secret values.
- **Tests:** `python3 -m unittest discover -s tests -v` must pass; CI enforces
  it. Tests mock HTTP — no network, no real tokens.
- **Workflow:** work on `vibe/<slug>-dd7e4e` branches, open a draft PR, request
  a Copilot review before merge. Merging is done by the user, not the agent
  sandbox.
- **Docs:** architecture/quickstart in `README.md`; Studio/Work connector
  setup in `adapters/mistral/README.md`; skill usage in
  `skills/seafile-connector/SKILL.md`.
