"""Run a vocabulary the engine was never built for, end to end.

Everything else in this suite exercises `cisco-campus.yaml`. That schema was
transcribed from the engine's own former constants, so it agrees with the
engine by construction, and a check that silently assumed a Cisco-shaped
variable name would still pass against it. The whole point of the schema work
is that someone else's vocabulary works too, and nothing tested that.

So the schema here shares no variable name, type name, pool, or regex with the
bundled one. It describes an nginx-flavoured config: ports, hostnames,
filesystem paths, upstream addresses. If any check were still keying off Cisco
naming (a `"netmask" in var` substring test, a name-prefix subnet family, a
hardcoded pool), these configs would not come back clean.

What this file does NOT claim
-----------------------------
The *syntax* section is still Cisco-shaped here, deliberately, because the
engine does not read `schema.syntax` yet: `extract.py`, `section.py`,
`line_analyzer.py` and `section_comparer.py` each match against their own
module-level regexes, and the schema's syntax block is currently validated and
then ignored. `test_bundled_syntax_matches_hardcoded` at the bottom of this file
is what pins the two representations together. Until those modules take their
patterns from the schema, a genuinely different block syntax cannot be tested,
and claiming otherwise here would be the kind of green test that hides work.

Generality therefore holds for vocabulary, which is what the schema migration
set out to externalize, and not yet for dialect.
"""
import contextlib
import io
import json
import os

import pytest

from conftee.models.config_compare import ConfigCompare
from conftee.models.extract import Extract
from conftee.models.gen_summary import GenSummary
from conftee.models.outline import Outline
from conftee.utils import schema as schema_module

# A web-server vocabulary, overlapping the bundled schema nowhere. The block
# markers are Cisco-shaped for the reason given in the module docstring.
WEB_SCHEMA = """
syntax:
  variable: '\\{[\\-\\#\\w]+\\}'
  expression: '\\{\\{[\\-\\#\\w]+\\}[-+][0-9]\\}'
  operation: '\\}[+-]([1-9][0-9]?|[0-9])'
  blocks:
    device:
      title_line: '^\\s*~+\\s*([a-zA-Z0-9\\-\\_\\#]+\\s*)+\\s*~*$'
      title: '[a-zA-Z\\_\\#][\\-\\w\\s]+\\s*'
    section:
      title_line: '^\\s*!\\s*#+\\s([A-Z]+\\s*)+START\\s[0-9a-zA-Z#\\s]*$'
      title: '([A-Z]+\\s*)+START'
      title_suffix: 'START'
types:
  port:
    regex: '(80|443|8080|[1-9][0-9]{3})'
    arithmetic: int
  hostname:
    regex: '[a-z][a-z0-9\\-]*\\.example\\.(com|net)'
  ipv4:
    regex: '([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\\.([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])'
    arithmetic: ipv4
  subnet_mask:
    regex: '255\\.255\\.255\\.(0|128|192|224|240|248)'
  fs_path:
    regex: '/[\\w/\\-\\.]*'
  worker_count:
    regex: '([1-9]|[1-9][0-9])'
    arithmetic: int
pools:
  backend_net:
    kind: ipv4
    ip: '10.20.0.0'
    mask: '/16'
variables:
  Listen_port: port
  Server_name: hostname
  Backend_first: {type: ipv4, pool: backend_net}
  Backend_second: {type: ipv4, pool: backend_net}
  # `role: netmask` is the whole reason this one is found by the subnet check.
  # Its name contains no "netmask" substring, which the engine used to require.
  Backend_mask: {type: subnet_mask, role: netmask}
  # Paths legitimately differ line to line, so they are exempt from the
  # file-wide "one value per variable" rule.
  Root_path: {type: fs_path, scope: none}
  Workers: worker_count
groups:
  # A subnet family declared outright. The members share no name prefix, which
  # is what the retired union-find keyed on.
  backend_pool:
    members: [Backend_first, Backend_second, Backend_mask]
"""

# Note the absence of nginx's trailing semicolons. See
# test_variable_must_be_its_own_token for why, and what it costs.
GOLDEN = """~~~~~~~ web01 edge proxy ~~~~~~~
! ########### UPSTREAM START ###########
worker_processes {Workers}
listen {Listen_port}
server_name {Server_name}
upstream backend {Backend_first} {Backend_mask}
upstream backup {{Backend_first}+1} {Backend_mask}
root {Root_path}
! ########### UPSTREAM END ###########
"""

CONFORMING = """~~~~~~~ web01 edge proxy ~~~~~~~
! ########### UPSTREAM START ###########
worker_processes 8
listen 443
server_name app.example.com
upstream backend 10.20.5.0 255.255.255.0
upstream backup 10.20.5.1 255.255.255.0
root /var/www/html
! ########### UPSTREAM END ###########
"""


