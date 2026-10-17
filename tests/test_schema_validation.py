"""Pin the load-time validation contract of `conftee.utils.schema`.

A schema is the one file a user of this tool has to write by hand, and the
error raised when they get it wrong is the whole of their debugging
experience. So the contract under test here is not just "a bad schema is
rejected" but "it is rejected as a SchemaError carrying a dotted path that
names the offending entry".

That second half is what nothing else checks. A refactor that let any of these
surface as a bare KeyError, TypeError or AttributeError would still leave the
engine working on the bundled schema, and every other test in this suite would
pass. `tests/test_schema_equivalence.py` loads only `cisco-campus.yaml`, which
is valid by construction, so no malformed input reaches the parser there.

Each case mutates `BASE`, a minimal valid schema, so that exactly one thing is
wrong and the assertion attributes the failure to that one thing. The regexes
in it are deliberately trivial: this file tests the parser, not the dialect.
"""
import pytest

from conftee.utils import schema as schema_module
from conftee.utils.schema import SchemaError

# A minimal schema that loads cleanly. Every test below mutates one piece of
# it, so `test_base_is_valid` failing means the fixtures are broken rather
# than the code under test.
BASE = """
syntax:
  variable: '\\{\\w+\\}'
  expression: '\\{\\{\\w+\\}[-+][0-9]\\}'
  operation: '\\}[+-][0-9]'
  blocks:
    device:
      title_line: '^~(.*)~$'
      title: '\\w+'
    section:
      title_line: '^!(.*)START$'
      title: '\\w+'
      title_suffix: 'START'
types:
  word:
    regex: '\\w+'
pools:
  p:
    kind: ipv4
    ip: '10.0.0.0'
    mask: '/16'
variables:
  A: word
  B: word
groups:
  g:
    members: [A, B]
"""


# The whole text of each nested block, so a test can replace one entirely.
# Swapping only a block's header for a scalar would leave its children
# indented underneath, which YAML rejects before the validator ever runs, and
# the test would then be asserting against a parse error rather than against
# the check it names.
SYNTAX_BLOCK = BASE[BASE.index("syntax:") : BASE.index("types:")]
BLOCKS_BLOCK = SYNTAX_BLOCK[SYNTAX_BLOCK.index("  blocks:") :]
DEVICE_BLOCK = BLOCKS_BLOCK[BLOCKS_BLOCK.index("    device:") : BLOCKS_BLOCK.index("    section:")]
TYPES_BLOCK = BASE[BASE.index("types:") : BASE.index("pools:")]
POOLS_BLOCK = BASE[BASE.index("pools:") : BASE.index("variables:")]
VARIABLES_BLOCK = BASE[BASE.index("variables:") : BASE.index("groups:")]
GROUPS_BLOCK = BASE[BASE.index("groups:") :]


def mutate(old, new=""):
    """Return BASE with one fragment replaced, asserting the fragment was there.

    Without the count check a fixture whose text drifts out of sync with BASE
    would silently stop mutating anything, and the test would then assert that
    a *valid* schema raises, which it would do for no discoverable reason.
    """
    assert BASE.count(old) == 1, f"fragment not unique in BASE: {old!r}"
    return BASE.replace(old, new)


def assert_rejected(text, path):
    """Assert the schema is rejected as a SchemaError naming `path`."""
    with pytest.raises(SchemaError) as exc_info:
        schema_module.loads(text)
    assert exc_info.value.path == path
    # The path is also prefixed onto the message, which is what a user
    # actually reads off their terminal.
    assert str(exc_info.value).startswith(f"{path}: ")


def test_base_is_valid():
    """The unmutated fixture loads, so every rejection below is the mutation."""
    schema = schema_module.loads(BASE)
    assert set(schema.variables) == {"A", "B"}
    assert set(schema.groups) == {"g"}
    assert set(schema.pools) == {"p"}


# --- Whole-file faults, which have no dotted path to report ---------------


