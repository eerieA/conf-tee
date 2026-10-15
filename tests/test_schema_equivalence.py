"""Pin schemas/cisco-campus.yaml to the constants it was transcribed from.

This is the gate for the schema migration. The schema is built and proven to
reproduce the engine's current constants exactly *before* any engine code reads
it, so that a transcription mistake fails here, pointing at the offending entry,
rather than surfacing later as a shifted report in a corpus of 63 pairs.

Once the engine consumes the schema and the constants modules are deleted, this
file goes with them: at that point tests/test_regression.py is what pins
behavior. Until then it is the only thing keeping the two representations honest.
"""
import os

import pytest

from conftee.models.constants_singleton import ConstantsSingleton
from conftee.utils import schema as schema_module
from conftee.utils.constants import (
    INT_VARIABLES,
    IPV4_VARIABLES,
    IPV4_VARIABLES_INFRA,
    IPV4_VARIABLES_USER,
    SUBNET_CLUSTERS,
    WORD_TYPE_REGEXES,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "conftee", "schemas", "cisco-campus.yaml")


@pytest.fixture(scope="module")
def schema():
    return schema_module.load(SCHEMA_PATH)


def test_variable_set_matches(schema):
    """The schema declares exactly the engine's vocabulary, no more or less."""
    assert set(schema.variables) == set(WORD_TYPE_REGEXES)


@pytest.mark.parametrize("name", sorted(WORD_TYPE_REGEXES))
def test_regex_matches(schema, name):
    """Each variable resolves to the same pattern string it has today.

    Parametrized per variable so a transcription slip names the offender rather
    than reporting one failed dict comparison across the whole vocabulary.
    """
    assert schema.regex_for(name).pattern == WORD_TYPE_REGEXES[name]


def test_ipv4_arithmetic_membership_matches(schema):
    assert schema.variables_with_arithmetic("ipv4") == set(IPV4_VARIABLES)


def test_int_arithmetic_membership_matches(schema):
    assert schema.variables_with_arithmetic("int") == set(INT_VARIABLES)


def test_variables_without_arithmetic_match(schema):
    """Variables in neither arithmetic list stay in neither.

    Guards the direction the other two tests cannot: granting arithmetic to a
    variable that lacks it today would make a previously-raising expression
    silently evaluate.
    """
    expected = set(WORD_TYPE_REGEXES) - set(IPV4_VARIABLES) - set(INT_VARIABLES)
    assert schema.variables_with_arithmetic(None) == expected


# The scope lists diff_helpers held until the schema replaced them, copied here
# verbatim. They lived next to the code that read them, so converting that module
# removed the definitions; keeping them as test data is what still makes the
# assertion below a comparison against the old behavior rather than a tautology.
VAR_CONS_SECTION = ["GW-FW_outside_IP"]
VAR_NO_CONS = [
    "int_#",
    "password",
    "key_word",
    "IP_local_pool_first_IP",
    "IP_local_pool_last_IP",
    "IP_local_pool_prefix",
    "IP_local_pool_netmask",
    "test_int_#",
]
# Computed by subtraction, as diff_helpers did at import time.
VAR_CONS_FILE = [
    key for key in WORD_TYPE_REGEXES
    if key not in VAR_CONS_SECTION and key not in VAR_NO_CONS
]


def test_consistency_scopes_match(schema):
    """`scope` reproduces the subtract-to-compute VAR_CONS_* lists."""
    assert schema.variables_with_scope("section") == set(VAR_CONS_SECTION)
    assert schema.variables_with_scope("none") == set(VAR_NO_CONS)
    assert schema.variables_with_scope("file") == set(VAR_CONS_FILE)


def test_netmask_role_matches_substring_test(schema):
    """`role: netmask` covers exactly what `"netmask" in var` covers today."""
    expected = {v for v in WORD_TYPE_REGEXES if "netmask" in v.lower()}
    actual = {v for v in WORD_TYPE_REGEXES if schema.is_netmask(v)}
    assert actual == expected


def test_subnet_groups_match_disjoint_set(schema):
    """Declared groups reproduce the union-find clusters, for subnet families.

    Only the SUBNET_CLUSTERS entries matter: DisjointSet buckets every variable
    by name prefix, but `_value_is_in_subnet` acts on a cluster only when it is
    one of those four.
    """
    clusters = ConstantsSingleton.get_clusters_dict()
    expected = {c: set(clusters[c]) for c in SUBNET_CLUSTERS if c in clusters}
    actual = {name: set(g.members) for name, g in schema.groups.items()}
    assert actual == expected


