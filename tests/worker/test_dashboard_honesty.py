"""What the dashboard says about itself must be true: event names, counts and numbers that were never read."""

import re
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import ui
from trendvn_worker.ui.labels import EVENT_LABELS

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "services" / "worker" / "src" / "trendvn_worker"


def emitted_event_names():
    """Every event name the worker writes to the log: literals, and the prefixed families with the values their callers pass."""
    names = set()
    families = {
        '"publish_" + outcome': ("published", "failed", "deferred", "unknown", "duplicate"),
        '"operator_" + action': ("approve", "reject", "retry"),
        '"resolved_" + outcome': ("published", "failed"),
    }
    for path in SRC.rglob("*.py"):
        for call in re.finditer(r"\.event\(\s*db,\s*[^,]+,\s*([^,)]+(?:\s+if\s+\w+\s+else\s+\"\w+\")?)", path.read_text()):
            expression = call.group(1).strip()
            if expression in families:
                names.update(prefix + value for prefix, value in [(expression.split('"')[1], v) for v in families[expression]])
            else:
                names.update(re.findall(r'"([a-z_]+)"', expression))
    return names


class EventLabelTests(unittest.TestCase):
    def test_every_event_the_worker_writes_has_a_vietnamese_label(self):
        names = emitted_event_names()
        self.assertGreater(len(names), 15, names)  # (the scan itself works)
        missing = sorted(name for name in names if name not in EVENT_LABELS and name != "baseline")
        self.assertEqual(missing, [], "events shown to the owner as raw English in the log")


class HeadlineEscapingTests(unittest.TestCase):
    """Titles come from other people's pages and captions from Gemini: nothing in them may become markup."""

    def test_markup_quotes_and_long_text_are_escaped_and_cut(self):
        from trendvn_worker.ui.format import headline

        evil = '</script><img src=x onerror=alert(1)> "quote" & <b>bold</b>'
        for row in ({"title": evil}, {"title": "t", "caption_vi": evil}, {"title": evil, "caption_vi": evil + " #tag"}):
            shown = headline(row)
            self.assertNotIn("<img", shown)
            self.assertNotIn("</script>", shown)
            self.assertNotIn("<b>", shown)
        self.assertEqual(headline({"title": "x" * 500}), "x" * 90)
        self.assertNotIn("#tag", headline({"title": "t", "caption_vi": "M\u00f4 t\u1ea3 #tag #khac"}))


class KeyRejectedTests(StoreCase):
    """A key Google refuses stops the queue: the owner must be able to see that on the dashboard (a phone alert is optional and throttled)."""

    def render(self):
        d = self.s.dashboard_data()
        d.update(notify_channels=[], voice_sample=False, ready=self.s.ready_list(), tasks=[])
        return ui.render(d, "CSRFX")

    def test_the_banner_the_attention_tab_and_its_count_all_say_so(self):
        self.s.set_key_rejected(True)
        html = self.render()
        self.assertRegex(
            html,
            'class="banner warn"><b>Ch\u01b0a t\u1ef1 \u0111\u1ed9ng ho\xe0n to\xe0n\\.</b> Kh\xf3a Gemini b\u1ecb Google t\u1eeb ch\u1ed1i',
        )
        self.assertIn("Kh\u00f3a Gemini b\u1ecb Google t\u1eeb ch\u1ed1i", html.split("<h2>C\u1ea7n xem</h2>")[1][:900])
        self.assertRegex(html, "C\u1ea7n xem</small><b>1</b>")
        self.s.key_accepted()
        self.assertNotIn("Kh\u00f3a Gemini b\u1ecb Google t\u1eeb ch\u1ed1i", self.render().split("<h2>C\u1ea7n xem</h2>")[1][:900])


class NewKeyTests(StoreCase):
    def test_saving_a_new_key_clears_the_rejection_of_the_old_one(self):
        from types import SimpleNamespace

        from trendvn_worker.web import forms

        self.s.set_key_rejected(True)
        forms.save_gemini_key(SimpleNamespace(store=self.s), {"key": ["k" * 30]})
        self.assertFalse(self.s.status()["gemini_key_rejected"])


class CountsTests(StoreCase):
    def render(self):
        d = self.s.dashboard_data()
        d.update(notify_channels=[], voice_sample=False, ready=self.s.ready_list(), tasks=[])
        return ui.render(d, "CSRFX")

    def test_a_list_cut_short_says_so_instead_of_a_count_it_does_not_match(self):
        for n in range(45):
            self.job("%032d" % n, "queued", title="video %d" % n)
        html = self.render()
        self.assertIn("\u0110ang ch\u1edd x\u1eed l\u00fd (30 trong 45)", html)
        self.job("%032d" % 99, "candidate", title="m\u1ed9t \u1ee9ng vi\u00ean")
        self.assertIn("\u1ee8ng vi\u00ean ch\u01b0a t\u1ea3i v\u1ec1 (1)", self.render())  # nothing is cut here: the plain number

    def test_the_needs_attention_number_counts_every_held_video_not_just_the_cards_shown(self):
        for n in range(35):
            self.job("%032d" % n, "needs_review", title="v%d" % n, reason="Audio needs review")
        html = self.render()
        self.assertRegex(html, "C\u1ea7n xem</small><b>35</b>")

    def test_the_needs_attention_tab_says_when_it_shows_only_part_of_what_is_held(self):
        for n in range(35):
            self.job("%032d" % n, "needs_review", title="v%d" % n, reason="Audio needs review")
        html = self.render()
        self.assertIn("30 trong 35", html.split("<h2>C\u1ea7n xem</h2>")[1][:600])

    def test_views_that_were_never_read_are_a_dash_not_a_zero(self):
        self.job("p" * 32, "published", title="x", published_at=1.0, publish_url="https://www.tiktok.com/@a/video/1")
        html = self.render()
        self.assertRegex(html, "L\u01b0\u1ee3t xem \\(30 b\xe0i g\u1ea7n nh\u1ea5t\\)</small><b>\u2014</b>")


if __name__ == "__main__":
    unittest.main()
