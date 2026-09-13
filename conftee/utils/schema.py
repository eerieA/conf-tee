"""Load a conformance schema from YAML into validated internal structures.

A schema declares the vocabulary a config template is written in: how variables
are delimited, what kinds of values exist, which variables use which kind, which
variables must agree with each other, and what ranges their values must fall in.
The engine previously recovered all of this by matching on variable *names*, so
a user had to adopt one organization's naming convention to get correct results.

Nothing in this module is wired into the engine yet. It is built and validated
first, against `utils/constants.py`, so that a transcription error in the schema
file surfaces as a failed equivalence test rather than as a shifted report much
later. See docs/repurposing-plan.md section 2.
"""
import re

import yaml


class SchemaError(ValueError):
    """A schema file is malformed, inconsistent, or references undefined names.

    Carries the offending location as a dotted path (e.g. `variables.User_prefix.type`)
    so an author is pointed at the entry to fix, not just told the file is bad.
    """

    def __init__(self, message, path=None):
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


# Arithmetic engines a type may declare. A type with no engine cannot appear in
# an expression like {{Var}+1}; the engine raises rather than guessing, which is
# what `section_comparer._evaluate_expression` does today for a variable in
# neither IPV4_VARIABLES nor INT_VARIABLES.
ARITHMETIC_KINDS = frozenset({"ipv4", "int", None})

# Consistency scopes. `file` and `section` mean a variable keeps one value
# throughout that span; `none` exempts it from the check entirely.
SCOPES = frozenset({"file", "section", "none"})

# Roles carry semantics the engine must know but cannot infer from a regex.
# `netmask` replaces the `"netmask" in var` substring test in diff_helpers.
ROLES = frozenset({"netmask", None})


def _require(mapping, key, path, expected_type=None):
    """Fetch a required key, raising SchemaError rather than KeyError/TypeError."""
    if not isinstance(mapping, dict):
        raise SchemaError(f"expected a mapping, got {type(mapping).__name__}", path)
    if key not in mapping:
        raise SchemaError(f"missing required key {key!r}", path)
    value = mapping[key]
    if expected_type is not None and not isinstance(value, expected_type):
        raise SchemaError(
            f"{key!r} must be {expected_type.__name__}, got {type(value).__name__}",
            path,
        )
    return value


def _compile(pattern, path):
    """Compile a regex, reporting the schema location instead of a bare re.error.

    Patterns are validated at load time so a typo in a rarely-hit variable fails
    immediately rather than on whichever config first exercises it.
    """
    if not isinstance(pattern, str):
        raise SchemaError(f"regex must be a string, got {type(pattern).__name__}", path)
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise SchemaError(f"invalid regex {pattern!r}: {exc}", path) from exc


class Syntax:
    """Delimiters and block markers describing the template dialect.

    Hardcoded today across `line_analyzer.py`, `extract.py` and `section.py`, which
    is what confines the tool to Cisco-style configs.
    """

    def __init__(self, raw, path="syntax"):
        self.variable_regex = _compile(
            _require(raw, "variable", f"{path}.variable"), f"{path}.variable"
        )
        self.expression_regex = _compile(
            _require(raw, "expression", f"{path}.expression"), f"{path}.expression"
        )
        self.operation_regex = _compile(
            _require(raw, "operation", f"{path}.operation"), f"{path}.operation"
        )
        blocks = _require(raw, "blocks", f"{path}.blocks", dict)
        device = _require(blocks, "device", f"{path}.blocks.device", dict)
        section = _require(blocks, "section", f"{path}.blocks.section", dict)

        self.device_title_line_regex = _compile(
            _require(device, "title_line", f"{path}.blocks.device.title_line"),
            f"{path}.blocks.device.title_line",
        )
        self.device_title_regex = _compile(
            _require(device, "title", f"{path}.blocks.device.title"),
            f"{path}.blocks.device.title",
        )
        self.section_title_line_regex = _compile(
            _require(section, "title_line", f"{path}.blocks.section.title_line"),
            f"{path}.blocks.section.title_line",
        )
        self.section_title_regex = _compile(
            _require(section, "title", f"{path}.blocks.section.title"),
            f"{path}.blocks.section.title",
        )
        self.section_title_suffix = _require(
            section, "title_suffix", f"{path}.blocks.section.title_suffix", str
        )


class ValueType:
    """A reusable kind of value: a regex, plus how arithmetic on it works.

    Pairing the two is the point. Today `WORD_TYPE_REGEXES` says what a value
    looks like and `IPV4_VARIABLES` / `INT_VARIABLES` separately say how to do
    arithmetic on it, so a variable can be in the first and neither of the
    others. That combination is a runtime error today and unrepresentable here.
    """

    def __init__(self, name, raw, path):
        self.name = name
        self.regex = _compile(_require(raw, "regex", f"{path}.regex"), f"{path}.regex")
        self.arithmetic = raw.get("arithmetic")
        if self.arithmetic not in ARITHMETIC_KINDS:
            raise SchemaError(
                f"arithmetic must be one of {sorted(k for k in ARITHMETIC_KINDS if k)} "
                f"or omitted, got {self.arithmetic!r}",
                f"{path}.arithmetic",
            )

    def matches(self, value):
        return bool(self.regex.fullmatch(value))