def run(golden_text, user_text, schema_text=WEB_SCHEMA):
    """Run one pair through the real pipeline, as tests/test_regression.py does."""
    schema = schema_module.loads(schema_text)
    golden = golden_text.splitlines(keepends=True)
    user = user_text.splitlines(keepends=True)

    # The engine narrates progress to stdout; keep test output readable.
    with contextlib.redirect_stdout(io.StringIO()):
        extract_golden, extract_user = Extract._extract_structs(golden, user)
        outline_golden = Outline(golden, extract_golden, True)
        outline_user = Outline(user, extract_user, False)
        results = ConfigCompare(
            (extract_golden, extract_user),
            (outline_golden, outline_user),
            schema,
        ).calculate_diff(infra_prefixes=[])
        return GenSummary(schema).generate_reports(
            outline_golden, outline_user, results
        )


def counts(summary):
    """Turn the summary rows into a {label: count} mapping.

    The counts arrive as numpy integers from the Pandas layer, so they are cast
    before comparison: `np.int64(0) == 0` holds, but a dict comparison reads
    better in a failure message with plain ints.
    """
    return {label: int(count) for count, label in summary}


def findings(report):
    """Collect the finding types the report records, across every block.

    The summary counts only some categories: a pool or subnet violation is a
    `value-wrong-src` finding, which is reported in full but does not raise the
    "value mismatches" row. Asserting on the report rather than on the summary
    is both the stricter check and the one that matches what a user reads.
    """
    parsed = json.loads(report) if isinstance(report, str) else report
    found = []
    for sections in parsed.values():
        for entries in sections.values():
            for finding_type, _detail in entries:
                found += [part.strip() for part in finding_type.split(",")]
    return found


def test_conforming_config_is_clean():
    """A conforming config in a foreign vocabulary reports nothing.

    This is the load-bearing assertion of the file. Every count must be zero:
    a single spurious finding would mean some check is still keying off Cisco
    naming rather than off the schema.
    """
    summary, _df, report = run(GOLDEN, CONFORMING)
    assert counts(summary) == {
        "value mismatches": 0,
        "struct mismatches": 0,
        "value inconsistencies": 0,
        "missed or extra lines": 0,
        "command mismatches": 0,
    }
    # The summary does not raise a row for every finding type, so check the
    # report is empty too rather than inferring it from five zeroes.
    assert findings(report) == []


def test_expression_arithmetic_uses_declared_engine():
    """`{{Backend_first}+1}` resolves through the type's `arithmetic: ipv4`.

    The golden line pairs a variable with the expression derived from it, so an
    engine that ignored the declaration would either raise or fail to match the
    incremented address.

    A value that contradicts the expression is reported as an inconsistency:
    `{Backend_first}` and `{{Backend_first}+1}` are the same variable, so .5.0
    paired with .5.9 means it holds two values at once, which the engine sees
    before it asks whether either is wrong.
    """
    _summary, _df, report = run(GOLDEN, CONFORMING)
    assert findings(report) == []

    broken = CONFORMING.replace(
        "upstream backup 10.20.5.1", "upstream backup 10.20.5.9"
    )
    _summary, _df, report = run(GOLDEN, broken)
    assert "value-incons" in findings(report)


def test_value_outside_its_declared_type_is_caught():
    """A value its type's regex rejects is reported, with no Cisco name in sight."""
    broken = CONFORMING.replace("listen 443", "listen 99999")
    summary, _df, _report = run(GOLDEN, broken)
    assert counts(summary)["value mismatches"] > 0


def test_value_outside_its_pool_is_caught():
    """The pool check runs against the declared range, not a hardcoded one.

    10.99.x is a valid address and matches the ipv4 type, so only the declared
    `backend_net` pool makes it wrong.
    """
    broken = CONFORMING.replace(
        "upstream backend 10.20.5.0", "upstream backend 10.99.5.0"
    ).replace("upstream backup 10.20.5.1", "upstream backup 10.99.5.1")
    _summary, _df, report = run(GOLDEN, broken)
    assert "value-wrong-src" in findings(report)
    # The finding names the pool it came from, which is derived from the
    # schema's own pool name rather than looked up in a fixed table.
    assert "backend-net-pool" in report


def test_subnet_group_is_found_without_a_naming_convention():
    """The subnet check fires on a group whose members share no name prefix.

    `Backend_first` and `Backend_mask` would never have been clustered by the
    retired union-find over name prefixes, and `Backend_mask` would never have
    been recognized as a mask by the `"netmask" in var` substring test. Both
    now come from the schema, so moving one member out of the subnet is caught.
    """
    broken = CONFORMING.replace(
        "upstream backup 10.20.5.1", "upstream backup 10.20.77.1"
    )
    _summary, _df, report = run(GOLDEN, broken)
    assert "value-wrong-src" in findings(report)
    # The subnet range is computed from the member carrying `role: netmask`,
    # and the finding is named after the group the schema declared.
    assert "backend_pool-subnet" in report
    assert "10.20.5.0 - 10.20.5.255" in report


