from datetime import datetime

import pytest

from extractor import WebExtractor, decode_cfemail, MIN_LEAD_SCORE

YEAR = datetime.now().year

@pytest.fixture
def ex():
    return WebExtractor()

def page(head="", body=""):
    return f"<html><head>{head}</head><body>{body}</body></html>"

VIEWPORT = '<meta name="viewport" content="width=device-width">'

def test_http_no_viewport_old_footer_is_legacy(ex):
    result = ex.evaluate_strategy(page(body="<p>&copy; 2016 Bob Plumbing</p>"), "http://bob.com")
    assert result["strategy"] == "legacy_redesign"
    assert result["issues"] == ["http", "no_viewport", "old_copyright:2016"]
    assert result["score"] >= MIN_LEAD_SCORE

def test_copyright_uses_newest_year(ex):
    html = page(VIEWPORT, f"<p>Founded &copy; 2012</p><footer>&copy; 2012 - {YEAR}</footer>")
    result = ex.evaluate_strategy(html, "https://a.com")
    assert not any(i.startswith("old_copyright") for i in result["issues"])

def test_copyright_staleness_is_relative_to_today(ex):
    result = ex.evaluate_strategy(page(VIEWPORT, f"<p>&copy; {YEAR - 3}</p>"), "https://a.com")
    assert f"old_copyright:{YEAR - 3}" in result["issues"]
    result = ex.evaluate_strategy(page(VIEWPORT, f"<p>&copy; {YEAR - 1}</p>"), "https://a.com")
    assert not any(i.startswith("old_copyright") for i in result["issues"])

def test_modern_site_with_booking_widget_scores_zero(ex):
    html = page(VIEWPORT, f'<p>&copy; {YEAR}</p><iframe src="https://booking.setmore.com/x"></iframe>')
    result = ex.evaluate_strategy(html, "https://a.com")
    assert result["score"] == 0
    assert result["issues"] == []

def test_manual_form_without_booking(ex):
    html = page(VIEWPORT, f'<p>&copy; {YEAR}</p><form><input type="email"><textarea></textarea></form>')
    assert ex.evaluate_strategy(html, "https://a.com")["issues"] == ["manual_form"]

def test_search_form_is_not_a_contact_form(ex):
    html = page(VIEWPORT, f'<p>&copy; {YEAR}</p><form><input name="q"><input type="submit"></form>')
    assert ex.evaluate_strategy(html, "https://a.com")["issues"] == ["no_booking"]

@pytest.mark.parametrize("raw,expected", [
    ("info@reactphysio.com", "info@reactphysio.com"),
    ("Hello@SmileDental.co.uk.", "hello@smiledental.co.uk"),
    ("%20info@acme.com", "info@acme.com"),
    ("logo@2x.png", None),
    ("core-js@3.2.1", None),
    ("abc123@sentry.wixpress.com", None),
    ("you@example.com", None),
    ("email@acme.com", None),
])
def test_clean_email(ex, raw, expected):
    assert ex._clean_email(raw) == expected

def test_decode_cfemail():
    key = 0x42
    encoded = f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in "info@smile.com")
    assert decode_cfemail(encoded) == "info@smile.com"
    assert decode_cfemail("zz") is None

def test_visible_php_errors_are_the_top_issue(ex):
    html = page(VIEWPORT, f"<br /><b>Notice</b>:  Function _load_textdomain_just_in_time was called incorrectly <p>&copy; {YEAR}</p>")
    result = ex.evaluate_strategy(html, "https://a.com")
    assert result["strategy"] == "legacy_redesign"
    assert result["issues"][0] == "site_errors"
