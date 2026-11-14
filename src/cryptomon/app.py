"""Transparent desktop crypto portfolio monitor.

Left-drag to move. Double-click a coin to edit its amount. Right-click for the
menu (add coin, currency, opacity, click-through, quit).

Prices come from CoinGecko's free public API. Only coin ids are sent; the
amounts you hold never leave this machine (they live in
~/.config/cryptomon/config.json).
"""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QPushButton, QHBoxLayout,
                               QVBoxLayout, QWidget)

API = "https://api.coingecko.com/api/v3"
REFRESH_S = 60
W = 340
HEAD_H, ROW_H, FOOT_H = 78, 50, 30
CURRENCIES = {"gbp": "£", "usd": "$", "eur": "€"}
GREEN, RED, GREY = QColor("#5fe3a1"), QColor("#ff6b6b"), QColor("#8a8f98")


# ---------------------------------------------------------------- config ----
def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "cryptomon" / "config.json"


DEFAULTS = {"currency": "gbp", "opacity": 130, "pos": None, "holdings": []}


def load_config(path=None):
    path = path or config_path()
    cfg = dict(DEFAULTS, holdings=[])
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return cfg
    if not isinstance(raw, dict):
        return cfg
    if raw.get("currency") in CURRENCIES:
        cfg["currency"] = raw["currency"]
    if isinstance(raw.get("opacity"), int) and 0 <= raw["opacity"] <= 255:
        cfg["opacity"] = raw["opacity"]
    pos = raw.get("pos")
    if (isinstance(pos, list) and len(pos) == 2
            and all(isinstance(v, int) for v in pos)):
        cfg["pos"] = pos
    seen = set()
    for h in raw.get("holdings") or []:
        try:
            cid, amt = str(h["id"]), float(h["amount"])
        except (KeyError, TypeError, ValueError):
            continue
        if cid and cid not in seen and amt >= 0 and amt == amt:
            seen.add(cid)
            cfg["holdings"].append({
                "id": cid, "amount": amt,
                "symbol": str(h.get("symbol") or cid)[:12].upper(),
                "name": str(h.get("name") or cid)[:40]})
    return cfg


def save_config(cfg, path=None):
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ------------------------------------------------------------- formatting ----
def fmt_amount(a):
    if a >= 1000:
        return f"{a:,.2f}"
    s = f"{a:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"


def fmt_price(v):
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    if v >= 0.01:
        return f"{v:.4f}"
    return f"{v:.8f}".rstrip("0") or "0"


def fmt_money(v, cur, signed=False):
    sym = CURRENCIES.get(cur, "")
    sign = ("+" if v >= 0 else "-") if signed else ("-" if v < 0 else "")
    return f"{sign}{sym}{abs(v):,.2f}"


def fmt_pct(p):
    return "-" if p is None else f"{p:+.2f}%"


def portfolio(holdings, data):
    """Return (total, change24h_in_money, change24h_pct) over priced holdings."""
    total = prev = 0.0
    for h in holdings:
        d = data.get(h["id"])
        if not d or d.get("price") is None:
            continue
        val = h["amount"] * d["price"]
        total += val
        chg = d.get("change")
        prev += val / (1 + chg / 100) if chg is not None and chg > -100 else val
    delta = total - prev
    return total, delta, (delta / prev * 100 if prev else None)


