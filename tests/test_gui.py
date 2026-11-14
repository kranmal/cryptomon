import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtWidgets import QApplication

from cryptomon import app


class Wheel:
    def __init__(self, dy):
        self.dy = dy

    def angleDelta(self):
        return QPoint(0, self.dy)

    def accept(self):
        pass


class Scrolling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QApplication.instance() or QApplication([])

    def widget(self, n, cap=400):
        w = app.Monitor(demo=True)
        w.cfg["holdings"] = [{"id": f"c{i}", "symbol": f"C{i}", "name": "x", "amount": 1.0}
                             for i in range(n)]
        w.max_height = lambda: cap
        w.fit()
        return w

    def test_short_list_is_not_capped_or_scrollable(self):
        w = self.widget(3)
        self.assertEqual(w.height(), app.HEAD_H + 3 * app.ROW_H + app.FOOT_H)
        self.assertEqual(w.max_scroll(), 0)

    def test_long_list_is_capped_and_scrolls_within_bounds(self):
        w = self.widget(20)
        self.assertEqual(w.height(), 400)
        top = w.max_scroll()
        self.assertEqual(top, 20 * app.ROW_H - (400 - app.HEAD_H - app.FOOT_H))
        for _ in range(100):
            w.wheelEvent(Wheel(-120))
        self.assertEqual(w.scroll_pos(), top)
        w.wheelEvent(Wheel(120 * 1000))
        self.assertEqual(w.scroll_pos(), 0)

    def test_hit_testing_follows_scroll_and_ignores_header_footer(self):
        w = self.widget(20)
        w.scroll = 125
        self.assertEqual(w.row_at(QPointF(10, 100)), (100 + 125 - app.HEAD_H) // app.ROW_H)
        self.assertIsNone(w.row_at(QPointF(10, 30)))
        self.assertIsNone(w.row_at(QPointF(10, w.height() - 5)))

    def test_scroll_resets_when_list_shrinks(self):
        w = self.widget(20)
        w.scroll = 10 ** 9
        w.cfg["holdings"] = w.cfg["holdings"][:2]
        w.fit()
        self.assertEqual(w.scroll_pos(), 0)
        self.assertEqual(w.height(), app.HEAD_H + 2 * app.ROW_H + app.FOOT_H)


class Menu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = QApplication.instance() or QApplication([])

    def test_menu_builds_in_demo_and_normal_mode(self):
        for demo in (True, False):
            w = app.Monitor(demo=demo)
            titles = [a.text() for a in w.build_menu(None).actions()]
            self.assertIn("Open at", titles)
            self.assertIn("Refresh every", titles)
            self.assertIn("Quit", titles)

    def test_demo_config_has_every_setting(self):
        self.assertTrue(set(app.DEFAULTS) <= set(app.demo_config()))


if __name__ == "__main__":
    unittest.main()
