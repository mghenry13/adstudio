# adstudio

Make video and static ads by talking to Claude Code. Real footage in; draft
previews in seconds; finished MP4s and a Premiere Pro XML out. Every version
is kept on a page where you leave timecoded comments.

## Install

You need a Mac with Apple Silicon (M1 or newer) and
[Claude Code](https://claude.com/claude-code) (in the Claude desktop app or
in Terminal). Paste this into Claude Code:

    Install Ad Studio for me: https://raw.githubusercontent.com/mghenry13/adstudio/main/INSTALL.md

Claude installs everything that is missing (Xcode command line tools,
Homebrew, ffmpeg, Node, Google Chrome and adstudio itself), checks it, and
tells you when it is ready. On a new Mac it may ask you to click Install in a
pop-up once, and to paste one line into Terminal so Homebrew can ask for your
Mac password. Your password never goes through Claude.

To update later, tell Claude "update adstudio".

### Without Claude: one line in Terminal

Open Terminal (Command+Space, type Terminal, press Return), paste this and
press Return:

    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/mghenry13/adstudio/main/install.sh)"

It does the same steps, and also installs Claude Code if you do not have it.
Running it again is safe and updates adstudio. You can read it first at
[install.sh](install.sh).

### Gemini key (optional)

A free Gemini key lets adstudio look at your footage and tag every shot by
what is in it, and break down reference ads. Without one, footage is still
transcribed and searchable by what is said. To add one any time, copy a key
from https://aistudio.google.com/apikey and run
`~/.config/adstudio/adstudio key gemini --paste` (or ask Claude to run it).
It reads the key from your clipboard, clears it, and saves it on your Mac
only. Never paste a key into a chat.

<details>
<summary>Install by hand instead</summary>

Run these in Terminal in order. Steps 1 to 3 can be skipped if you already
have the tool they install.

1. Xcode command line tools: `xcode-select --install` (click Install and wait)
2. Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`,
   then run the two "Next steps" lines it prints and reopen Terminal
3. `brew install ffmpeg node`
4. Google Chrome in your Applications folder: https://www.google.com/chrome/
5. [Claude Code](https://claude.com/claude-code)
6. adstudio:

       git clone https://github.com/mghenry13/adstudio.git ~/adstudio
       cd ~/adstudio
       ./adstudio setup

   Setup creates your workspace (`~/adstudio-work`, or pass another folder:
   `./adstudio setup ~/path/to/folder`), installs the skill for Claude Code
   and builds the helpers.
7. Optional, your Gemini key (see above)
8. Check: `~/.config/adstudio/adstudio doctor`

</details>

After installing, every line of `~/.config/adstudio/adstudio doctor` should
say `ok`, except these, which are fine to see as `MISS`: `parakeet model`
(downloads itself, about 500 MB, the first time footage is transcribed),
`HyperFrames CLI` (only needed for animations), `gemini key` and
`runware key` (both optional).

### If something goes wrong

| You see | Do this |
|---|---|
| The install line stopped partway | Run it again; it picks up where it left off |
| `command not found: brew` or `claude` | Open a new Terminal window |
| `MISS ffmpeg` or `MISS node` | `brew install ffmpeg node` |
| `MISS swift` | `xcode-select --install`, wait for it to finish, then `./adstudio setup` again |
| `MISS ffmpeg scale_vt` or `videotoolbox` | `brew upgrade ffmpeg` |
| `MISS Google Chrome` | Install Chrome into Applications |
| `MISS playwright-core` or `parakeet helper` | `cd ~/adstudio && ./adstudio setup` |
| Claude does not know about adstudio | Open a new Claude Code chat; chats opened before setup do not see it |
| The ad page does not load | `~/.config/adstudio/adstudio serve` and leave it running |

To update later, tell Claude "update adstudio", or run the install line again.

## Your first ad

    ~/.config/adstudio/adstudio brand new "My Brand"

Then open a new Claude Code chat and say what you want:

> Set up my brand kit for mybrand.com. Then ingest the footage in
> ~/Movies/shoot and make a 15 second ad about the spring sale.

Claude follows `skill/SKILL.md`. It shows you a page with the draft; type
comments there, then say "redo" in the chat for the next version.

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

    watch add <brand> <folder>  remember a footage or assets folder
    sync                        process anything new in watched folders
    search <words>              find moments
    preview <brand>/<ad>        fast draft
    snapshot <brand>/<ad>       keep a version (shows on the page)
    render / xml                finals and Premiere Pro XML
    ref add <brand> <file|url>  break down an ad you like

## Notes

- A free Gemini key allows about 20 analyses a day. For a real footage
  library, turn on billing for the key's project in Google AI Studio. The
  cost is small: cents per ten minutes of footage.

- Sound in paid ads needs a licence you can point to. The sound library
  records a source and licence for every file.
- HDR phone footage is converted to standard range on the way in.
- The Premiere XML carries cuts, reframing, text as images, and audio levels.
  It does not carry speed changes or fades.

## Licence

MIT. See `LICENSE`.