# -------------------------------------------------------------------- api ----
def http_json(url, timeout=10):
    req = urllib.request.Request(url, headers={
        "User-Agent": "cryptomon/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_markets(ids, cur):
    q = urllib.parse.urlencode({
        "vs_currency": cur, "ids": ",".join(ids), "sparkline": "true",
        "price_change_percentage": "24h", "per_page": 250})
    out = {}
    for c in http_json(f"{API}/coins/markets?{q}"):
        out[c["id"]] = {
            "price": c.get("current_price"),
            "change": c.get("price_change_percentage_24h"),
            "spark": (c.get("sparkline_in_7d") or {}).get("price") or [],
            "symbol": str(c.get("symbol") or "").upper(),
            "name": c.get("name") or c["id"]}
    return out


def search_coins(query):
    res = http_json(f"{API}/search?{urllib.parse.urlencode({'query': query})}")
    return [{"id": c["id"], "name": c["name"], "symbol": c["symbol"].upper(),
             "rank": c.get("market_cap_rank")} for c in res.get("coins", [])[:25]]


def describe_error(e):
    if isinstance(e, urllib.error.HTTPError):
        return "rate limited, retrying" if e.code == 429 else f"API error {e.code}"
    return "offline, retrying"


class Bus(QObject):
    markets = Signal(object, str)   # data, currency it was fetched in
    failed = Signal(str)
    found = Signal(object)
    search_failed = Signal(str)


# ----------------------------------------------------------------- dialogs ----
class AddCoinDialog(QDialog):
    def __init__(self, parent, bus):
        super().__init__(parent)
        self.setWindowTitle("Add coin")
        self.setMinimumWidth(380)
        self.bus, self.coin = bus, None
        self.q = QLineEdit(placeholderText="Search by name or symbol, e.g. bitcoin")
        self.go = QPushButton("Search")
        self.list = QListWidget()
        self.status = QLabel("")
        self.amount = QDoubleSpinBox()
        self.amount.setDecimals(8)
        self.amount.setRange(0, 1e12)
        self.amount.setGroupSeparatorShown(True)
        row = QHBoxLayout()
        row.addWidget(self.q)
        row.addWidget(self.go)
        form = QFormLayout()
        form.addRow("Amount you hold", self.amount)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.list)
        lay.addWidget(self.status)
        lay.addLayout(form)
        lay.addWidget(self.buttons)
        self.go.clicked.connect(self.search)
        self.q.returnPressed.connect(self.search)
        self.list.currentItemChanged.connect(self.pick)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        bus.found.connect(self.show_results)
        bus.search_failed.connect(self.show_error)

    def search(self):
        text = self.q.text().strip()
        if not text:
            return
        self.status.setText("Searching…")
        self.list.clear()

        def run():
            try:
                self.bus.found.emit(search_coins(text))
            except Exception as e:  # noqa: BLE001
                self.bus.search_failed.emit(describe_error(e))
        threading.Thread(target=run, daemon=True).start()

    def show_results(self, coins):
        self.list.clear()
        for c in coins:
            rank = f"  #{c['rank']}" if c["rank"] else ""
            it = QListWidgetItem(f"{c['name']} ({c['symbol']}){rank}")
            it.setData(Qt.UserRole, c)
            self.list.addItem(it)
        self.status.setText("" if coins else "No matches")
        if coins:
            self.list.setCurrentRow(0)

    def show_error(self, msg):
        self.status.setText(f"Search failed: {msg}")

    def pick(self, item):
        self.coin = item.data(Qt.UserRole) if item else None
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self.coin is not None)

    def done(self, r):
        for sig, slot in ((self.bus.found, self.show_results),
                          (self.bus.search_failed, self.show_error)):
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().done(r)


