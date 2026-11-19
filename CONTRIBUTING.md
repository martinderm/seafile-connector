# Contributing

- Branch: `vibe/<short-slug>-dd7e4e` from `main`; open a **draft PR** and
  request a Copilot (coding-agent) review before merge. Fix findings or
  dismiss them with a reason. The user merges — merging from an agent sandbox
  is not allowed.
- Keep the core platform-neutral: no Mistral-specific code and no third-party
  dependencies outside `adapters/mistral/`; skill scripts stay stdlib-only
  and self-contained.
- Never commit tokens, keys, or `.env` files. Tests must not hit the network
  or real credentials.
- Run `python3 -m unittest discover -s tests -v` before pushing (CI enforces).
- Update docs alongside code: `README.md`, `adapters/mistral/README.md`,
  `skills/seafile-connector/SKILL.md`.