class Variable:
    """One name in the user's vocabulary, bound to a type and a consistency scope."""

    def __init__(self, name, raw, path):
        self.name = name
        # A bare string is shorthand for {type: <name>}, which keeps the common
        # case in the schema file to one line.
        if isinstance(raw, str):
            raw = {"type": raw}
        self.type_name = _require(raw, "type", f"{path}.type", str)
        self.scope = raw.get("scope", "file")
        if self.scope not in SCOPES:
            raise SchemaError(
                f"scope must be one of {sorted(SCOPES)}, got {self.scope!r}",
                f"{path}.scope",
            )
        self.role = raw.get("role")
        if self.role not in ROLES:
            raise SchemaError(
                f"role must be one of {sorted(r for r in ROLES if r)} or omitted, "
                f"got {self.role!r}",
                f"{path}.role",
            )
        self.pool_name = raw.get("pool")
        # Resolved during Schema.__init__ once types are known.
        self.type = None


class Group:
    """An explicit family of variables whose values must share a subnet.

    Replaces the union-find over name prefixes in `constants_singleton.py`, and
    with it the requirement that users name variables in a magic convention.
    """

    def __init__(self, name, raw, path):
        self.name = name
        members = _require(raw, "members", f"{path}.members", list)
        if not members:
            raise SchemaError("group must have at least one member", f"{path}.members")
        self.members = list(members)
        self.constraint = raw.get("constraint", "same_subnet")


class Pool:
    """A named range values must fall within.

    Optional by design. Where the engine currently hardcodes an organization's
    ranges and always checks against them, an absent pool here means the check
    does not run, rather than running against a built-in default.
    """

    def __init__(self, name, raw, path):
        self.name = name
        self.kind = _require(raw, "kind", f"{path}.kind", str)
        if self.kind not in ("ipv4", "int"):
            raise SchemaError(
                f"kind must be 'ipv4' or 'int', got {self.kind!r}", f"{path}.kind"
            )
        if self.kind == "ipv4":
            self.ip = _require(raw, "ip", f"{path}.ip", str)
            self.mask = _require(raw, "mask", f"{path}.mask", str)
            self.start = self.end = None
        else:
            self.start = _require(raw, "start", f"{path}.start", int)
            self.end = _require(raw, "end", f"{path}.end", int)
            self.ip = self.mask = None
            if self.start > self.end:
                raise SchemaError(
                    f"start ({self.start}) is above end ({self.end})", path
                )


class Schema:
    """A parsed, cross-checked schema.

    Cross-references are resolved here rather than lazily, so a schema that loads
    is known to be internally consistent: every variable's type exists, every
    group member is a declared variable, every named pool is defined.
    """

    def __init__(self, raw, source=None):
        self.source = source
        if not isinstance(raw, dict):
            raise SchemaError(
                f"schema root must be a mapping, got {type(raw).__name__}"
            )

        self.syntax = Syntax(_require(raw, "syntax", "syntax", dict))

        self.types = {
            name: ValueType(name, body, f"types.{name}")
            for name, body in _require(raw, "types", "types", dict).items()
        }
        self.pools = {
            name: Pool(name, body, f"pools.{name}")
            for name, body in (raw.get("pools") or {}).items()
        }
        self.variables = {
            name: Variable(name, body, f"variables.{name}")
            for name, body in _require(raw, "variables", "variables", dict).items()
        }
        self.groups = {
            name: Group(name, body, f"groups.{name}")
            for name, body in (raw.get("groups") or {}).items()
        }

        self._resolve()

    def _resolve(self):
        for var in self.variables.values():
            if var.type_name not in self.types:
                raise SchemaError(
                    f"undefined type {var.type_name!r}", f"variables.{var.name}.type"
                )
            var.type = self.types[var.type_name]
            if var.pool_name is not None and var.pool_name not in self.pools:
                raise SchemaError(
                    f"undefined pool {var.pool_name!r}", f"variables.{var.name}.pool"
                )

        for group in self.groups.values():
            for member in group.members:
                if member not in self.variables:
                    raise SchemaError(
                        f"undefined variable {member!r}", f"groups.{group.name}.members"
                    )
            # A variable in two subnet families has no meaningful answer to
            # "which subnet must this value be in", so reject it at load time.
            for other in self.groups.values():
                if other.name >= group.name:
                    continue
                overlap = set(group.members) & set(other.members)
                if overlap:
                    raise SchemaError(
                        f"variables {sorted(overlap)} are in both {other.name!r} "
                        f"and {group.name!r}",
                        f"groups.{group.name}.members",
                    )

    # Accessors below present the schema the way the engine consumes it.

    def regex_for(self, variable_name):
        return self.variables[variable_name].type.regex

    def arithmetic_for(self, variable_name):
        return self.variables[variable_name].type.arithmetic

    def variables_with_arithmetic(self, kind):
        return {
            name
            for name, var in self.variables.items()
            if var.type.arithmetic == kind
        }

    def variables_with_scope(self, scope):
        return {name for name, var in self.variables.items() if var.scope == scope}

    def is_netmask(self, variable_name):
        var = self.variables.get(variable_name)
        return var is not None and var.role == "netmask"

    def group_of(self, variable_name):
        """Return the group a variable belongs to, or None.

        Membership is explicit, so unlike `determine_cluster` this cannot invent
        a family for a variable that was never declared to be in one.
        """
        for group in self.groups.values():
            if variable_name in group.members:
                return group
        return None

    def pool_for(self, variable_name):
        var = self.variables.get(variable_name)
        if var is None or var.pool_name is None:
            return None
        return self.pools[var.pool_name]


def load(path):
    """Load and validate a schema from a YAML file."""
    with open(path, encoding="utf-8") as handle:
        return loads(handle.read(), source=path)


def loads(text, source=None):
    """Load and validate a schema from a YAML string."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SchemaError(f"could not parse YAML: {exc}") from exc
    return Schema(raw, source=source)
