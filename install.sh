#!/usr/bin/env bash
# Instalator klawiatury. Uruchamia go plik „Zainstaluj” (dwa kliknięcia).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
REQ="$DIR/requirements.txt"

fail() {
  trap - ERR
  echo
  echo "BŁĄD: $*"
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "Klawiatura" --error "$*" || true
  fi
  if [[ -t 0 ]]; then
    read -r -p "Naciśnij Enter, żeby zamknąć..." _ || true
  fi
  exit 1
}

trap 'fail "Instalacja przerwała się. Jeśli wyżej jest błąd sieci, włącz Wi-Fi i kliknij Zainstaluj jeszcze raz."' ERR

printf '\033]0;Instalacja klawiatury\007'
echo "============================================"
echo "  Instalacja klawiatury na Steam Decku"
echo "  Nie zamykaj tego okna aż do komunikatu"
echo "  „Gotowe”."
echo "============================================"
echo

if [[ "$(uname -s)" != "Linux" ]]; then
  fail "To działa tylko na Steam Decku, w trybie pulpitu."
fi

if command -v kdialog >/dev/null 2>&1; then
  if ! kdialog --title "Klawiatura" --yesno "$(printf '%s\n' \
    "Zainstalować klawiaturę na tym Steam Decku?" \
    "" \
    "Nie zamykaj czarnego okna, aż wyskoczy „Gotowe”." \
    "Jak zapyta o hasło, wpisz je w czarnym oknie." \
    "Litery hasła nie będą widoczne — to normalne.")"; then
    echo "Anulowano."
    exit 0
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  fail "Brak Pythona. Zrób zdjęcie tego okna."
fi

echo "Przygotowuję program (pierwszy raz może potrwać kilka minut)..."

ensure_pip() {
  local py="$1"
  if "$py" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  echo "Pobieram narzędzie do instalacji..."
  local tmp
  tmp="$(mktemp)"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$tmp" || fail "Brak internetu. Włącz Wi-Fi i uruchom instalator jeszcze raz."
  "$py" "$tmp" --user || "$py" "$tmp" || fail "Nie udało się pobrać narzędzi. Sprawdź Wi-Fi."
  rm -f "$tmp"
}

if [[ -x "$VENV/bin/python" ]] && ! "$VENV/bin/python" -c "import sys" >/dev/null 2>&1; then
  rm -rf "$VENV"
fi
if [[ ! -x "$VENV/bin/python" ]]; then
  rm -rf "$VENV"
  if ! python3 -m venv --system-site-packages "$VENV"; then
    python3 -m venv --system-site-packages --without-pip "$VENV" || fail "Nie udało się przygotować Pythona."
  fi
fi

ensure_pip "$VENV/bin/python"
"$VENV/bin/python" -m pip install --upgrade pip
if ! "$VENV/bin/python" -m pip install -r "$REQ"; then
  echo "Pobieranie nie wyszło. Próbuję z systemu SteamOS..."
  sudo steamos-readonly disable || true
  sudo pacman -S --needed --noconfirm python-pyqt6 python-evdev || fail "Nie udało się pobrać składników. Włącz Wi-Fi i spróbuj jeszcze raz."
  sudo steamos-readonly enable || true
fi

PY="$VENV/bin/python"
if ! "$PY" -c "import PyQt6" >/dev/null 2>&1; then
  if python3 -c "import PyQt6" >/dev/null 2>&1; then
    PY="python3"
  else
    fail "Nie udało się zainstalować klawiatury. Włącz Wi-Fi i spróbuj jeszcze raz."
  fi
fi
if ! "$PY" -c "import evdev" >/dev/null 2>&1; then
  fail "Klawiatura jest w połowie zainstalowana, ale brakuje ostatniego składnika. Włącz Wi-Fi i spróbuj jeszcze raz."
fi
printf '%s\n' "$PY" > "$DIR/.python-cmd"

echo
echo "Jeszcze zgoda na wpisywanie klawiszy."
if ! sudo -n true 2>/dev/null; then
  echo "Jak wyskoczy hasło, wpisz hasło do trybu pulpitu."
  echo "Nie zobaczysz liter — to normalne. Na końcu naciśnij Enter."
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
chmod +x "$DIR/run.sh" "$DIR/install.sh" "$DIR/Zainstaluj.desktop" 2>/dev/null || true
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
echo "Gotowe."
DONE="$(printf '%s\n' \
  "Gotowe." \
  "" \
  "Ikona klawiatury jest przy zegarze." \
  "Lewe kliknięcie pokazuje ją i chowa." \
  "" \
  "Jak ikony nie widać, kliknij małą strzałkę przy zegarze i przeciągnij klawiaturę na pasek.")"
if [[ "$NEED_RELOGIN" == 1 ]]; then
  DONE+=$'\n\n'"Wyloguj się z pulpitu i zaloguj jeszcze raz, żeby dało się pisać."
fi
if command -v kdialog >/dev/null 2>&1; then
  kdialog --title "Klawiatura" --msgbox "$DONE" || true
elif [[ -t 0 ]]; then
  echo "$DONE"
  read -r -p "Naciśnij Enter, żeby zamknąć..." _ || true
fi
