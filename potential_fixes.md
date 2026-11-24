# Potential fixes

## User password during installation

On a fresh Steam Deck the `deck` account often has no password. The installer calls `sudo` so it can allow key typing (`/dev/uinput`), and the system then stops on a password that does not exist.

What you see: installation waits or asks for a password the user never set. They have to open system settings and create one by hand.

Possible fix: before `sudo`, check `passwd -S` (`NP` means no password). If there is no password, show a window that says System Settings → Users → set a password, and do not continue until a password exists.

## The keyboard cannot be moved

Dragging calls `move()` on the window (right button, or the blue background). Steam Deck desktop mode runs Wayland (KWin). KWin ignores that kind of move. A program cannot place its own window on the screen.

The window stays where it first appeared. A left click on a key types a character instead of dragging. The blue margin is thin, so it would still be hard to grab even if `move()` worked.

Possible fix: when the window is grabbed, call `startSystemMove()` so Qt asks KWin to drag it. Add a clear grab bar, not only the thin blue background.
