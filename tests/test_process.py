import json

import pytest

from mcp_magento_audit._process import extract_json


def test_extract_json_parses_clean_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_skips_leading_noise():
    noisy = "DEPRECATED: Scanning CSS/JS files is deprecated.\n" + json.dumps({"a": 1})
    assert extract_json(noisy) == {"a": 1}


def test_extract_json_raises_when_no_json_object_present():
    with pytest.raises(json.JSONDecodeError):
        extract_json("nothing but noise, no braces here")
