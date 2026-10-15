"""Regression tests pinning current engine behavior.

These exist so the schema-externalization refactor can be verified: the
reports produced for every corpus pair must not change. Generated from the
engine's own output (tests/fixtures/baseline.json), so they assert
"behavior is unchanged", not "behavior is correct".
"""
import contextlib
import hashlib
import io
import json
import os
import re

import pytest

from conftee.models.config_compare import ConfigCompare
from conftee.models.extract import Extract
from conftee.models.gen_summary import GenSummary
from conftee.models.outline import Outline
from conftee.utils.read_config import ReadConfig
from conftee.utils import schema as schema_module

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(ROOT, "golden_config_files")
USER_DIR = os.path.join(ROOT, "user_config_files")
SCHEMA_PATH = os.path.join(ROOT, "conftee", "schemas", "cisco-campus.yaml")
BASELINE = os.path.join(ROOT, "tests", "fixtures", "baseline.json")

with open(BASELINE) as _f:
    _baseline = json.load(_f)

PAIR_NAMES = sorted(_baseline)


def run_pair(name):
    """Run one golden/user pair through the full pipeline."""
    golden = ReadConfig.read_config_from_txt(os.path.join(GOLDEN_DIR, name))
    user = ReadConfig.read_config_from_txt(os.path.join(USER_DIR, name))

    # The engine prints progress to stdout; keep test output readable.
    with contextlib.redirect_stdout(io.StringIO()):
        extract_golden, extract_user = Extract._extract_structs(golden, user)
        outline_golden = Outline(golden, extract_golden, True)
        outline_user = Outline(user, extract_user, False)
        schema = schema_module.load(SCHEMA_PATH)
        results = ConfigCompare(
            (extract_golden, extract_user), (outline_golden, outline_user), schema
        ).calculate_diff(infra_prefixes=None)
        return GenSummary(schema).generate_reports(outline_golden, outline_user, results)


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_summary_counts_unchanged(name):
    """Each pair yields the same finding counts as the recorded baseline."""
    summary, _df, _json_report = run_pair(name)
    actual = [[int(row[0]), row[1]] for row in summary]
    assert actual == _baseline[name]["summary"]


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_json_report_unchanged(name):
    """Each pair's JSON report is byte-identical to the recorded baseline."""
    _summary, _df, json_report = run_pair(name)
    digest = hashlib.sha256(
        json.dumps(json_report, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    assert digest == _baseline[name]["report_sha"]


def test_corpus_is_complete():
    """Guard against fixtures silently disappearing."""
    pairs = [
        n
        for n in os.listdir(GOLDEN_DIR)
        if n.endswith(".txt") and os.path.exists(os.path.join(USER_DIR, n))
    ]
    assert len(pairs) == len(PAIR_NAMES)


# Digests of the identifiers that must never appear in the published corpus.
#
# The sample data originally carried a real organization's building codes and a
# real person's name. Both were replaced with neutral equivalents. This guard
# fails if any of them reappear -- for instance by restoring an old file from a
# backup, or pasting in an un-sanitized config.
#
# The identifiers are stored as salted digests rather than plaintext so that
# retiring them from the data does not mean re-publishing them here. A digest
# is enough to detect a match; it does not put the names back in the repo.
# The salt keeps its original value on purpose: changing it would invalidate
# every digest below and require regenerating them from the plaintext names,
# which is exactly what storing digests is meant to avoid. It is an opaque
# constant, so the old project name in it carries no meaning.
_GUARD_SALT = "conf-diff-corpus-guard-v1"
_BANNED_DIGESTS = frozenset(
    {
        "a831621938d9d041", "8d728527f494b7cf", "497cfa070b2d8baf",
        "5ad3055fd6337cff", "1e943e5108e7c749", "217a6eb169c30929",
        "546e92a317dd0d94", "38978528bd3a7b77", "128fa53a46fb9fb6",
        "75fa6bb165ddc9ab", "fb47ca1317c1c486", "2b38139b426f3fac",
    }
)


def _digest(text):
    return hashlib.sha256((_GUARD_SALT + text).encode()).hexdigest()[:16]


def _find_banned(text):
    """Return banned words found in text.

    Each alphabetic run is checked whole, and its 4-character prefix is checked
    too, so that both bare tokens and prefixed forms (a building code followed
    by a device number) are caught. Because matching is word-based rather than
    substring-based, an innocent word that merely contains a banned token as a
    substring does not trip the guard.
    """
    hits = set()
    for word in re.findall(r"[a-z]+", text.lower()):
        if _digest(word) in _BANNED_DIGESTS:
            hits.add(word)
        elif len(word) > 4 and _digest(word[:4]) in _BANNED_DIGESTS:
            hits.add(word[:4] + "*")
    return hits


def test_no_identifying_strings():
    """The published corpus must not carry organization- or person-identifying names."""
    scanned_dirs = (
        GOLDEN_DIR,
        USER_DIR,
        os.path.join(ROOT, "resources"),
        os.path.join(ROOT, "docs"),
    )
    skip_ext = {".jpg", ".png", ".pyc"}

    offenders = []
    for directory in scanned_dirs:
        if not os.path.isdir(directory):
            continue
        for fn in os.listdir(directory):
            path = os.path.join(directory, fn)
            if not os.path.isfile(path) or os.path.splitext(fn)[1].lower() in skip_ext:
                continue
            with open(path, encoding="utf-8", errors="surrogateescape") as f:
                hits = _find_banned(f.read())
            offenders += [f"{fn}: {hit}" for hit in sorted(hits)]
    assert not offenders, f"identifying strings found: {offenders[:10]}"


def test_guard_itself_works():
    """The guard must actually fire -- otherwise it passes vacuously forever.

    The positive sample is recovered by brute-forcing one banned digest over
    short lowercase strings, so this test proves the guard fires without
    restating any identifier in plaintext.
    """
    import itertools
    import string

    sample = None
    for length in (3, 4):
        for combo in itertools.product(string.ascii_lowercase, repeat=length):
            candidate = "".join(combo)
            if _digest(candidate) in _BANNED_DIGESTS:
                sample = candidate
                break
        if sample:
            break

    assert sample is not None, "could not recover a sample from the digest set"
    assert _find_banned(f"hostname {sample}01-fwm"), "guard failed to detect an identifier"
    # And it must stay quiet on innocent text, including words that merely
    # contain a banned token as a substring.
    assert not _find_banned("see the schema work superseding constants.py")
    assert not _find_banned("hostname NOVA22-fwm  name BLDE01-LINK32=NOVA-WLAN31")
