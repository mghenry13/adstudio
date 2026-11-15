---
name: adstudio
description: Make and edit video ads and static ads with the adstudio tool (real footage, captions, text overlays, music, SFX, Premiere XML export, version history with feedback). Use whenever the user asks to make, cut, edit, preview, export or revise an ad, reel or static for one of their brands, to ingest or search footage, to break down a reference ad, to set up a brand kit, or to improve adstudio itself.
---

# adstudio

A command-line ad editor driven from chat. Run it as
`~/.config/adstudio/adstudio <command>` (a link that setup creates; it works
from any folder). `adstudio help` lists every command.

Two folders, kept apart on purpose:
- the tool: code, shared by everyone, updated with git
- the workspace: this person's brands, ads, sound library, footage index and
  `docs/LESSONS.md`. Private to them.
`adstudio where` prints both. `adstudio brand list` shows their brands.

Before writing a timeline read `docs/TIMELINE.md` in the tool folder. Before
making creative choices read `docs/LESSONS.md` in the workspace.

If `~/.config/adstudio/adstudio` does not exist, the tool is not set up:
run `./adstudio setup` from the repo, then `adstudio doctor`.

## Rules

1. Use the commands. Never hand-write ffmpeg for something a command does.
   If a command is missing a feature, add it to the tool, then use it.
   Brands, ads and lessons belong in the workspace, never in the tool folder.
2. Speed matters. Draft with `preview` (half size, cached per segment).
   Only run `render` when the user wants finals.
3. One chat edits a given ad at a time.
4. Footage is never modified. Everything derived lives in `media/`.
5. API keys are per user and never in the repo or in chat. If a key is
   missing, tell the user to run `adstudio key gemini --paste` themselves.
6. Check your own work before showing it: pull frames from the preview and
   look at them (ffmpeg select filter, or `adstudio sheet`).
7. Sound in paid ads needs a known licence. `lib add` records it; do not
   add sounds ripped from meme or soundboard sites.
8. Copy on screen follows the user's own writing rules and `docs/LESSONS.md`.

## Brand kits

`adstudio brand new <name>` creates `brands/<name>/` in the workspace with
`brand.json` and `brand.css`. Fill them from what the user gives you (site,
colours, fonts, logo). Font files go in the kit's `fonts/` folder and are
declared with `@font-face` in `brand.css`. Never invent brand colours or
fonts: ask, or read them from the brand's own site.

Brand rules the user states ("never show prices", "always end on the logo")
go in the `rules` list in that brand's `brand.json`, and you follow them for
every ad for that brand. `adstudio brand page <brand>` writes the brand's
web page (rules, colours, fonts, logos, folders, ads, every asset with its
id) at `http://localhost:<port>/brands/<brand>/index.html`; point the user
there when they want to browse assets or look up an id.

## Workflow

1. `adstudio clips <brand>` and `adstudio search <words>` to find moments.
   `adstudio clip <id>` shows a clip's shot log and timed transcript.
   Each brand keeps its own footage and asset folders (in its `brand.json`;
   `adstudio watch list`, `watch add <brand> <folder>`).
   `adstudio sync <brand>` ingests, transcribes and analyzes only what is new
   there. **Run sync only when the user asks for it**: it costs API calls
   and can pull large files down from a cloud drive. `sync --dry-run` shows
   what is new without doing anything. One-off: `adstudio ingest <brand> <folder>`.
   If Gemini reports a daily limit, say so plainly; sync resumes where it stopped.
2. `adstudio new <brand> <ad>` then write `ads/<brand>/<ad>/timeline.json`.
   Cut on word timings from the transcript, not on guesses.
3. `adstudio preview <brand>/<ad>`. It prints timings and the page URL
   `http://localhost:<port>/ads/<brand>/<ad>/preview.html`. The page is served
   by `adstudio serve` (start it in the background if the page does not load).
4. Revise by editing the timeline and running `preview` again. Unchanged
   segments are reused, so small edits return in about a second.
5. On approval: `adstudio render <brand>/<ad> --aspect all` for MP4s and
   `adstudio xml <brand>/<ad>` for Premiere Pro.

## The web pages

`adstudio serve` gives one path through everything: `/` lists the projects
(brands), a project page lists its ads with the latest frame, version count
and waiting comments, and each ad opens its version page. The project page
also links to the brand kit page (rules, colours, fonts, footage with ids).
When you finish something, give the user the ad's page URL.

## Versions and comments

The ad's page is a version history. The user watches there and leaves
comments: some pinned to a timecode, some about the whole video. Comments
are saved the moment they are typed. Nothing on the page starts work; the
user comes to chat and says "redo" (or "apply my comments", or similar).

1. Make sure `adstudio serve` is running (start it in the background if the
   page does not load).
2. When a draft is worth showing: `adstudio snapshot <brand>/<ad> --note "..."`.
3. When the user asks you to apply their comments: `adstudio todo <brand>/<ad>`.
   It lists every comment no version has answered, numbered, each with what
   was on screen at its timecode (segment, clip, source time). Handle EVERY
   one. If a comment asks for options or a discussion, answer it in chat.
4. `adstudio snapshot <brand>/<ad> --done <numbers> --note "..."`, naming only
   the comments the new version really answers. Anything not listed stays
   waiting and shows on the new version. Never use `--done all` without
   having checked each item. Tell the user in chat which comments are left
   and why.
The page offers the new version behind a "Version N is ready" button.
`adstudio history` shows the record, `adstudio restore <ad> <n>` goes back.

## References

`adstudio ref add <brand> <file|url> --note "what I like"` measures the cuts
and writes a breakdown (hook, beats, text style, pacing, sound). Use
`ref show <id>` and model the new timeline on its structure. Never reuse a
reference's footage, music or wording.

## Voiceover

Put voiceover lines in the timeline's `vo` list (`text` and `at`), then run
`adstudio voice <brand>/<ad>` for scratch takes (Fish Audio via Runware, needs
`adstudio key runware`) and caption timings. When the user records the real
VO, set each line's `file` to their take and run `voice` again. See TIMELINE.md.

## Sound

Music and SFX are generated in chat with the Runware connector (MiniMax
Music 2.6 with `settings.instrumental: true`; Mirelo SFX 1.5), then stored
with `adstudio lib add <sfx|music> <url> --name ... --tags ... --license ...
--prompt ...`. Check `adstudio lib list` first and reuse what exists.

## Animations

Rare. `adstudio gfx <brand>/<ad> <name>` scaffolds a HyperFrames project,
and renders it to a transparent MOV once authored. Follow the HyperFrames
skill for authoring. Reference it in the timeline as `{"gfx": "<name>"}`.

## Improving the tool

- The user's taste goes in the workspace's `docs/LESSONS.md` the moment
  they state it. If it is a personal preference, change it in their brand
  kit or timeline; only change the tool's defaults for things everyone
  would want.
- Code changes: keep modules small, stdlib-only Python, run the test ad
  (`adstudio preview <brand>/<ad>` on any existing ad) before finishing, and commit.
- Bump `RENDER_VERSION` in `lib/render.py` when a change affects pixels, so
  cached segments are not reused wrongly.
- `adstudio timings` shows where time goes. Fix slow steps, do not accept them.
