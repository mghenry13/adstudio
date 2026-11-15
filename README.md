# adstudio

Make video and static ads by talking to Claude Code. Real footage in; draft
previews in seconds; finished MP4s and a Premiere Pro XML out. Every version
is kept on a page where you type feedback and press Redo.

## What you need

- A Mac with Apple Silicon
- [Claude Code](https://claude.com/claude-code)
- Homebrew tools: `brew install ffmpeg node`
- Xcode command line tools: `xcode-select --install`
- Google Chrome
- A Gemini API key (from Google AI Studio), used to log what is in your footage
- Optional: the HyperFrames app, only if you want animations

## Install

    git clone <this repo> adstudio
    cd adstudio
    ./adstudio setup                  # or: ./adstudio setup ~/path/to/my-workspace
    ~/.config/adstudio/adstudio key gemini --paste    # copy your key first
    ~/.config/adstudio/adstudio doctor

Setup creates your workspace (default `~/adstudio-work`), installs the skill
for Claude Code, and builds the helpers. Your API key is stored in
`~/.config/adstudio/`, never in this repo and never in a chat.

## Your first ad

    ~/.config/adstudio/adstudio brand new "My Brand"

Then open a new Claude Code chat and say what you want:

> Set up my brand kit for mybrand.com. Then ingest the footage in
> ~/Movies/shoot and make a 15 second ad about the spring sale.

Claude follows `skill/SKILL.md`. It shows you a page with the draft; type
feedback there and press Redo for the next version.

## Two folders

| Folder | What is in it | Shared? |
|---|---|---|
| This repo | the tool: code, text styles, docs | yes |
| Your workspace | brand kits, ads, sounds, footage index, your preferences | no, it is yours |

Update the tool with `git pull`. Your workspace is never touched by updates.
Back it up however you like; it is set up to work as its own private git repo
(large derived files are ignored).

## Commands

`adstudio help` lists everything. The ones you will see most:

    ingest <brand> <folder>     register footage, transcribe it
    analyze --all               log what is in each clip
    search <words>              find moments
    preview <brand>/<ad>        fast draft
    snapshot <brand>/<ad>       keep a version (shows on the page)
    render / xml                finals and Premiere Pro XML
    ref add <brand> <file|url>  break down an ad you like

## Notes

- Sound in paid ads needs a licence you can point to. The sound library
  records a source and licence for every file.
- HDR phone footage is converted to standard range on the way in.
- The Premiere XML carries cuts, reframing, text as images, and audio levels.
  It does not carry speed changes or fades.
