# Development notes

## Layout
| Path | What it is |
| --- | --- |
| `src/cryptomon/app.py` | Everything: config, CoinGecko calls, the widget, dialogs, tray |
| `src/cryptomon/icon.svg` | App icon, shipped inside the package and used as the window and tray icon |
| `data/cryptomon.desktop` | Launcher / autostart entry |
| `install.sh` | Installs with pipx, or into a venv, and adds the menu entry and icon |
| `tests/` | `test_logic.py` (formatting, maths, config) and `test_gui.py` (sizing, scrolling) |
| `docs/` | This documentation and its images |

Only dependency: `PySide6`. HTTP uses the standard library.

## Run from a checkout

    PYTHONPATH=src python3 -m cryptomon            # real coins
    PYTHONPATH=src python3 -m cryptomon --demo     # fake coins, no network

## Tests

    PYTHONPATH=src python3 -m unittest discover -s tests

The tests run headless (`QT_QPA_PLATFORM=offscreen` is set for the GUI tests) and
use a temporary config directory, so they never touch `~/.config/cryptomon`.

## Screenshots

    QT_QPA_PLATFORM=offscreen PYTHONPATH=src python3 -m cryptomon --demo --screenshot docs/screenshot.png

The widget is translucent, so the screenshot is composited onto a dark backdrop.

## How it works
- **Prices:** one call to CoinGecko `/coins/markets` per refresh, with
  `sparkline=true`, returns price, 24h change and 7 day history for every coin.
  Search uses `/search`. Network calls run on worker threads and report back
  through Qt signals.
- **Config:** `load_config` validates every field and drops anything invalid;
  `save_config` writes atomically with mode 600.
- **Sizing:** the window has a fixed size recomputed from the number of rows,
  capped at the screen height; rows scroll inside a clipped area.
- **KWin/Wayland quirk:** a resize requested right after a modal dialog closes is
  silently ignored by the compositor, so `fit_later()` defers it by 150 ms and
  verifies afterwards.
- **Placement on Wayland:** clients cannot position windows, so `kwin_place()`
  loads a tiny script into KWin over D-Bus (`org.kde.KWin /Scripting`). Elsewhere
  it falls back to doing nothing (Wayland) or `QWidget.move` (X11).

## Releasing
Bump `version` in `pyproject.toml`, run the tests, regenerate the screenshots if the
look changed, and push. The site page at kranmal.github.io/cryptomon/ links to
the repo's `main` archive, so it needs no change for a normal release.

## License
MIT, see [`LICENSE`](../LICENSE).
