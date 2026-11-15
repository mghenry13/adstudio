# adstudio

Make video and static ads by talking to Claude Code. Real footage in; draft
previews in seconds; finished MP4s and a Premiere Pro XML out. Every version
is kept on a page where you type feedback and press Redo.

## Install

You need a Mac with Apple Silicon (M1 or newer) and
[Claude Code](https://claude.com/claude-code). Open Terminal and run these
in order. Steps 1 to 3 can be skipped if you already have the tool they install.

**1. Xcode command line tools** (gives you git and Swift; a window pops up, click Install and wait for it to finish)

    xcode-select --install

**2. Homebrew** (the Mac package manager; skip if `brew --version` prints a version)

    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

When it finishes it prints two "Next steps" lines. Run them, then close and reopen Terminal.

**3. ffmpeg and Node**

    brew install ffmpeg node

**4. Google Chrome**, if it is not already in your Applications folder: https://www.google.com/chrome/

**5. adstudio itself**

    git clone <this repo> ~/adstudio
    cd ~/adstudio
    ./adstudio setup

Setup creates your workspace (`~/adstudio-work`, or pass another folder:
`./adstudio setup ~/path/to/folder`), installs the skill for Claude Code and
builds the helpers. It takes about a minute and is safe to run again.

**6. Your Gemini API key.** Create one at https://aistudio.google.com/apikey,
copy it, then run:

    ~/.config/adstudio/adstudio key gemini --paste

The key is saved in `~/.config/adstudio/` on your Mac only. It is never put
in this repo or in a chat.

**7. Check everything**

    ~/.config/adstudio/adstudio doctor

Every line should say `ok`, except these, which are fine to see as `MISS`:
`parakeet model` (downloads itself, about 500 MB, the first time footage is
transcribed), `HyperFrames CLI` (only needed for animations) and `runware key`.

### If something goes wrong

| You see | Do this |
|---|---|
| `command not found: brew` after installing Homebrew | Run the two "Next steps" lines Homebrew printed, then reopen Terminal |
| `MISS ffmpeg` or `MISS node` | `brew install ffmpeg node` |
| `MISS swift` | `xcode-select --install`, wait for it to finish, then `./adstudio setup` again |
| `MISS ffmpeg scale_vt` or `videotoolbox` | `brew upgrade ffmpeg` |
| `MISS Google Chrome` | Install Chrome into Applications |
| `MISS playwright-core` or `parakeet helper` | `cd ~/adstudio && ./adstudio setup` |
| Claude does not know about adstudio | Open a new Claude Code chat; chats opened before setup do not see it |
| The ad page does not load | `~/.config/adstudio/adstudio serve` and leave it running |

To update later: `cd ~/adstudio && git pull && ./adstudio setup`.

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