# ------------------------------------------------------------------ widget ----
class Monitor(QWidget):
    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.cfg = load_config() if not demo else demo_config()
        self.data, self.status, self.updated = {}, "loading…", None
        self.bus = Bus()
        self.bus.markets.connect(self.on_markets)
        self.bus.failed.connect(self.on_failed)
        self._inflight = False
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("cryptomon")
        self.resize(W, self.want_height())
        pos = self.cfg.get("pos")
        if pos and not demo and QApplication.platformName() != "wayland":
            self.move(*pos)
        t = QTimer(self)
        t.timeout.connect(self.refresh)
        t.start(REFRESH_S * 1000)
        self.tick = QTimer(self)  # repaint so "updated" text stays fresh
        self.tick.timeout.connect(self.update)
        self.tick.start(15000)
        self.refresh()

    def want_height(self):
        rows = max(len(self.cfg["holdings"]), 1)
        return HEAD_H + rows * ROW_H + FOOT_H

    # ---- data ----
    def refresh(self):
        ids = [h["id"] for h in self.cfg["holdings"]]
        if self.demo:
            self.data, self.updated, self.status = demo_data(), time.time(), "demo data"
            self.update()
            return
        if not ids or self._inflight:
            return
        self._inflight = True
        cur = self.cfg["currency"]

        def run():
            try:
                self.bus.markets.emit(fetch_markets(ids, cur), cur)
            except Exception as e:  # noqa: BLE001
                self.bus.failed.emit(describe_error(e))
        threading.Thread(target=run, daemon=True).start()

    def on_markets(self, data, cur):
        self._inflight = False
        if cur != self.cfg["currency"]:  # currency changed mid-flight
            self.refresh()
            return
        self.data, self.updated, self.status = data, time.time(), ""
        self.update()

    def on_failed(self, msg):
        self._inflight = False
        self.status = msg
        self.update()

    def save(self):
        if not self.demo:
            # Wayland never reports window positions (always 0,0): don't save junk.
            if QApplication.platformName() != "wayland":
                self.cfg["pos"] = [self.x(), self.y()]
            save_config(self.cfg)

    # ---- drawing ----
    def text(self, p, x, y, s, color=QColor("white"), bold=False, size=10,
             align=Qt.AlignLeft, width=0):
        f = QFont("Noto Sans Mono", size)
        f.setBold(bold)
        p.setFont(f)
        r = QRectF(x, y - 14, width or W, 18)
        p.setPen(QColor(0, 0, 0, 200))
        p.drawText(r.translated(1, 1), align | Qt.AlignVCenter, s)
        p.setPen(color)
        p.drawText(r, align | Qt.AlignVCenter, s)

    def spark(self, p, x, y, w, h, data, color):
        if len(data) < 2:
            return
        lo, hi = min(data), max(data)
        span = (hi - lo) or 1.0
        n = len(data)
        path = QPainterPath()
        for i, v in enumerate(data):
            px, py = x + w * i / (n - 1), y + h - h * (v - lo) / span
            path.moveTo(px, py) if i == 0 else path.lineTo(px, py)
        p.setPen(QPen(color, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 12, 18, self.cfg["opacity"]))
        p.drawRoundedRect(QRectF(0, 0, W, self.height()), 14, 14)
        cur, R = self.cfg["currency"], W - 14
        hold = self.cfg["holdings"]

        total, delta, pct = portfolio(hold, self.data)
        self.text(p, 14, 24, "PORTFOLIO", QColor("#9ad1ff"), bold=True, size=9)
        self.text(p, 0, 24, cur.upper(), GREY, size=9, align=Qt.AlignRight, width=R)
        self.text(p, 14, 52, fmt_money(total, cur), bold=True, size=18)
        if pct is not None:
            c = GREEN if delta >= 0 else RED
            self.text(p, 14, 72, f"{fmt_money(delta, cur, True)}  {fmt_pct(pct)}  24h",
                      c, size=10)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.drawLine(14, HEAD_H - 2, W - 14, HEAD_H - 2)

        if not hold:
            self.text(p, 0, HEAD_H + 30, "No coins yet", QColor("#cccccc"),
                      align=Qt.AlignCenter, width=W)
            self.text(p, 0, HEAD_H + 50, "Right-click to add one", GREY, size=9,
                      align=Qt.AlignCenter, width=W)
        for i, h in enumerate(hold):
            y = HEAD_H + i * ROW_H
            d = self.data.get(h["id"])
            self.text(p, 14, y + 20, h["symbol"], bold=True, size=11)
            self.text(p, 14 + 9 * (len(h["symbol"]) + 1), y + 20,
                      fmt_amount(h["amount"]), GREY, size=9, width=130)
            if not d or d.get("price") is None:
                self.text(p, 0, y + 20, "…", GREY, align=Qt.AlignRight, width=R)
                continue
            chg = d.get("change")
            col = GREY if chg is None else GREEN if chg >= 0 else RED
            self.text(p, 14, y + 38, f"{CURRENCIES[cur]}{fmt_price(d['price'])}",
                      QColor("#cfd6e0"), size=9)
            self.text(p, 0, y + 20, fmt_money(h["amount"] * d["price"], cur),
                      bold=True, size=10, align=Qt.AlignRight, width=R)
            self.text(p, 0, y + 38, fmt_pct(chg), col, size=9,
                      align=Qt.AlignRight, width=R)
            sp = d.get("spark") or []
            sc = GREEN if len(sp) > 1 and sp[-1] >= sp[0] else RED
            self.spark(p, 150, y + 8, 80, 28, sp, sc)

        fy = HEAD_H + max(len(hold), 1) * ROW_H + 18
        if self.status:
            self.text(p, 14, fy, self.status, QColor("#ffcf5c"), size=8)
        elif self.updated:
            self.text(p, 14, fy, time.strftime("updated %H:%M", time.localtime(self.updated)),
                      GREY, size=8)
        self.text(p, 0, fy, "data: CoinGecko", GREY, size=8, align=Qt.AlignRight, width=R)
        p.end()

    # ---- interaction ----
    def row_at(self, pos):
        i = int((pos.y() - HEAD_H) // ROW_H)
        return i if 0 <= i < len(self.cfg["holdings"]) else None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.save()

    def mouseDoubleClickEvent(self, e):
        i = self.row_at(e.position())
        if i is not None:
            self.edit(i)

    def contextMenuEvent(self, e):
        m = QMenu(self)
        i = self.row_at(e.pos())
        if i is not None:
            h = self.cfg["holdings"][i]
            m.addAction(f"Edit {h['symbol']} amount…", lambda: self.edit(i))
            m.addAction(f"Remove {h['symbol']}", lambda: self.remove(i))
            m.addSeparator()
        m.addAction("Add coin…", self.add)
        m.addAction("Refresh now", self.refresh)
        m.addSeparator()
        cm = m.addMenu("Currency")
        for c in CURRENCIES:
            a = QAction(c.upper(), cm, checkable=True)
            a.setChecked(c == self.cfg["currency"])
            a.triggered.connect(lambda _=False, c=c: self.set_currency(c))
            cm.addAction(a)
        om = m.addMenu("Opacity")
        for label, a in (("Clear", 0), ("Light", 60), ("Medium", 130), ("Dark", 200)):
            om.addAction(label, lambda a=a: self.set_alpha(a))
        m.addAction("Click-through (restart to undo)", self.enable_click_through)
        m.addAction("Quit", self.quit)
        m.exec(e.globalPos())

    def add(self):
        d = AddCoinDialog(self, self.bus)
        if d.exec() != QDialog.Accepted or not d.coin:
            return
        c, amt = d.coin, d.amount.value()
        for h in self.cfg["holdings"]:
            if h["id"] == c["id"]:
                h["amount"] += amt  # already held: top up
                break
        else:
            self.cfg["holdings"].append({
                "id": c["id"], "symbol": c["symbol"], "name": c["name"], "amount": amt})
        self.changed()

    def edit(self, i):
        h = self.cfg["holdings"][i]
        v, ok = QInputDialog.getDouble(
            self, f"Edit {h['symbol']}", f"Amount of {h['name']} you hold:",
            h["amount"], 0, 1e12, 8)
        if ok:
            h["amount"] = v
            self.changed(refetch=False)

    def remove(self, i):
        h = self.cfg["holdings"][i]
        if QMessageBox.question(self, "Remove coin", f"Remove {h['name']} from the list?"
                                ) == QMessageBox.Yes:
            del self.cfg["holdings"][i]
            self.changed(refetch=False)

    def changed(self, refetch=True):
        self.save()
        self.resize(W, self.want_height())
        self.update()
        if refetch:
            self.refresh()

    def set_currency(self, c):
        self.cfg["currency"], self.data, self.status = c, {}, "loading…"
        self.save()
        self.refresh()

    def set_alpha(self, a):
        self.cfg["opacity"] = a
        self.save()
        self.update()

    def enable_click_through(self):
        self.setWindowFlag(Qt.WindowTransparentForInput, True)
        self.show()

    def quit(self):
        self.save()
        QApplication.quit()


# -------------------------------------------------------------------- demo ----
def demo_config():
    return {"currency": "gbp", "opacity": 130, "pos": None, "holdings": [
        {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "amount": 0.25},
        {"id": "ethereum", "symbol": "ETH", "name": "Ethereum", "amount": 2.4},
        {"id": "solana", "symbol": "SOL", "name": "Solana", "amount": 18.0},
        {"id": "dogecoin", "symbol": "DOGE", "name": "Dogecoin", "amount": 5200.0}]}


def demo_data():
    import math

    def wave(a, b, n=168):
        return [100 + a * math.sin(i / 14) + b * i / n for i in range(n)]
    return {
        "bitcoin": {"price": 50868.0, "change": -2.91, "spark": wave(6, -8)},
        "ethereum": {"price": 1892.45, "change": 1.37, "spark": wave(4, 6)},
        "solana": {"price": 112.3, "change": 4.82, "spark": wave(5, 12)},
        "dogecoin": {"price": 0.0912, "change": -0.64, "spark": wave(3, -3)}}


def shot(w, out):
    """Save a screenshot on a dark backdrop (the widget itself is translucent)."""
    from PySide6.QtGui import QPixmap
    src = w.grab()
    pm = QPixmap(src.size())
    pm.fill(QColor("#1b2330"))
    q = QPainter(pm)
    q.drawPixmap(0, 0, src)
    q.end()
    pm.save(out)


def main():
    demo = "--demo" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName("cryptomon")
    app.setDesktopFileName("cryptomon")
    # The widget is a Tool window; closing a dialog must not quit the app.
    app.setQuitOnLastWindowClosed(False)
    w = Monitor(demo=demo)
    w.show()
    app.aboutToQuit.connect(w.save)
    if "--screenshot" in sys.argv:  # used to make docs/screenshot.png
        out = sys.argv[sys.argv.index("--screenshot") + 1]
        QTimer.singleShot(300, lambda: (shot(w, out), QApplication.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
