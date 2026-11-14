# cryptomon

Transparent, draggable desktop crypto portfolio monitor (PySide6) for Linux, in
the style of [sysmon-widget](https://github.com/kranmal/sysmon-widget).
Add the coins you hold and watch their live value, 24h change and 7 day trend.

![cryptomon screenshot (demo data)](docs/screenshot.png)

## Features
- Total portfolio value and 24h change in money and percent
- Per coin: amount, price, value, 24h change, 7 day sparkline
- Add any coin CoinGecko lists (search by name or symbol), edit or remove it later
- GBP, USD or EUR; adjustable opacity; optional click-through
- Remembers your coins, currency, opacity and window position

## Requirements
- Linux, Python >= 3.9, a desktop session (X11 or Wayland), internet access
- `PySide6` (installed automatically). No API key needed.

## Install

    git clone https://github.com/kranmal/cryptomon && cd cryptomon
    ./install.sh        # or: pipx install .

## Usage
Run `cryptomon`.

- Left-drag to move
- Right-click, **Add coin…**: search, pick a coin, enter how much you hold
- Double-click a coin to change its amount; right-click it to remove it
- Right-click for currency, refresh interval, opacity, refresh, click-through and quit

Prices refresh every minute by default; pick 30 seconds to 5 minutes under right-click, **Refresh every**. Try it with fake data and no network:
`cryptomon --demo`.

Autostart: copy `data/cryptomon.desktop` to `~/.config/autostart/`.

Uninstall: `pipx uninstall cryptomon` and remove
`~/.local/share/applications/cryptomon.desktop`.

## Privacy
Your holdings are stored only in `~/.config/cryptomon/config.json` (mode 600).
The app sends CoinGecko the coin ids it needs (for example `bitcoin`) and your
chosen currency. It never sends how much you hold. No accounts, no wallet
addresses, no exchange keys.

## Notes
- Data from [CoinGecko](https://www.coingecko.com)'s free public API. It is
  rate limited; if it says "rate limited, retrying" it will try again next minute.
- Prices are indicative, not trading quotes. This is not financial advice.
- Wayland: always-on-bottom depends on the compositor; works best on X11/XWayland.
- Tests: `PYTHONPATH=src python3 -m unittest discover -s tests`

MIT licensed.
