#!/bin/bash
# adstudio installer for Apple Silicon Macs.
#
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/mghenry13/adstudio/main/install.sh)"
#
# Installs whatever is missing (Xcode command line tools, Homebrew, ffmpeg,
# Node, Google Chrome, Claude Code), downloads adstudio to ~/adstudio, runs
# setup, asks for your Gemini key and checks everything. Safe to run again:
# it skips what you already have and updates adstudio.
#
# Options (environment variables):
#   ADSTUDIO_DIR=~/somewhere    where the tool goes (default ~/adstudio)
#   ADSTUDIO_WORKSPACE=~/path   where your brands and ads go (default ~/adstudio-work)
#   ADSTUDIO_SKIP_KEY=1         do not ask for the (optional) Gemini key
#
# Claude can run this for you too: see INSTALL.md. Without a keyboard it never
# waits for input; the two steps that need you (the Xcode pop-up and your Mac
# password for Homebrew) stop the script with a message saying what to do.

set -euo pipefail

REPO="https://github.com/mghenry13/adstudio.git"
DIR="${ADSTUDIO_DIR:-$HOME/adstudio}"
LAUNCHER="$HOME/.config/adstudio/adstudio"

bold=$'\033[1m'; dim=$'\033[2m'; red=$'\033[31m'; green=$'\033[32m'; off=$'\033[0m'
step() { printf '\n%s==> %s%s\n' "$bold" "$1" "$off"; }
note() { printf '    %s\n' "$1"; }
ok()   { printf '    %sok%s %s\n' "$green" "$off" "$1"; }
die()  { printf '\n%sStopped: %s%s\n' "$red" "$1" "$off" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# A person at a keyboard, or Claude running this for them (no keyboard).
if ( : </dev/tty ) 2>/dev/null; then TTY=1; else TTY=; fi

# Reads from the keyboard even when this script arrives through a pipe.
ask() {  # ask <prompt> <var> [hidden]
  local reply=""
  if [ -n "$TTY" ]; then
    if [ "${3:-}" = hidden ]; then
      read -r -s -p "$1" reply </dev/tty || true; echo
    else
      read -r -p "$1" reply </dev/tty || true
    fi
  fi
  printf -v "$2" '%s' "$reply"
}

# ---------------------------------------------------------------- machine
[ "$(uname -s)" = Darwin ] || die "adstudio needs a Mac."
[ "$(uname -m)" = arm64 ] || die "adstudio needs an Apple Silicon Mac (M1 or newer)."
[ "$(id -u)" -ne 0 ] || die "run this as yourself, not with sudo."

printf '%sInstalling adstudio.%s This takes 5 to 15 minutes on a new Mac,\n' "$bold" "$off"
printf 'mostly downloads. You may be asked for your Mac password once (for Homebrew).\n'

# ---------------------------------------------------------------- 1. Xcode CLT
step "Xcode command line tools (git, Swift, Python)"
if xcode-select -p >/dev/null 2>&1; then
  ok "already installed"
else
  xcode-select --install >/dev/null 2>&1 || true
  if [ -z "$TTY" ]; then
    printf '\nNEEDS_YOU: xcode\n'
    die "A window popped up asking to install the command line developer tools. Click Install, agree, wait for it to finish (5 to 10 minutes), then run this again."
  fi
  note "A window popped up. Click Install, agree, and wait for it to finish."
  note "This script carries on by itself when it is done."
  until xcode-select -p >/dev/null 2>&1; do sleep 5; done
  ok "installed"
fi

# ---------------------------------------------------------------- 2. Homebrew
step "Homebrew"
if [ -x /opt/homebrew/bin/brew ]; then
  ok "already installed"
elif [ -z "$TTY" ]; then
  printf '\nNEEDS_YOU: homebrew\n'
  die "Homebrew needs your Mac password, so it has to be installed in Terminal. Open Terminal, paste this line, press Return and type your password when asked:

    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"

Then run this again."
else
  note "Installing Homebrew. It asks for your Mac password (nothing shows as you type)."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty
  [ -x /opt/homebrew/bin/brew ] || die "Homebrew did not install. Run this script again."
  ok "installed"
fi
eval "$(/opt/homebrew/bin/brew shellenv)"
# Make brew available in every new Terminal window, as Homebrew's "Next steps" say.
if ! grep -qs 'brew shellenv' "$HOME/.zprofile"; then
  printf '\neval "$(/opt/homebrew/bin/brew shellenv)"\n' >> "$HOME/.zprofile"
  note "added Homebrew to ~/.zprofile"
fi

# ---------------------------------------------------------------- 3. ffmpeg, Node
step "ffmpeg and Node"
need=()
have ffmpeg || need+=(ffmpeg)
have node || need+=(node)
if [ ${#need[@]} -eq 0 ]; then
  ok "already installed"
else
  note "installing ${need[*]}..."
  brew install "${need[@]}"
  ok "installed"
fi
filters="$(ffmpeg -hide_banner -filters 2>/dev/null || true)"
if [[ "$filters" != *" scale_vt "* ]]; then
  note "your ffmpeg is too old for HDR footage; upgrading..."
  brew upgrade ffmpeg || true
fi

# ---------------------------------------------------------------- 4. Chrome
step "Google Chrome (used to draw text and statics)"
if [ -d "/Applications/Google Chrome.app" ]; then
  ok "already installed"
else
  brew install --cask google-chrome
  ok "installed"
fi

# ---------------------------------------------------------------- 5. Claude Code
step "Claude Code"
export PATH="$HOME/.local/bin:$PATH"
if have claude; then
  ok "already installed"
else
  curl -fsSL https://claude.ai/install.sh | bash
  if ! grep -qs '.local/bin' "$HOME/.zprofile" "$HOME/.zshrc" 2>/dev/null; then
    printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.zprofile"
  fi
  have claude && ok "installed" || note "Claude Code did not install; get it at https://claude.com/claude-code"
fi

# ---------------------------------------------------------------- 6. adstudio
step "adstudio"
if [ -d "$DIR/.git" ]; then
  # Older setups let npm rewrite the lock file; that is not a real local change.
  git -C "$DIR" checkout -- package-lock.json 2>/dev/null || true
  if [ -n "$(git -C "$DIR" status --porcelain --untracked-files=no)" ]; then
    note "you have local changes in $DIR, so it was not updated"
  else
    git -C "$DIR" pull --ff-only --quiet && ok "updated $DIR"
  fi
elif [ -e "$DIR" ]; then
  die "$DIR exists and is not an adstudio download. Move it away, or set ADSTUDIO_DIR."
else
  git clone --quiet "$REPO" "$DIR"
  ok "downloaded to $DIR"
fi
cd "$DIR"
if [ -n "${ADSTUDIO_WORKSPACE:-}" ]; then
  ./adstudio setup "$ADSTUDIO_WORKSPACE"
else
  ./adstudio setup
fi

# ---------------------------------------------------------------- 7. Gemini key
step "Gemini API key (optional: lets adstudio look at your footage and tag every shot)"
keys="$("$LAUNCHER" key 2>/dev/null || true)"
if printf '%s\n' "$keys" | grep -Eq '^ *gemini +not set'; then
  if [ -n "${ADSTUDIO_SKIP_KEY:-}" ] || [ -z "$TTY" ]; then
    note "skipped. adstudio works without it; footage is still transcribed."
    note "Add it any time: $LAUNCHER key gemini"
  else
    note "Without a key adstudio still works: footage is transcribed, but shots"
    note "are not tagged by what is in them. You can add one any time."
    ask "    Set up a free Gemini key now? [y/N] " WANT
    KEY=""
    if [[ "$WANT" == [yY]* ]]; then
      note "Opening Google AI Studio. Sign in, click Create API key, and copy it."
      open "https://aistudio.google.com/apikey" 2>/dev/null || true
      ask "    Paste the key here (hidden) and press Enter: " KEY hidden
    fi
    if [ -n "$KEY" ]; then
      printf '%s' "$KEY" | "$LAUNCHER" key gemini || note "not saved. Try again later: $LAUNCHER key gemini"
    else
      note "skipped. Later: $LAUNCHER key gemini"
    fi
    unset KEY
  fi
else
  ok "already set"
fi

# ---------------------------------------------------------------- check
step "Checking everything"
"$LAUNCHER" doctor || true
note "${dim}MISS is fine for: parakeet model (downloads on first use), HyperFrames CLI, gemini key, runware key${off}"

printf '\n%s%sadstudio is ready.%s\n\n' "$bold" "$green" "$off"
cat <<EOF
Open a new Terminal window and type:  claude

Then say something like:

  Set up my brand kit for mybrand.com. Then ingest the footage in
  ~/Movies/shoot and make a 15 second ad about the spring sale.

To update later, run the same install line again.
EOF
