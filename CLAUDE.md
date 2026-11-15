# adstudio

Command-line ad editor driven from Claude. Start with `skill/SKILL.md` (rules
and workflow) and `docs/TIMELINE.md` (the edit format).

- This repo is the shared tool. A person's brands, ads, sounds, media and
  `docs/LESSONS.md` live in their workspace (`adstudio where`). Never commit
  brand assets, footage, ads or keys here.
- Python 3, standard library only. Node is used only by `helpers/shoot.mjs`.
- `lib/` modules: util, probe, media (ingest), transcribe, analyze, catalog,
  timeline, overlay, render, page, versions, serve, fcpxml, static, gfx,
  library, refs, setup, cli.
- Secrets live in `~/.config/adstudio/`.
- After changing rendering code, bump `RENDER_VERSION` and render an existing ad.
