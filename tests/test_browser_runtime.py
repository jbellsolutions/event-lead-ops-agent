from __future__ import annotations

import pytest

from event_lead_ops.browser_runtime import default_start_url, parse_viewport


def test_browser_start_urls_use_allowlisted_platform_roots():
    assert default_start_url("facebook") == "https://www.facebook.com/marketplace/"
    assert default_start_url("craigslist") == "https://tampa.craigslist.org/"


def test_viewport_parser_requires_positive_dimensions():
    assert parse_viewport("1440x900") == {"width": 1440, "height": 900}
    with pytest.raises(ValueError, match="viewport"):
        parse_viewport("zero")
    with pytest.raises(ValueError, match="positive"):
        parse_viewport("0x900")
