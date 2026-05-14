from __future__ import annotations

import pytest

from plugins.google_health import client as gh


def test_error_hierarchy():
    assert issubclass(gh.GoogleHealthAuthRequiredError, gh.GoogleHealthError)
    assert issubclass(gh.GoogleHealthAPIError, gh.GoogleHealthError)
    err = gh.GoogleHealthAPIError("boom", status_code=429, response_body="{}")
    assert err.status_code == 429
    assert err.response_body == "{}"
    assert str(err) == "boom"