def test_scope_none_exempts_a_variable_from_consistency():
    """`scope: none` lets one variable hold different values in one file.

    Without the exemption the second `root` line would be an inconsistency,
    which is how the engine treats every other repeated variable.
    """
    golden = GOLDEN.replace(
        "root {Root_path}\n", "root {Root_path}\nroot {Root_path}\n"
    )
    user = CONFORMING.replace(
        "root /var/www/html\n", "root /var/www/html\nroot /srv/other\n"
    )
    summary, _df, _report = run(golden, user)
    assert counts(summary)["value inconsistencies"] == 0


def test_file_scope_still_catches_an_inconsistency():
    """The counterpart to the test above: a scoped variable must stay constant.

    Guards against `scope: none` passing for the wrong reason, namely the
    consistency check not running at all in this schema.
    """
    golden = GOLDEN.replace(
        "listen {Listen_port}\n", "listen {Listen_port}\nlisten {Listen_port}\n"
    )
    user = CONFORMING.replace("listen 443\n", "listen 443\nlisten 8080\n")
    summary, _df, _report = run(golden, user)
    assert counts(summary)["value inconsistencies"] > 0


def test_variable_must_be_its_own_token():
    """A variable glued to punctuation is read as literal text, not a slot.

    This is a real limit on how general the tool is today, recorded rather than
    worked around. Words are split on whitespace and a word counts as a
    variable slot only when the variable regex matches the whole of it, so
    nginx's `listen {Listen_port};` leaves the variable embedded in a longer
    token. The line then compares as literal text and every value differs,
    which is why the fixtures above drop the trailing semicolons.

    Supporting such dialects means matching variables inside a word rather than
    across the whole of it. If that lands, this test should start failing.
    """
    golden = GOLDEN.replace("listen {Listen_port}", "listen {Listen_port};")
    user = CONFORMING.replace("listen 443", "listen 443;")
    summary, _df, _report = run(golden, user)
    assert counts(summary)["command mismatches"] > 0


def test_a_second_schema_does_not_disturb_the_first():
    """Two schemas coexist in one process, holding no shared state.

    The engine takes a schema as an argument precisely so that this is
    representable; a module-level accessor would make it impossible. Worth an
    explicit check because the failure mode is cross-test contamination, which
    shows up as an unrelated test failing in a different order.
    """
    web = schema_module.loads(WEB_SCHEMA)
    bundled = schema_module.load(
        __import__("os").path.join(
            __import__("os").path.dirname(__import__("os").path.dirname(__file__)),
            "conftee",
            "schemas",
            "cisco-campus.yaml",
        )
    )
    assert set(web.variables).isdisjoint(set(bundled.variables))
    # Re-running after loading the other schema must still come back clean.
    summary, _df, _report = run(GOLDEN, CONFORMING)
    assert counts(summary)["value mismatches"] == 0


@pytest.mark.parametrize(
    "variable, expected",
    [
        ("Backend_mask", True),
        ("Backend_first", False),
        ("Root_path", False),
    ],
)
def test_netmask_role_is_declared_not_inferred(variable, expected):
    """`role: netmask` identifies the mask, since no name contains "netmask"."""
    schema = schema_module.loads(WEB_SCHEMA)
    assert schema.is_netmask(variable) is expected


BUNDLED_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "conftee",
    "schemas",
    "cisco-campus.yaml",
)


def test_bundled_syntax_matches_hardcoded():
    """The bundled schema's syntax section reproduces the hardcoded regexes.

    This is the half the module docstring above says does not work yet: the
    four modules below own the patterns, and `syntax:` is validated and then
    unread. Nothing would fail if the two drifted apart, which is exactly why
    the check is worth keeping. It is the one test carried over from the
    retired `test_schema_equivalence.py`, because it reads no vocabulary
    constant.
    """
    from conftee.models.extract import DEVICE_TITLE_LINE_REGEX, DEVICE_TITLE_REGEX
    from conftee.models.line_analyzer import EXPRESSION_REGEX, VARIABLE_REGEX
    from conftee.models.section import (
        SECTION_TITLE_LINE_REGEX,
        SECTION_TITLE_REGEX,
        SECTION_TITLE_SUFFIX,
    )
    from conftee.models.section_comparer import OPERATION_REGEX

    syntax = schema_module.load(BUNDLED_SCHEMA_PATH).syntax
    assert syntax.variable_regex.pattern == VARIABLE_REGEX
    assert syntax.expression_regex.pattern == EXPRESSION_REGEX
    assert syntax.operation_regex.pattern == OPERATION_REGEX
    assert syntax.device_title_line_regex.pattern == DEVICE_TITLE_LINE_REGEX
    assert syntax.device_title_regex.pattern == DEVICE_TITLE_REGEX
    assert syntax.section_title_line_regex.pattern == SECTION_TITLE_LINE_REGEX
    assert syntax.section_title_regex.pattern == SECTION_TITLE_REGEX
    assert syntax.section_title_suffix == SECTION_TITLE_SUFFIX