def test_unparseable_yaml_is_wrapped():
    """A YAML syntax error arrives as SchemaError, not yaml.YAMLError.

    Callers catch SchemaError; letting the underlying library's exception
    escape would make a typo'd schema crash a caller that correctly handles
    every documented failure.
    """
    with pytest.raises(SchemaError) as exc_info:
        schema_module.loads("syntax: [unclosed\n")
    assert "could not parse YAML" in str(exc_info.value)


@pytest.mark.parametrize(
    "text, described",
    [
        ("- a\n- b\n", "list"),
        ("", "NoneType"),
    ],
    ids=["list", "empty"],
)
def test_root_must_be_a_mapping(text, described):
    with pytest.raises(SchemaError) as exc_info:
        schema_module.loads(text)
    assert "schema root must be a mapping" in str(exc_info.value)
    assert described in str(exc_info.value)


# --- Required sections and keys -------------------------------------------


@pytest.mark.parametrize(
    "block, path",
    [
        (SYNTAX_BLOCK, "syntax"),
        (TYPES_BLOCK, "types"),
        (VARIABLES_BLOCK, "variables"),
    ],
    ids=["syntax", "types", "variables"],
)
def test_missing_required_section(block, path):
    """The three mandatory top-level sections are each reported by name."""
    assert_rejected(mutate(block), path)


@pytest.mark.parametrize(
    "old, path",
    [
        ("  variable: '\\{\\w+\\}'\n", "syntax.variable"),
        ("  expression: '\\{\\{\\w+\\}[-+][0-9]\\}'\n", "syntax.expression"),
        ("  operation: '\\}[+-][0-9]'\n", "syntax.operation"),
        (BLOCKS_BLOCK, "syntax.blocks"),
        ("      title_line: '^~(.*)~$'\n", "syntax.blocks.device.title_line"),
        ("      title_suffix: 'START'\n", "syntax.blocks.section.title_suffix"),
    ],
    ids=["variable", "expression", "operation", "blocks", "device_title_line", "suffix"],
)
def test_missing_syntax_key(old, path):
    """Every syntax key is required, and names its own position when absent."""
    assert_rejected(mutate(old), path)


def test_type_without_regex():
    assert_rejected(mutate("    regex: '\\w+'\n", "    arithmetic: int\n"), "types.word.regex")


def test_variable_without_type():
    assert_rejected(mutate("  A: word", "  A: {scope: file}"), "variables.A.type")


def test_group_without_members():
    assert_rejected(
        mutate("    members: [A, B]", "    constraint: same_subnet"), "groups.g.members"
    )


def test_pool_without_kind():
    assert_rejected(mutate("    kind: ipv4\n"), "pools.p.kind")


def test_ipv4_pool_without_ip():
    assert_rejected(mutate("    ip: '10.0.0.0'\n"), "pools.p.ip")


def test_int_pool_without_start():
    assert_rejected(
        mutate("    kind: ipv4\n    ip: '10.0.0.0'\n    mask: '/16'", "    kind: int\n    end: 1"),
        "pools.p.start",
    )


# --- Wrong types in the right places --------------------------------------


@pytest.mark.parametrize(
    "old, new, path",
    [
        (SYNTAX_BLOCK, "syntax: 7\n", "syntax"),
        (BLOCKS_BLOCK, "  blocks: [1, 2]\n", "syntax.blocks"),
        (DEVICE_BLOCK, "    device: 7\n", "syntax.blocks.device"),
        ("      title_suffix: 'START'", "      title_suffix: 7", "syntax.blocks.section.title_suffix"),
        (TYPES_BLOCK, "types: [a, b]\n", "types"),
        (VARIABLES_BLOCK, "variables: [A, B]\n", "variables"),
        ("    members: [A, B]", "    members: A", "groups.g.members"),
    ],
    ids=["syntax", "blocks", "device", "suffix", "types", "variables", "members"],
)
def test_section_of_wrong_type(old, new, path):
    """A section written as the wrong YAML type is reported at its own path."""
    assert_rejected(mutate(old, new), path)


