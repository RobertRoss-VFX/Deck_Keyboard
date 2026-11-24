#!/usr/bin/env bash
# Keyboard installer. Double-click the Install file to run it.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
REQ="$DIR/requirements.txt"

fail() {
  trap - ERR
  echo
  echo "ERROR: $*"
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "Keyboard" --error "$*" || true
  fi
  if [[ -t 0 ]]; then
    read -r -p "Press Enter to close..." _ || true
  fi
  exit 1
}

trap 'fail "Installation stopped. If the error above is about the network, turn on Wi-Fi and run Install again."' ERR

printf '\033]0;Keyboard installation\007'
echo "============================================"
echo "  Installing the keyboard on a Steam Deck"
echo "  Leave this window open until you see"
echo "  Done."
echo "============================================"
echo

if [[ "$(uname -s)" != "Linux" ]]; then
  fail "This only works on a Steam Deck, in desktop mode."
fi

if command -v kdialog >/dev/null 2>&1; then
  if ! kdialog --title "Keyboard" --yesno "$(printf '%s\n' \
    "Install the keyboard on this Steam Deck?" \
    "" \
    "Leave the black window open until you see Done." \
    "If it asks for a password, type it in the black window." \
    "The letters stay hidden. That is normal.")"; then
    echo "Cancelled."
    exit 0
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  fail "Python is missing. Take a photo of this window."
fi

echo "Preparing the program. The first run can take a few minutes..."

ensure_pip() {
  local py="$1"
  if "$py" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  echo "Downloading the install tool..."
  local tmp
  tmp="$(mktemp)"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$tmp" || fail "No internet. Turn on Wi-Fi and run the installer again."
  "$py" "$tmp" --user || "$py" "$tmp" || fail "Could not download the tools. Check Wi-Fi."
  rm -f "$tmp"
}

if [[ -x "$VENV/bin/python" ]] && ! "$VENV/bin/python" -c "import sys" >/dev/null 2>&1; then
  rm -rf "$VENV"
fi
if [[ ! -x "$VENV/bin/python" ]]; then
  rm -rf "$VENV"
  if ! python3 -m venv --system-site-packages "$VENV"; then
    python3 -m venv --system-site-packages --without-pip "$VENV" || fail "Could not prepare Python."
  fi
fi

ensure_pip "$VENV/bin/python"
"$VENV/bin/python" -m pip install --upgrade pip
if ! "$VENV/bin/python" -m pip install -r "$REQ"; then
  echo "Download failed. Trying the SteamOS packages..."
  sudo steamos-readonly disable || true
  sudo pacman -S --needed --noconfirm python-pyqt6 python-evdev || fail "Could not download the pieces. Turn on Wi-Fi and try again."
  sudo steamos-readonly enable || true
fi

PY="$VENV/bin/python"
if ! "$PY" -c "import PyQt6" >/dev/null 2>&1; then
  if python3 -c "import PyQt6" >/dev/null 2>&1; then
    PY="python3"
  else
    fail "Could not install the keyboard. Turn on Wi-Fi and try again."
  fi
fi
if ! "$PY" -c "import evdev" >/dev/null 2>&1; then
  fail "The keyboard is only partly installed. A piece is missing. Turn on Wi-Fi and try again."
fi
printf '%s\n' "$PY" > "$DIR/.python-cmd"

echo
echo "One more step: permission to type keys."
if ! sudo -n true 2>/dev/null; then
  echo "If a password prompt appears, type your desktop password."
  echo "You will not see the letters. That is normal. Press Enter at the end."
fi
if sudo -n true 2>/dev/null; then
  SUDO=(sudo -n)
else
  SUDO=(sudo)
fi

RULE_FILE="/etc/udev/rules.d/99-deck-keyboard-uinput.rules"
MODULE_FILE="/etc/modules-load.d/uinput.conf"
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0666", TAG+="uaccess"' | "${SUDO[@]}" tee "$RULE_FILE" >/dev/null
echo uinput | "${SUDO[@]}" tee "$MODULE_FILE" >/dev/null
"${SUDO[@]}" modprobe uinput || true
"${SUDO[@]}" udevadm control --reload-rules || true
"${SUDO[@]}" udevadm trigger --subsystem-match=misc --action=add || true
if [[ -e /dev/uinput ]]; then
  "${SUDO[@]}" chmod 666 /dev/uinput || true
fi

"$PY" "$DIR/deck_keyboard.py" --install-rules --install-desktop
chmod +x "$DIR/run.sh" "$DIR/install.sh" "$DIR/Install.desktop" 2>/dev/null || true
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${HOME}/.local/share/applications" || true
fi

mkdir -p "${HOME}/.local/state"
NEED_RELOGIN=0
if [[ ! -w /dev/uinput ]]; then
  NEED_RELOGIN=1
fi
if [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" && -w /dev/uinput ]]; then
  nohup "$DIR/run.sh" >>"${HOME}/.local/state/deck-keyboard.log" 2>&1 &
  disown || true
fi

trap - ERR
echo
echo "Done."
DONE="$(printf '%s\n' \
  "Done." \
  "" \
  "The keyboard icon is by the clock." \
  "Left-click shows it and hides it." \
  "" \
  "If you do not see the icon, click the small arrow by the clock and drag the keyboard onto the bar.")"
if [[ "$NEED_RELOGIN" == 1 ]]; then
  DONE+=$'\n\n'"Log out of the desktop and back in before typing will work."
fi
if command -v kdialog >/dev/null 2>&1; then
  kdialog --title "Keyboard" --msgbox "$DONE" || true
elif [[ -t 0 ]]; then
  echo "$DONE"
  read -r -p "Press Enter to close..." _ || true
fi
