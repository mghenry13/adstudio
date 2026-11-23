# Installing adstudio (instructions for Claude)

A person pasted something like "Install Ad Studio for me" with a link to this
file. Install it for them on this Mac by following these steps. They may not
be technical: do the work yourself, keep your messages short and plain, and
only ask them for the two things below that need a human.

## 1. Check the machine

Run `uname -sm`. It must print `Darwin arm64` (an Apple Silicon Mac, M1 or
newer). If it does not, stop and tell them adstudio only runs on Apple Silicon
Macs.

## 2. Run the installer

    curl -fsSL https://raw.githubusercontent.com/mghenry13/adstudio/main/install.sh -o /tmp/adstudio-install.sh
    ADSTUDIO_SKIP_KEY=1 bash /tmp/adstudio-install.sh

Give the command a long timeout (10 minutes): Homebrew packages and Chrome
are large downloads. It installs only what is missing, so running it again is
always safe. Do not use sudo.

If it stops with a `NEEDS_YOU:` line, the person has to do one thing, then
you run the installer again:

- `NEEDS_YOU: xcode`: a window has popped up on their screen. Ask them to
  click Install, agree, and tell you when it says it is done (5 to 10
  minutes). Then run the installer again.
- `NEEDS_YOU: homebrew`: Homebrew needs their Mac password, which must never
  go through you. Ask them to open the Terminal app (Command+Space, type
  Terminal, Return), paste the line below, press Return, type their Mac
  password when asked (nothing shows as they type), and tell you when it
  finishes:

      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  Then run the installer again.

Any other failure: read the message, fix the cause if you can (for example
`brew upgrade ffmpeg`), and run it again.

## 3. Check it

    ~/.config/adstudio/adstudio doctor

Every line should say `ok`. These are fine as `MISS`: `parakeet model`
(downloads itself the first time footage is transcribed), `HyperFrames CLI`
(only for animations), `gemini key` and `runware key` (both optional).

## 4. Tell them they are done

Say it worked, in a sentence or two, and then:

- To start, they open a new Claude Code chat (this one was started before
  the adstudio skill existed, so it cannot see it) and say something like:
  "Set up my brand kit for mybrand.com, then make a 15 second ad from the
  footage in ~/Movies/shoot."
- Optional: a free Gemini key lets adstudio look at their footage and tag
  every shot, so it can find "the close-up of the coffee pour". Without it,
  footage is still transcribed and searchable by what is said. To add one
  later: copy a key from https://aistudio.google.com/apikey, then ask Claude
  to run `adstudio key gemini --paste` (it reads the key from the clipboard
  and clears it). They should never paste the key into a chat.
- To update later, they can say "update adstudio" and Claude runs the
  installer again.
