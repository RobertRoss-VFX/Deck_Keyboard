#!/usr/bin/env python3
"""Kompaktowa klawiatura ekranowa dla Steam Deck (tryb pulpitu).

Klawisze idą do jądra przez /dev/uinput, więc trafiają do okna, które już
jest aktywne. Okno klawiatury nie przyjmuje fokusu (flagi Qt + reguła KWin).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path

APP_ID = "deck-keyboard"
WINDOW_TITLE = "Deck Keyboard"
SERVER_NAME = "deck-keyboard"
RULE_MARKER = "deck-keyboard-nofocus"
BLUE = (28, 73, 149)
COLUMNS = 60
WIDTH_PRESETS = (("Mała", 640), ("Kompaktowa", 760), ("Większa", 980))
ALPHA_PRESETS = (("30%", 77), ("50%", 128), ("70%", 179), ("Pełne", 255))

# (etykieta, akcja, szerokość w kolumnach). Suma szerokości w rzędzie = 60.
ROWS: list[list[tuple[str, str, int]]] = [
    [
        ("`", "key:`", 4),
        ("1", "key:1", 4),
        ("2", "key:2", 4),
        ("3", "key:3", 4),
        ("4", "key:4", 4),
        ("5", "key:5", 4),
        ("6", "key:6", 4),
        ("7", "key:7", 4),
        ("8", "key:8", 4),
        ("9", "key:9", 4),
        ("0", "key:0", 4),
        ("-", "key:-", 4),
        ("=", "key:=", 4),
        ("backspace", "key:backspace", 8),
    ],
    [
        ("tab", "key:tab", 6),
        ("q", "key:q", 4),
        ("w", "key:w", 4),
        ("e", "key:e", 4),
        ("r", "key:r", 4),
        ("t", "key:t", 4),
        ("y", "key:y", 4),
        ("u", "key:u", 4),
        ("i", "key:i", 4),
        ("o", "key:o", 4),
        ("p", "key:p", 4),
        ("[", "key:[", 4),
        ("]", "key:]", 4),
        ("\\", "key:\\", 6),
    ],
    [
        ("caps", "caps", 7),
        ("a", "key:a", 4),
        ("s", "key:s", 4),
        ("d", "key:d", 4),
        ("f", "key:f", 4),
        ("g", "key:g", 4),
        ("h", "key:h", 4),
        ("j", "key:j", 4),
        ("k", "key:k", 4),
        ("l", "key:l", 4),
        (";", "key:;", 4),
        ("'", "key:'", 4),
        ("< enter", "key:enter", 9),
    ],
    [
        ("shift", "shift", 9),
        ("z", "key:z", 4),
        ("x", "key:x", 4),
        ("c", "key:c", 4),
        ("v", "key:v", 4),
        ("b", "key:b", 4),
        ("n", "key:n", 4),
        ("m", "key:m", 4),
        (",", "key:,", 4),
        (".", "key:.", 4),
        ("/", "key:/", 4),
        ("shift", "shift", 11),
    ],
    [
        (".com", "text:.com", 9),
        ("@", "text:@", 5),
        ("", "key: ", 46),
    ],
]

KEY_OF = {
    "`": "KEY_GRAVE",
    "1": "KEY_1",
    "2": "KEY_2",
    "3": "KEY_3",
    "4": "KEY_4",
    "5": "KEY_5",
    "6": "KEY_6",
    "7": "KEY_7",
    "8": "KEY_8",
    "9": "KEY_9",
    "0": "KEY_0",
    "-": "KEY_MINUS",
    "=": "KEY_EQUAL",
    "backspace": "KEY_BACKSPACE",
    "tab": "KEY_TAB",
    "q": "KEY_Q",
    "w": "KEY_W",
    "e": "KEY_E",
    "r": "KEY_R",
    "t": "KEY_T",
    "y": "KEY_Y",
    "u": "KEY_U",
    "i": "KEY_I",
    "o": "KEY_O",
    "p": "KEY_P",
    "[": "KEY_LEFTBRACE",
    "]": "KEY_RIGHTBRACE",
    "\\": "KEY_BACKSLASH",
    "a": "KEY_A",
    "s": "KEY_S",
    "d": "KEY_D",
    "f": "KEY_F",
    "g": "KEY_G",
    "h": "KEY_H",
    "j": "KEY_J",
    "k": "KEY_K",
    "l": "KEY_L",
    ";": "KEY_SEMICOLON",
    "'": "KEY_APOSTROPHE",
    "enter": "KEY_ENTER",
    "z": "KEY_Z",
    "x": "KEY_X",
    "c": "KEY_C",
    "v": "KEY_V",
    "b": "KEY_B",
    "n": "KEY_N",
    "m": "KEY_M",
    ",": "KEY_COMMA",
    ".": "KEY_DOT",
    "/": "KEY_SLASH",
    " ": "KEY_SPACE",
}


def log(message: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + message
    print(line, file=sys.stderr)
    try:
        path = Path.home() / ".local" / "state"
        path.mkdir(parents=True, exist_ok=True)
        with (path / "deck-keyboard.log").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def settings_path() -> Path:
    return Path.home() / ".config" / "deck-keyboard.json"


def load_settings() -> dict:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(data: dict) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        log(f"nie zapisano ustawień: {exc}")


def script_path() -> Path:
    return Path(__file__).resolve()


def quote_desktop_arg(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def desktop_text(hidden: bool) -> str:
    command = quote_desktop_arg(sys.executable) + " " + quote_desktop_arg(str(script_path()))
    if hidden:
        command += " --hidden"
    icon = script_path().parent / "icon.svg"
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Klawiatura\n"
        "GenericName=Wirtualna klawiatura\n"
        "Comment=Kompaktowa klawiatura ekranowa, która nie przejmuje aktywnego okna\n"
        f"Exec={command}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "StartupNotify=false\n"
        "X-KDE-StartupNotify=false\n"
        f"StartupWMClass={APP_ID}\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / "deck-keyboard.desktop"


def applications_path() -> Path:
    return Path.home() / ".local" / "share" / "applications" / "deck-keyboard.desktop"


def install_desktop_files() -> None:
    applications_path().parent.mkdir(parents=True, exist_ok=True)
    autostart_path().parent.mkdir(parents=True, exist_ok=True)
    applications_path().write_text(desktop_text(False), encoding="utf-8")
    autostart_path().write_text(desktop_text(True), encoding="utf-8")
    print(f"Skrót: {applications_path()}")
    print(f"Autostart: {autostart_path()}")


def set_autostart(enabled: bool) -> None:
    if enabled:
        autostart_path().parent.mkdir(parents=True, exist_ok=True)
        autostart_path().write_text(desktop_text(True), encoding="utf-8")
    else:
        try:
            autostart_path().unlink()
        except FileNotFoundError:
            pass


def _section_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    """Return (name, start, end) for each [section], end exclusive."""
    starts: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        if len(line) >= 2 and line.startswith("[") and line.endswith("]"):
            starts.append((line[1:-1].strip(), index))
    spans: list[tuple[str, int, int]] = []
    for position, (name, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        spans.append((name, start, end))
    return spans


def merge_kwin_rules(raw: str) -> str | None:
    """Add the no-focus rule. Return None when it is already present."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    if RULE_MARKER in raw:
        return None

    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    spans = _section_spans(lines)
    rule_groups = [name for name, _, _ in spans if name != "General" and not name.startswith("$")]
    general = next((span for span in spans if span[0] == "General"), None)

    new_id = str(uuid.uuid4())
    use_rules_key = True
    if general is None and rule_groups and all(name.isdigit() for name in rule_groups):
        use_rules_key = False
        new_id = str(max(int(name) for name in rule_groups) + 1)
    elif general is not None and not any(
        lines[index].startswith("rules=") for index in range(general[1] + 1, general[2])
    ):
        if rule_groups and all(name.isdigit() for name in rule_groups):
            use_rules_key = False
            new_id = str(max(int(name) for name in rule_groups) + 1)

    if general is None:
        if use_rules_key:
            general_lines = ["[General]", "count=1", f"rules={new_id}", ""]
        else:
            general_lines = ["[General]", f"count={new_id}", ""]
        lines = general_lines + lines
    else:
        _, start, end = general
        body = lines[start + 1 : end]
        rules_value = None
        count_index = None
        rules_index = None
        for offset, line in enumerate(body):
            if line.startswith("count="):
                count_index = offset
            elif line.startswith("rules="):
                rules_index = offset
                rules_value = line.split("=", 1)[1].strip()
        if use_rules_key:
            parts = [part.strip() for part in (rules_value or "").split(",") if part.strip()]
            if not parts:
                parts = list(rule_groups)
            if new_id not in parts:
                parts.append(new_id)
            rules_line = "rules=" + ",".join(parts)
            count_line = f"count={len(parts)}"
            if rules_index is None:
                body.append(rules_line)
            else:
                body[rules_index] = rules_line
            if count_index is None:
                body.append(count_line)
            else:
                body[count_index] = count_line
        else:
            count_line = f"count={new_id}"
            if count_index is None:
                body.append(count_line)
            else:
                body[count_index] = count_line
        lines = lines[: start + 1] + body + lines[end:]

    lines.extend(
        [
            "",
            f"[{new_id}]",
            f"Description=Deck Keyboard [{RULE_MARKER}]",
            "above=true",
            "aboverule=2",
            "acceptfocus=false",
            "acceptfocusrule=2",
            "fsplevel=4",
            "fsplevelrule=2",
            "skiptaskbar=true",
            "skiptaskbarrule=2",
            "skippager=true",
            "skippagerrule=2",
            "skipswitcher=true",
            "skipswitcherrule=2",
            f"title={WINDOW_TITLE}",
            "titlematch=2",
            "types=262143",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def reconfigure_kwin() -> None:
    commands = [
        ["qdbus6", "org.kde.KWin", "/KWin", "reconfigure"],
        ["qdbus", "org.kde.KWin", "/KWin", "reconfigure"],
        [
            "dbus-send",
            "--session",
            "--type=method_call",
            "--dest=org.kde.KWin",
            "/KWin",
            "org.kde.KWin.reconfigure",
        ],
    ]
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
        if result.returncode == 0:
            return


def install_kwin_rule() -> None:
    if sys.platform != "linux":
        print("Reguła KWin jest potrzebna tylko na Linuksie.")
        return
    path = Path.home() / ".config" / "kwinrulesrc"
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    merged = merge_kwin_rules(raw)
    if merged is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name("kwinrulesrc.bak-deck-keyboard")
        if not backup.exists():
            shutil.copy(path, backup)
    path.write_text(merged, encoding="utf-8")
    reconfigure_kwin()
    print(f"Dodano regułę KWin: {path}")


def validate_layout() -> None:
    if len(ROWS) != 5:
        raise AssertionError(f"oczekiwano 5 rzędów, jest {len(ROWS)}")
    for index, row in enumerate(ROWS):
        total = sum(span for _, _, span in row)
        if total != COLUMNS:
            raise AssertionError(f"rząd {index} ma szerokość {total}, nie {COLUMNS}")
        for _label, action, _span in row:
            if action.startswith("key:"):
                token = action[4:]
                if token not in KEY_OF:
                    raise AssertionError(f"brak kodu dla {token!r}")
            elif action.startswith("text:"):
                for character in action[5:]:
                    if character == "@":
                        continue
                    if character.lower() not in KEY_OF and character not in KEY_OF:
                        raise AssertionError(f"brak kodu dla {character!r}")
            elif action not in {"shift", "caps"}:
                raise AssertionError(f"nieznana akcja {action}")


def run_self_tests() -> None:
    validate_layout()

    legacy = "\n".join(
        [
            "[General]",
            "count=1",
            "",
            "[1]",
            "Description=Stara reguła",
            "title=Cos",
            "titlematch=2",
            "",
        ]
    )
    merged = merge_kwin_rules(legacy)
    assert merged is not None
    assert "[2]" in merged
    assert "count=2" in merged
    assert "rules=" not in merged.split("[2]")[0]
    assert RULE_MARKER in merged
    assert merge_kwin_rules(merged) is None

    modern = "\n".join(
        [
            "[$Version]",
            "update_info=kwinrules.upd:example",
            "",
            "[General]",
            "count=1",
            "rules=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "",
            "[aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee]",
            "Description=Firefox",
            "title=Firefox",
            "titlematch=2",
            "",
        ]
    )
    merged = merge_kwin_rules(modern)
    assert merged is not None
    assert "rules=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee," in merged
    assert "Description=Firefox" in merged
    assert "[$Version]" in merged
    assert merged.count(RULE_MARKER) == 1

    empty = merge_kwin_rules("")
    assert empty is not None
    assert "[General]" in empty
    assert "rules=" in empty
    assert RULE_MARKER in empty
    print("self-test ok")


class KeyEmitter:
    """Wstrzykuje zdarzenia klawiatury przez uinput (działa na X11 i Wayland)."""

    def __init__(self) -> None:
        self.ui = None
        self.held: tuple[int, bool] | None = None
        self._e = None
        self.error: str | None = None
        self._open()

    def _open(self) -> None:
        if sys.platform != "linux":
            self.error = "Wpisywanie działa na Steam Decku w trybie pulpitu (Linux)."
            return
        try:
            from evdev import UInput, ecodes as codes
        except ImportError:
            self.error = "Brak biblioteki evdev. W terminalu uruchom ./install.sh"
            return
        self._e = codes
        if not os.path.exists("/dev/uinput"):
            self.error = "Nie ma /dev/uinput. W terminalu uruchom ./install.sh"
            return
        if not os.access("/dev/uinput", os.W_OK):
            self.error = (
                "Brak prawa zapisu do /dev/uinput. "
                "W terminalu uruchom ./install.sh i zaloguj się ponownie do pulpitu."
            )
            return
        names = set(KEY_OF.values())
        names.add("KEY_LEFTSHIFT")
        try:
            keys = [getattr(codes, name) for name in sorted(names)]
            self.ui = UInput({codes.EV_KEY: keys}, name="Deck Keyboard")
        except OSError as exc:
            log(f"uinput: {exc!r}")
            self.error = "Nie udało się włączyć wpisywania. Uruchom ./install.sh"
            self.ui = None

    def press(self, code_name: str, shift: bool = False) -> bool:
        if self.ui is None or self._e is None:
            return False
        self.release()
        codes = self._e
        code = getattr(codes, code_name)
        try:
            if shift:
                self.ui.write(codes.EV_KEY, codes.KEY_LEFTSHIFT, 1)
                self.ui.syn()
            self.ui.write(codes.EV_KEY, code, 1)
            self.ui.syn()
        except OSError as exc:
            log(f"zapis klawisza: {exc!r}")
            self.error = "Wpisywanie przerwało się. Uruchom klawiaturę ponownie."
            self.held = None
            return False
        self.held = (code, shift)
        return True

    def release(self) -> None:
        if self.ui is None or self._e is None or self.held is None:
            self.held = None
            return
        code, shift = self.held
        self.held = None
        codes = self._e
        try:
            self.ui.write(codes.EV_KEY, code, 0)
            if shift:
                self.ui.write(codes.EV_KEY, codes.KEY_LEFTSHIFT, 0)
            self.ui.syn()
        except OSError as exc:
            log(f"puszczenie klawisza: {exc!r}")

    def tap(self, code_name: str, shift: bool = False) -> bool:
        self.release()
        if not self.press(code_name, shift):
            return False
        try:
            time.sleep(0.018)
        finally:
            self.release()
        time.sleep(0.012)
        return True

    def close(self) -> None:
        self.release()
        if self.ui is not None:
            try:
                self.ui.close()
            except OSError:
                pass
            self.ui = None


try:
    from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, QTimer
    from PyQt6.QtGui import (
        QAction,
        QActionGroup,
        QColor,
        QCursor,
        QFont,
        QFontDatabase,
        QFontMetrics,
        QGuiApplication,
        QIcon,
        QPainter,
        QPixmap,
    )
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    from PyQt6.QtWidgets import (
        QApplication,
        QGridLayout,
        QMenu,
        QSizePolicy,
        QSystemTrayIcon,
        QWidget,
    )

    HAS_QT = True
except ImportError:
    HAS_QT = False


if HAS_QT:

    def size_for(width: int) -> tuple[int, int]:
        height = max(190, round(width * 210 / 667))
        return width, height

    def pick_font_family() -> str:
        families = set(QFontDatabase.families())
        for name in ("Noto Sans", "DejaVu Sans", "Liberation Sans", "Helvetica Neue", "Arial"):
            if name in families:
                return name
        return QFont().defaultFamily() or "Sans Serif"

    def draw_icon(size: int, error: bool = False) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(0, 0, 0, 0))
        painter.setBrush(QColor(*BLUE))
        margin = max(1, size // 32)
        radius = max(3, size // 5)
        painter.drawRoundedRect(
            QRectF(margin, margin, size - 2 * margin, size - 2 * margin),
            radius,
            radius,
        )
        painter.setBrush(QColor(255, 255, 255))
        left = size * 0.16
        right = size * 0.84
        gap = size * 0.035
        key_h = size * 0.09
        top = size * 0.24
        for row in range(4):
            y = top + row * (key_h + gap)
            x = left
            widths = (0.16, 0.16, 0.16, 0.16, 0.22) if row < 3 else (0.22, 0.42, 0.22)
            for fraction in widths:
                width = (right - left) * fraction
                painter.drawRoundedRect(QRectF(x, y, width - gap, key_h), size * 0.03, size * 0.03)
                x += width
        if error:
            radius = size * 0.16
            painter.setBrush(QColor(220, 90, 40))
            painter.drawEllipse(QRectF(size - radius * 2.1, size - radius * 2.1, radius * 1.7, radius * 1.7))
        painter.end()
        return pixmap

    def build_icon(error: bool = False) -> QIcon:
        icon = QIcon()
        for size in (16, 22, 32, 64, 128):
            icon.addPixmap(draw_icon(size, error))
        return icon

    class KeyButton(QWidget):
        def __init__(self, label: str, action: str, keyboard: "Keyboard") -> None:
            super().__init__(keyboard)
            self.base_label = label
            self.label = label
            self.action = action
            self.keyboard = keyboard
            self.down = False
            self.active = False
            self.setFocusPolicy(Qt_NoFocus())
            self.setAutoFillBackground(False)
            self.setAttribute(Qt_Translucent(), True)
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self.setCursor(QCursor(Qt_PointingHand()))
            self.setMinimumSize(0, 0)

        def mousePressEvent(self, event) -> None:  # noqa: N802
            if event.button() == Qt_Right():
                self.keyboard.begin_drag(event.globalPosition().toPoint())
                event.accept()
                return
            if event.button() == Qt_Left():
                self.down = True
                self.update()
                self.keyboard.on_press(self)
                event.accept()
                return
            event.ignore()

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self.keyboard.dragging:
                self.keyboard.continue_drag(event.globalPosition().toPoint())
                event.accept()
                return
            event.ignore()

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            if event.button() == Qt_Right():
                self.keyboard.end_drag()
                event.accept()
                return
            if event.button() == Qt_Left():
                self.down = False
                self.update()
                self.keyboard.on_release(self)
                event.accept()
                return
            event.ignore()

        def contextMenuEvent(self, event) -> None:  # noqa: N802
            event.accept()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
            alpha = self.keyboard.key_fill_alpha()
            if self.active:
                fill = QColor(223, 234, 255, alpha)
                text = QColor(*BLUE)
            elif self.down:
                fill = QColor(214, 220, 228, alpha)
                text = QColor(70, 70, 70)
            else:
                fill = QColor(255, 255, 255, alpha)
                text = self.keyboard.key_text_color()
            painter.setPen(QColor(0, 0, 0, 0))
            painter.setBrush(fill)
            radius = max(4.0, min(self.width(), self.height()) * 0.16)
            painter.drawRoundedRect(rect, radius, radius)
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.setPen(QColor(150, 158, 170, 70))
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(text)
            font = fitted_font(self.label, self.keyboard.font_family, self.keyboard.font_px(self.label), rect)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt_AlignCenter(), self.label)
            painter.end()

    def fitted_font(text: str, family: str, pixel_size: int, rect: QRectF) -> QFont:
        font = QFont(family)
        font.setPixelSize(max(8, pixel_size))
        if not text:
            return font
        limit = max(8, int(rect.width()) - 8)
        metrics = QFontMetrics(font)
        while font.pixelSize() > 8 and metrics.horizontalAdvance(text) > limit:
            font.setPixelSize(font.pixelSize() - 1)
            metrics = QFontMetrics(font)
        return font

    class Keyboard(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.settings = load_settings()
            self.emitter = KeyEmitter()
            self.buttons: list[KeyButton] = []
            self.held_button: KeyButton | None = None
            self.repeat_code: str | None = None
            self.repeat_shift = False
            self.repeat_timer = QTimer(self)
            self.repeat_timer.setSingleShot(True)
            self.repeat_timer.timeout.connect(self.repeat_key)
            self.shift_armed = False
            self.caps = False
            self.bg_alpha = int(self.settings.get("bg_alpha", 128))
            self.ghost_keys = bool(self.settings.get("ghost_keys", False))
            self.font_family = pick_font_family()
            self.dragging = False
            self._plate_press = False
            self._drag_origin: QPoint | None = None
            self._drag_top_left: QPoint | None = None
            self._quitting = False
            self._warned = False
            self.tray: QSystemTrayIcon | None = None
            self.menu: QMenu | None = None
            self.toggle_action: QAction | None = None
            self._tray_tries = 0
            self._server: QLocalServer | None = None

            self.setWindowTitle(WINDOW_TITLE)
            self.setWindowFlags(
                Qt_Tool() | Qt_Frameless() | Qt_StaysOnTop() | Qt_NoFocusWindow()
            )
            self.setAttribute(Qt_ShowWithoutActivating(), True)
            self.setAttribute(Qt_X11NoFocus(), True)
            self.setAttribute(Qt_Translucent(), True)
            self.setAttribute(Qt_NoSystemBackground(), True)
            self.setAutoFillBackground(False)
            self.setFocusPolicy(Qt_NoFocus())
            self.setCursor(QCursor(Qt_OpenHand()))

            width = self.clamp_width(int(self.settings.get("width", 760)))
            self.setFixedSize(*size_for(width))

            grid = QGridLayout(self)
            grid.setContentsMargins(10, 10, 10, 10)
            grid.setHorizontalSpacing(4)
            grid.setVerticalSpacing(4)
            for column in range(COLUMNS):
                grid.setColumnStretch(column, 1)
            for row_index, row in enumerate(ROWS):
                grid.setRowStretch(row_index, 1)
                column = 0
                for label, action, span in row:
                    button = KeyButton(label, action, self)
                    grid.addWidget(button, row_index, column, 1, span)
                    self.buttons.append(button)
                    column += span

            self.refresh_labels()

        def key_fill_alpha(self) -> int:
            if self.ghost_keys:
                return max(90, self.bg_alpha)
            return 242

        def key_text_color(self) -> QColor:
            if self.key_fill_alpha() > 220:
                return QColor(176, 176, 176)
            return QColor(55, 58, 64)

        def font_px(self, text: str) -> int:
            base = max(12, int(self.width() * 15 / 760))
            if len(text) <= 1:
                return base
            if len(text) <= 3:
                return max(11, base - 2)
            if len(text) <= 6:
                return max(10, base - 4)
            return max(9, base - 5)

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QColor(0, 0, 0, 0))
            painter.setBrush(QColor(*BLUE, self.bg_alpha))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
            painter.end()

        def event(self, event) -> bool:  # noqa: N802
            if event.type() == QEvent.Type.WindowActivate:
                self.clearFocus()
            return super().event(event)

        def keyPressEvent(self, event) -> None:  # noqa: N802
            event.ignore()

        def stop_repeat(self) -> None:
            self.repeat_timer.stop()
            self.repeat_code = None
            self.held_button = None

        def on_press(self, button: KeyButton) -> None:
            self.stop_repeat()
            action = button.action
            if action == "shift":
                self.shift_armed = not self.shift_armed
                self.refresh_labels()
                return
            if action == "caps":
                self.caps = not self.caps
                self.refresh_labels()
                return
            if action.startswith("text:"):
                self.type_text(action[5:])
                self.consume_shift()
                return
            if action.startswith("key:"):
                token = action[4:]
                shift = len(token) == 1 and token.isalpha() and (self.caps ^ self.shift_armed)
                code = KEY_OF[token]
                if not self.emitter.tap(code, shift):
                    self.warn_input()
                    return
                self.held_button = button
                self.repeat_code = code
                self.repeat_shift = shift
                self.repeat_timer.start(360)

        def repeat_key(self) -> None:
            if self.repeat_code is None:
                return
            if not self.emitter.tap(self.repeat_code, self.repeat_shift):
                self.stop_repeat()
                self.warn_input()
                return
            self.repeat_timer.start(50)

        def on_release(self, button: KeyButton) -> None:
            if button is not self.held_button:
                return
            self.stop_repeat()
            self.emitter.release()
            self.consume_shift()

        def type_text(self, text: str) -> None:
            ok = True
            for character in text:
                if character == "@":
                    ok = self.emitter.tap("KEY_2", shift=True) and ok
                elif character.isalpha():
                    ok = self.emitter.tap(KEY_OF[character.lower()], shift=character.isupper()) and ok
                else:
                    ok = self.emitter.tap(KEY_OF[character], shift=False) and ok
            if not ok:
                self.warn_input()

        def consume_shift(self) -> None:
            if self.shift_armed:
                self.shift_armed = False
                self.refresh_labels()

        def refresh_labels(self) -> None:
            upper = self.caps ^ self.shift_armed
            for button in self.buttons:
                if button.action == "shift":
                    button.active = self.shift_armed
                elif button.action == "caps":
                    button.active = self.caps
                elif button.action.startswith("key:"):
                    token = button.action[4:]
                    if len(token) == 1 and token.isalpha():
                        button.label = token.upper() if upper else token
                    else:
                        button.label = button.base_label
                else:
                    button.label = button.base_label
                button.update()
            self.update()

        def begin_drag(self, global_pos: QPoint) -> None:
            self.dragging = True
            self._drag_origin = global_pos
            self._drag_top_left = self.frameGeometry().topLeft()
            self.setCursor(QCursor(Qt_ClosedHand()))

        def continue_drag(self, global_pos: QPoint) -> None:
            if not self.dragging or self._drag_origin is None or self._drag_top_left is None:
                return
            self.move(self._drag_top_left + (global_pos - self._drag_origin))

        def end_drag(self) -> None:
            if self.dragging:
                self.dragging = False
                self.setCursor(QCursor(Qt_OpenHand()))
                self.remember()

        def mousePressEvent(self, event) -> None:  # noqa: N802
            if event.button() in (Qt_Left(), Qt_Right()):
                self.begin_drag(event.globalPosition().toPoint())
                self._plate_press = event.button() == Qt_Left()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self.dragging:
                if getattr(self, "_plate_press", False):
                    assert self._drag_origin is not None
                    if (event.globalPosition().toPoint() - self._drag_origin).manhattanLength() < 4:
                        event.accept()
                        return
                    self._plate_press = False
                self.continue_drag(event.globalPosition().toPoint())
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            self._plate_press = False
            self.end_drag()
            event.accept()

        def contextMenuEvent(self, event) -> None:  # noqa: N802
            event.accept()

        def remember(self) -> None:
            data = load_settings()
            data.update(
                {
                    "x": self.x(),
                    "y": self.y(),
                    "width": self.width(),
                    "bg_alpha": self.bg_alpha,
                    "ghost_keys": self.ghost_keys,
                }
            )
            save_settings(data)
            self.settings = data

        def apply_alpha(self, alpha: int) -> None:
            self.bg_alpha = alpha
            self.update()
            for button in self.buttons:
                button.update()
            self.remember()

        def apply_ghost(self, enabled: bool) -> None:
            self.ghost_keys = enabled
            for button in self.buttons:
                button.update()
            self.remember()

        def apply_width(self, width: int) -> None:
            width = self.clamp_width(width)
            geometry = self.frameGeometry()
            center_x = geometry.center().x()
            bottom = geometry.bottom()
            wide, high = size_for(width)
            self.setFixedSize(wide, high)
            self.move(center_x - wide // 2, bottom - high + 1)
            self.ensure_on_screen()
            self.remember()

        def clamp_width(self, width: int) -> int:
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is not None:
                width = min(width, int(screen.availableGeometry().width() * 0.94))
            return max(520, width)

        def ensure_on_screen(self) -> None:
            rect = QRect(self.x(), self.y(), self.width(), self.height())
            for screen in QGuiApplication.screens():
                area = screen.availableGeometry().intersected(rect)
                if area.width() > 80 and area.height() > 50:
                    return
            self.place_default()

        def place_default(self) -> None:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            if screen is None:
                return
            area = screen.availableGeometry()
            x = area.x() + (area.width() - self.width()) // 2
            y = area.y() + area.height() - self.height() - 16
            self.move(x, y)

        def restore_place(self) -> None:
            if "x" in self.settings and "y" in self.settings:
                self.move(int(self.settings["x"]), int(self.settings["y"]))
                self.ensure_on_screen()
            else:
                self.place_default()

        def show_keyboard(self) -> None:
            self.restore_place()
            self.show()
            self.raise_()
            self.clearFocus()

        def hide_keyboard(self) -> None:
            self.release_keys()
            self.hide()

        def toggle(self) -> None:
            if self.isVisible():
                self.hide_keyboard()
            else:
                self.show_keyboard()
            self.sync_menu()

        def release_keys(self) -> None:
            self.stop_repeat()
            self.emitter.release()
            if self.shift_armed:
                self.shift_armed = False
                self.refresh_labels()

        def warn_input(self) -> None:
            if not self.emitter.error or self._warned:
                return
            self._warned = True
            log(self.emitter.error)
            if self.tray is not None:
                self.tray.showMessage("Klawiatura", self.emitter.error, QSystemTrayIcon.MessageIcon.Warning, 8000)
                self.tray.setIcon(build_icon(error=True))
                self.tray.setToolTip("Klawiatura — " + self.emitter.error)

        def setup_tray(self) -> None:
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.create_tray()
                return
            self._tray_tries += 1
            if self._tray_tries < 30:
                QTimer.singleShot(1000, self.setup_tray)
            else:
                log("brak zasobnika systemowego, zostawiam okno otwarte")
                self.show_keyboard()

        def create_tray(self) -> None:
            tray = QSystemTrayIcon(build_icon(bool(self.emitter.error)), self)
            tray.setToolTip(
                "Klawiatura\n"
                "Kliknij ikonę, żeby pokazać albo schować.\n"
                "Przeciąganie: prawy przycisk albo niebieskie tło."
            )
            menu = QMenu()
            self.toggle_action = QAction("Pokaż", menu)
            self.toggle_action.triggered.connect(self.toggle)
            menu.addAction(self.toggle_action)
            menu.addSeparator()

            alpha_menu = menu.addMenu("Przezroczystość tła")
            alpha_group = QActionGroup(alpha_menu)
            alpha_group.setExclusive(True)
            for label, alpha in ALPHA_PRESETS:
                action = QAction(label, alpha_menu)
                action.setCheckable(True)
                action.setChecked(alpha == self.bg_alpha)
                action.triggered.connect(lambda _checked=False, value=alpha: self.apply_alpha(value))
                alpha_group.addAction(action)
                alpha_menu.addAction(action)

            ghost = QAction("Klawisze też półprzezroczyste", menu)
            ghost.setCheckable(True)
            ghost.setChecked(self.ghost_keys)
            ghost.toggled.connect(self.apply_ghost)
            menu.addAction(ghost)
            menu.addSeparator()

            size_menu = menu.addMenu("Rozmiar")
            size_group = QActionGroup(size_menu)
            size_group.setExclusive(True)
            for label, width in WIDTH_PRESETS:
                action = QAction(label, size_menu)
                action.setCheckable(True)
                action.setChecked(abs(self.width() - width) < 30)
                action.triggered.connect(lambda _checked=False, value=width: self.apply_width(value))
                size_group.addAction(action)
                size_menu.addAction(action)
            menu.addSeparator()

            autostart = QAction("Uruchamiaj przy logowaniu", menu)
            autostart.setCheckable(True)
            autostart.setChecked(autostart_path().exists())
            autostart.toggled.connect(set_autostart)
            menu.addAction(autostart)
            menu.addSeparator()

            quit_action = QAction("Zamknij", menu)
            quit_action.triggered.connect(self.quit)
            menu.addAction(quit_action)
            menu.aboutToShow.connect(self.sync_menu)

            tray.setContextMenu(menu)
            tray.activated.connect(self.on_tray)
            tray.show()
            self.tray = tray
            self.menu = menu
            if self.emitter.error and sys.platform == "linux":
                QTimer.singleShot(600, self.warn_input)

        def on_tray(self, reason) -> None:
            if reason in (
                QSystemTrayIcon.ActivationReason.Trigger,
                QSystemTrayIcon.ActivationReason.DoubleClick,
                QSystemTrayIcon.ActivationReason.MiddleClick,
            ):
                self.toggle()

        def sync_menu(self) -> None:
            if self.toggle_action is not None:
                self.toggle_action.setText("Schowaj" if self.isVisible() else "Pokaż")

        def listen_for_peers(self, show: bool) -> bool:
            socket = QLocalSocket()
            socket.connectToServer(SERVER_NAME)
            if socket.waitForConnected(200):
                if show:
                    socket.write(b"show")
                    socket.flush()
                    socket.waitForBytesWritten(200)
                return False
            QLocalServer.removeServer(SERVER_NAME)
            server = QLocalServer(self)
            if not server.listen(SERVER_NAME):
                log(f"nie udało się zająć gniazda: {server.errorString()}")
            else:
                server.newConnection.connect(self.on_peer)
            self._server = server
            return True

        def on_peer(self) -> None:
            if self._server is None:
                return
            connection = self._server.nextPendingConnection()
            if connection is None:
                return

            def read() -> None:
                data = bytes(connection.readAll())
                if b"show" in data:
                    self.show_keyboard()
                    self.sync_menu()
                connection.disconnectFromServer()

            connection.readyRead.connect(read)
            if connection.bytesAvailable():
                read()

        def quit(self) -> None:
            self._quitting = True
            self.release_keys()
            self.emitter.close()
            self.remember()
            QApplication.quit()

        def closeEvent(self, event) -> None:  # noqa: N802
            self.release_keys()
            if self._quitting or self.tray is None:
                self.emitter.close()
                event.accept()
                return
            event.ignore()
            self.hide()

        def hideEvent(self, event) -> None:  # noqa: N802
            self.release_keys()
            super().hideEvent(event)
            self.sync_menu()


def Qt_NoFocus():
    from PyQt6.QtCore import Qt

    return Qt.FocusPolicy.NoFocus


def Qt_Translucent():
    from PyQt6.QtCore import Qt

    return Qt.WidgetAttribute.WA_TranslucentBackground


def Qt_NoSystemBackground():
    from PyQt6.QtCore import Qt

    return Qt.WidgetAttribute.WA_NoSystemBackground


def Qt_ShowWithoutActivating():
    from PyQt6.QtCore import Qt

    return Qt.WidgetAttribute.WA_ShowWithoutActivating


def Qt_X11NoFocus():
    from PyQt6.QtCore import Qt

    return Qt.WidgetAttribute.WA_X11DoNotAcceptFocus


def Qt_Tool():
    from PyQt6.QtCore import Qt

    return Qt.WindowType.Tool


def Qt_Frameless():
    from PyQt6.QtCore import Qt

    return Qt.WindowType.FramelessWindowHint


def Qt_StaysOnTop():
    from PyQt6.QtCore import Qt

    return Qt.WindowType.WindowStaysOnTopHint


def Qt_NoFocusWindow():
    from PyQt6.QtCore import Qt

    return Qt.WindowType.WindowDoesNotAcceptFocus


def Qt_Left():
    from PyQt6.QtCore import Qt

    return Qt.MouseButton.LeftButton


def Qt_Right():
    from PyQt6.QtCore import Qt

    return Qt.MouseButton.RightButton


def Qt_OpenHand():
    from PyQt6.QtCore import Qt

    return Qt.CursorShape.OpenHandCursor


def Qt_ClosedHand():
    from PyQt6.QtCore import Qt

    return Qt.CursorShape.ClosedHandCursor


def Qt_PointingHand():
    from PyQt6.QtCore import Qt

    return Qt.CursorShape.PointingHandCursor


def Qt_AlignCenter():
    from PyQt6.QtCore import Qt

    return Qt.AlignmentFlag.AlignCenter


def run_gui(argv: list[str]) -> int:
    render_path = None
    if "--render" in argv:
        index = argv.index("--render")
        if index + 1 >= len(argv):
            print("Użycie: deck_keyboard.py --render plik.png", file=sys.stderr)
            return 2
        render_path = argv[index + 1]
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    if sys.platform == "linux" and render_path is None:
        try:
            install_kwin_rule()
        except Exception as exc:  # noqa: BLE001
            log(f"reguła KWin: {exc}")

    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("Klawiatura")
    app.setOrganizationName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    try:
        app.setDesktopFileName(APP_ID)
    except Exception:
        pass

    window = Keyboard()
    if render_path is not None:
        window.show()
        app.processEvents()
        window.repaint()
        app.processEvents()
        window.grab().save(render_path)
        window.emitter.close()
        return 0

    hidden = "--hidden" in argv
    if not window.listen_for_peers(show=not hidden):
        return 0

    def wake(_signum, _frame) -> None:
        app.quit()

    signal.signal(signal.SIGINT, wake)
    signal.signal(signal.SIGTERM, wake)
    ticker = QTimer()
    ticker.start(400)
    ticker.timeout.connect(lambda: None)

    window.setup_tray()
    if not hidden:
        window.show_keyboard()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        run_self_tests()
        return 0
    if "--install-rules" in argv or "--install-desktop" in argv:
        if "--install-rules" in argv:
            install_kwin_rule()
        if "--install-desktop" in argv:
            install_desktop_files()
        return 0
    if not HAS_QT:
        print("Brak PyQt6. Na Steam Decku, w trybie pulpitu, uruchom ./install.sh", file=sys.stderr)
        return 1
    return run_gui(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log(traceback.format_exc())
        raise