@pytest.mark.parametrize(
    "old, new, path",
    [
        ("  word:\n    regex: '\\w+'", "  word: [1, 2]", "types.word.regex"),
        ("  A: word", "  A: 7", "variables.A.type"),
        ("  g:\n    members: [A, B]", "  g: 7", "groups.g.members"),
    ],
    ids=["type", "variable", "group"],
)
def test_entry_body_of_wrong_type(old, new, path):
    """An individual entry written as a scalar or list names that entry."""
    assert_rejected(mutate(old, new), path)


@pytest.mark.parametrize(
    "section", ["pools", "groups"], ids=["pools", "groups"]
)
def test_optional_section_of_wrong_type(section):
    """The optional sections are type-checked like the mandatory ones.

    These two are reached by `.get()` rather than by the helper that validates
    the mandatory sections, so until this was tested a list here escaped as a
    bare AttributeError with no path at all, while every neighbouring mistake
    produced a clean message.
    """
    body = {"pools": POOLS_BLOCK, "groups": GROUPS_BLOCK}[section]
    assert_rejected(mutate(body, f"{section}: [1, 2]\n"), section)


@pytest.mark.parametrize(
    "section", ["pools", "groups"], ids=["pools", "groups"]
)
def test_optional_section_may_be_absent_or_null(section):
    """Omitting an optional section, or leaving it empty, is not an error.

    `groups:` with nothing under it parses as None rather than as an empty
    mapping, which is an easy way to write "no groups yet" by hand.
    """
    body = {"pools": POOLS_BLOCK, "groups": GROUPS_BLOCK}[section]
    assert getattr(schema_module.loads(mutate(body)), section) == {}
    assert getattr(schema_module.loads(mutate(body, f"{section}:\n")), section) == {}


# --- Regexes ---------------------------------------------------------------


@pytest.mark.parametrize(
    "old, new, path",
    [
        ("  variable: '\\{\\w+\\}'", "  variable: 7", "syntax.variable"),
        ("    regex: '\\w+'", "    regex: 7", "types.word.regex"),
    ],
    ids=["syntax", "type"],
)
def test_regex_must_be_a_string(old, new, path):
    assert_rejected(mutate(old, new), path)


@pytest.mark.parametrize(
    "old, new, path",
    [
        ("  variable: '\\{\\w+\\}'", "  variable: '[unclosed'", "syntax.variable"),
        ("    regex: '\\w+'", "    regex: '(?P<bad'", "types.word.regex"),
    ],
    ids=["syntax", "type"],
)
def test_uncompilable_regex_is_caught_at_load(old, new, path):
    """A bad pattern fails on load, not on whichever config first hits it.

    Compiling eagerly is what keeps a typo in a rarely-used variable from
    surviving a full corpus run and surfacing much later.
    """
    with pytest.raises(SchemaError) as exc_info:
        schema_module.loads(mutate(old, new))
    assert exc_info.value.path == path
    assert "invalid regex" in str(exc_info.value)


# --- Enumerated values -----------------------------------------------------


def test_unknown_arithmetic_kind():
    """Only the engines the evaluator implements may be declared.

    An unrecognized value here would otherwise mean the variable silently
    behaves as though it had no arithmetic at all, turning a typo into a
    missing check rather than an error.
    """
    with pytest.raises(SchemaError) as exc_info:
        schema_module.loads(mutate("    regex: '\\w+'", "    regex: '\\w+'\n    arithmetic: float"))
    assert exc_info.value.path == "types.word.arithmetic"
    assert "float" in str(exc_info.value)


@pytest.mark.parametrize(
    "new, path",
    [
        ("  A: {type: word, scope: galaxy}", "variables.A.scope"),
        ("  A: {type: word, role: gateway}", "variables.A.role"),
    ],
    ids=["scope", "role"],
)
def test_unknown_enumerated_value(new, path):
    assert_rejected(mutate("  A: word", new), path)


