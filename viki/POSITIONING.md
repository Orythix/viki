# Positioning & Personas

Who VIKI is for, what it is best at, and how personas change that.

## Positioning

VIKI is **the sovereign agent that evolves locally**. It is built for users who want:

- **Privacy**: No data leaves the machine unless you explicitly use research or external APIs.
- **Specificity**: Not a generic chatbot—focused identities (Dev, Research, Home) so the agent is best-in-class for one thing at a time.
- **Evolution**: The Neural Forge and Orythix stack let the agent improve from your usage without cloud training.

## What VIKI is best at

- **Local-first coding**: Dev persona pairs with your codebase, shell, and Forge.
- **Research and recall**: Research persona focuses on search, citation, and recall of past findings.
- **Life and productivity**: Home persona focuses on calendar, email, media, and voice.
- **Full sovereignty**: Sovereign persona keeps all skills; you choose the right tool per request.

## How personas change behavior

Personas are defined in `viki/config/personas/*.yaml`. Each file sets:

- **name**, **tagline**: Identity and one-line positioning (shown in API and CLI).
- **behavior**, **directives**: How the model should act (e.g. “Prioritize code quality” for Dev).
- **skill_allowlist** (optional): When set, only those skills are registered. This makes the agent specific to a vertical (e.g. Dev has no calendar skill).

Set the active persona via `system.persona` in `viki/config/settings.yaml` or the `VIKI_PERSONA` environment variable. The `/api/health` response includes `persona`, `tagline`, and `differentiators` so UIs can display “This is VIKI Dev: the local-first coding partner” and “What makes this agent special: …”.
