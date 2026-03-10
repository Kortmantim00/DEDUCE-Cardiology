"""Unit tests for core utilities in ``deduce_pipeline``."""

import tempfile
from pathlib import Path

import pytest

from deduce_pipeline import core


def test_preprocess_text():
    assert core.preprocess_text("patientJohn") == "patient John"
    assert core.preprocess_text("drNaamJohannes") == "dr Naam Johannes"
    # nothing to change
    assert core.preprocess_text("already spaced") == "already spaced"


def test_fix_cid_codes():
    text = "foo (cid:431) bar (cid:432)"
    assert core.fix_cid_codes(text) == "foo ff bar ffi"


def test_anonymize_months():
    assert core.anonymize_months("januari") == "[MAAND]"
    assert core.anonymize_months("jan") == "[MAAND]"
    assert core.anonymize_months("In July 2020") == "In July 2020"  # english months unaffected



def test_anonymize_years():
    # explicit date replaced first
    text = "on 01-02-2020 and 1999 and 2001"
    out = core.anonymize_years(text)
    assert "[DATUM]" in out
    assert "[JAAR 0]" in out

    # no years
    assert core.anonymize_years("no years here") == "no years here"


def test_medical_whitelist():
    wl = core.get_medical_terms_whitelist()
    assert "glasgow" in wl
    # filter_medical_terms drops an annotation with text 'glasgow'
    class Dummy:
        def __init__(self, tag, text):
            self.tag = tag
            self.text = text

    anns = [Dummy("score", "glasgow"), Dummy("name", "John")]
    filtered = core.filter_medical_terms(anns)
    assert len(filtered) == 1
    assert filtered[0].text == "John"


def test_deduce_secure_and_logging(tmp_path):
    sd = core.init_deduce_secure(write_log_file=True, log_dir=tmp_path)
    assert sd.deduce is not None
    assert sd.log_file is not None
    # logging handlers close without exception
    core.close_logging_handlers()


if __name__ == "__main__":
    pytest.main([__file__])