def test_pool_membership_matches(schema):
    """Variables carry the same IP and VLAN pool assignments as today."""
    user_ipv4 = {
        v for v in WORD_TYPE_REGEXES
        if (p := schema.pool_for(v)) is not None and p.name == "user_ipv4"
    }
    infra_ipv4 = {
        v for v in WORD_TYPE_REGEXES
        if (p := schema.pool_for(v)) is not None and p.name == "infra_ipv4"
    }
    user_vlan = {
        v for v in WORD_TYPE_REGEXES
        if (p := schema.pool_for(v)) is not None and p.name == "user_vlan"
    }
    assert user_ipv4 == set(IPV4_VARIABLES_USER)
    assert infra_ipv4 == set(IPV4_VARIABLES_INFRA)
    # The VLAN pool check is hardcoded to this one variable in diff_helpers:370.
    assert user_vlan == {"Vlan_ID_user"}


def test_syntax_regexes_match_hardcoded(schema):
    """The syntax section reproduces the regexes hardcoded across three modules."""
    from conftee.models.extract import DEVICE_TITLE_LINE_REGEX, DEVICE_TITLE_REGEX
    from conftee.models.line_analyzer import EXPRESSION_REGEX, VARIABLE_REGEX
    from conftee.models.section import (
        SECTION_TITLE_LINE_REGEX,
        SECTION_TITLE_REGEX,
        SECTION_TITLE_SUFFIX,
    )
    from conftee.models.section_comparer import OPERATION_REGEX

    syntax = schema.syntax
    assert syntax.variable_regex.pattern == VARIABLE_REGEX
    assert syntax.expression_regex.pattern == EXPRESSION_REGEX
    assert syntax.operation_regex.pattern == OPERATION_REGEX
    assert syntax.device_title_line_regex.pattern == DEVICE_TITLE_LINE_REGEX
    assert syntax.device_title_regex.pattern == DEVICE_TITLE_REGEX
    assert syntax.section_title_line_regex.pattern == SECTION_TITLE_LINE_REGEX
    assert syntax.section_title_regex.pattern == SECTION_TITLE_REGEX
    assert syntax.section_title_suffix == SECTION_TITLE_SUFFIX


# The pool ranges get_legit_ip_pools() and get_legit_vlan_pools() returned until
# the schema replaced them, copied here verbatim for the same reason as the scope
# lists above: the helpers were deleted with the code that called them, and
# keeping their values as test data is what makes the assertion below a
# comparison against the old behavior rather than a tautology.
LEGIT_IP_POOL_INFRA = {"ip": "10.45.0.0", "mask": "/16"}
LEGIT_IP_POOL_USER = {"ip": "10.45.0.0", "mask": "/16"}
LEGIT_VLAN_POOL_INFRA = {"start": 1, "end": 4096}
LEGIT_VLAN_POOL_USER = {"start": 1, "end": 4096}


def test_pool_ranges_match_helpers(schema):
    """Pool definitions carry the values the helper functions returned."""
    infra_ip, user_ip = LEGIT_IP_POOL_INFRA, LEGIT_IP_POOL_USER
    infra_vlan, user_vlan = LEGIT_VLAN_POOL_INFRA, LEGIT_VLAN_POOL_USER

    assert (schema.pools["infra_ipv4"].ip, schema.pools["infra_ipv4"].mask) == (
        infra_ip["ip"],
        infra_ip["mask"],
    )
    assert (schema.pools["user_ipv4"].ip, schema.pools["user_ipv4"].mask) == (
        user_ip["ip"],
        user_ip["mask"],
    )
    assert (schema.pools["user_vlan"].start, schema.pools["user_vlan"].end) == (
        user_vlan["start"],
        user_vlan["end"],
    )
    # The infra VLAN pool is identical to the user one, which is why a single
    # `user_vlan` pool suffices, and why _value_is_in_pool could drop the
    # section-conditional branch that chose between them: both arms compared
    # against the same range. If they ever diverge, the schema needs a second
    # pool, Vlan_ID_* variables outside USER PREFIX need to point at it, and that
    # branch has to come back in some form.
    assert (infra_vlan["start"], infra_vlan["end"]) == (
        user_vlan["start"],
        user_vlan["end"],
    )


def test_every_variable_validates_its_own_type(schema):
    """Sanity check that types resolved to usable compiled patterns."""
    for name, var in schema.variables.items():
        assert var.type is not None, name
        assert var.type.regex is not None, name
