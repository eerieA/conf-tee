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
from examples.sample_corpus import SAMPLE_INFRA_PREFIXES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The corpus lives under two roots: a handful of pairs sit in `examples/` as
# user-facing documentation and the rest in `tests/fixtures/corpus/`. Baseline
# keys are bare filenames, so a pair is found by searching the roots rather than
# by joining onto one of them. Names are unique across both roots, which
# `test_corpus_roots_are_disjoint` enforces.
CORPUS_ROOTS = (
    os.path.join(ROOT, "examples"),
    os.path.join(ROOT, "tests", "fixtures", "corpus"),
)
SCHEMA_PATH = os.path.join(ROOT, "conftee", "schemas", "cisco-campus.yaml")
BASELINE = os.path.join(ROOT, "tests", "fixtures", "baseline.json")

with open(BASELINE) as _f:
    _baseline = json.load(_f)

PAIR_NAMES = sorted(_baseline)


def pair_paths(name):
    """Locate one pair's golden and user files across the corpus roots.

    Raises rather than skipping when a pair is missing: a baseline entry whose
    files have vanished is a corpus that lost coverage, which is exactly what
    these tests exist to catch.
    """
    for root in CORPUS_ROOTS:
        golden = os.path.join(root, "golden", name)
        user = os.path.join(root, "user", name)
        if os.path.exists(golden) and os.path.exists(user):
            return golden, user
    raise FileNotFoundError(f"no corpus root holds both halves of {name!r}")


def iter_pair_names():
    """Every name with both halves present, across all roots."""
    for root in CORPUS_ROOTS:
        golden_dir = os.path.join(root, "golden")
        if not os.path.isdir(golden_dir):
            continue
        for name in os.listdir(golden_dir):
            if name.endswith(".txt") and os.path.exists(
                os.path.join(root, "user", name)
            ):
                yield name


def run_pair(name):
    """Run one golden/user pair through the full pipeline."""
    golden_path, user_path = pair_paths(name)
    golden = ReadConfig.read_config_from_txt(golden_path)
    user = ReadConfig.read_config_from_txt(user_path)

    # The engine prints progress to stdout; keep test output readable.
    with contextlib.redirect_stdout(io.StringIO()):
        extract_golden, extract_user = Extract._extract_structs(golden, user)
        outline_golden = Outline(golden, extract_golden, True)
        outline_user = Outline(user, extract_user, False)
        schema = schema_module.load(SCHEMA_PATH)
        results = ConfigCompare(
            (extract_golden, extract_user), (outline_golden, outline_user), schema
        ).calculate_diff(infra_prefixes=SAMPLE_INFRA_PREFIXES)
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
    assert len(list(iter_pair_names())) == len(PAIR_NAMES)


def test_corpus_roots_are_disjoint():
    """No pair name appears under two roots.

    Baseline keys carry no root, so a name present in both would make which
    files a test reads depend on root order rather than on the name.
    """
    names = list(iter_pair_names())
    assert len(names) == len(set(names))


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
    scanned_dirs = CORPUS_ROOTS + (
        os.path.join(ROOT, "docs"),
    )
    skip_ext = {".jpg", ".png", ".pyc"}

    # Walked rather than listed: the corpus sits one level down from its root,
    # in golden/ and user/, so a flat listing would scan neither.
    offenders = []
    for directory in scanned_dirs:
        if not os.path.isdir(directory):
            continue
        for dirpath, _dirnames, filenames in os.walk(directory):
            for fn in filenames:
                path = os.path.join(dirpath, fn)
                if os.path.splitext(fn)[1].lower() in skip_ext:
                    continue
                with open(path, encoding="utf-8", errors="surrogateescape") as f:
                    hits = _find_banned(f.read())
                rel = os.path.relpath(path, ROOT)
                offenders += [f"{rel}: {hit}" for hit in sorted(hits)]
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