@pytest.mark.parametrize(
    "kind", ["ipv6", "cidr"], ids=["ipv6", "cidr"]
)
def test_unknown_pool_kind(kind):
    assert_rejected(mutate("    kind: ipv4", f"    kind: {kind}"), "pools.p.kind")


# --- Cross-references, resolved at load time ------------------------------


def test_undefined_type_reference():
    assert_rejected(mutate("  A: word", "  A: nosuch"), "variables.A.type")


def test_undefined_pool_reference():
    assert_rejected(mutate("  A: word", "  A: {type: word, pool: nosuch}"), "variables.A.pool")


def test_undefined_group_member():
    """A group may only list variables that exist.

    Catching this at load time is what stops a renamed variable from quietly
    shrinking a subnet family instead of failing.
    """
    with pytest.raises(SchemaError) as exc_info:
        schema_module.loads(mutate("    members: [A, B]", "    members: [A, Z]"))
    assert exc_info.value.path == "groups.g.members"
    assert "Z" in str(exc_info.value)


def test_empty_group_is_rejected():
    assert_rejected(mutate("    members: [A, B]", "    members: []"), "groups.g.members")


def test_variable_in_two_groups():
    """Overlapping subnet families have no answer to "which subnet", so reject.

    The message names both groups and the shared variable, since the fix
    requires knowing all three.
    """
    with pytest.raises(SchemaError) as exc_info:
        schema_module.loads(BASE + "  h:\n    members: [B]\n")
    assert exc_info.value.path == "groups.h.members"
    message = str(exc_info.value)
    assert "'g'" in message and "'h'" in message and "B" in message


# --- Accessors on a loaded schema -----------------------------------------


def test_accessors_reflect_declarations():
    """The accessors the engine calls return what the file declared.

    Spot-checked on a schema small enough to read, which the equivalence test
    cannot do: it compares the bundled schema against the constants it was
    transcribed from, so it would pass even if both were wrong together.
    """
    schema = schema_module.loads(
        mutate(
            "variables:\n  A: word\n  B: word",
            "variables:\n"
            "  A: {type: word, scope: section, pool: p}\n"
            "  B: {type: word, role: netmask}",
        )
    )
    assert schema.variables_with_scope("section") == {"A"}
    assert schema.variables_with_scope("file") == {"B"}
    assert schema.is_netmask("B") and not schema.is_netmask("A")
    assert schema.pool_for("A").name == "p"
    assert schema.pool_for("B") is None
    assert schema.group_of("A").name == "g"
    assert schema.regex_for("A").pattern == "\\w+"


def test_accessors_are_safe_for_unknown_names():
    """Names the schema never declared get a negative answer, not a KeyError.

    The engine asks these questions about tokens it found in a config file, so
    an unrecognized name is ordinary input rather than a programming error.
    """
    schema = schema_module.loads(BASE)
    assert schema.is_netmask("NoSuch") is False
    assert schema.pool_for("NoSuch") is None
    assert schema.group_of("NoSuch") is None


def test_int_pool_start_above_end():
    assert_rejected(
        mutate(
            "    kind: ipv4\n    ip: '10.0.0.0'\n    mask: '/16'",
            "    kind: int\n    start: 99\n    end: 1",
        ),
        "pools.p",
    )


def test_bare_string_variable_is_shorthand_for_type():
    """`A: word` and `A: {type: word}` mean the same thing.

    The shorthand is what keeps the common case to one line per variable in a
    file with a hundred of them, so it is part of the format, not a courtesy.
    """
    shorthand = schema_module.loads(BASE)
    longhand = schema_module.loads(mutate("  A: word", "  A: {type: word}"))
    assert shorthand.variables["A"].type_name == longhand.variables["A"].type_name
    assert shorthand.variables["A"].scope == longhand.variables["A"].scope == "file"
