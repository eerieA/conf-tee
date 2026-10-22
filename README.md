# conf-tee

**A reverse-template validator.** Give it a template with typed, named holes and
constraints between them, and a real text file; it reports which holes are wrong
and why.

This is the inverse of Jinja2 or Mako. A template engine renders *forward*,
substituting values into holes. This tool runs the other way: it aligns a real
file against the template, *extracts* the value sitting in each hole, and then
checks those values. So it can answer questions a diff cannot:

- Is this value even the right shape? (`{Listen_port}` bound to `localhost`)
- Is it consistent? (the same `{VRF_name}` appearing twice in one section with
  two different values)
- Does it satisfy an arithmetic relation? (`{{Prefix_1st_IP}+1}` must be exactly
  one past whatever `{Prefix_1st_IP}` turned out to be)
- Is it in the right range? (an address that must fall inside a declared subnet)
- And separately from all of that: are any lines missing, extra, or reordered?

A plain diff reports that two lines differ. This reports that `10.45.54.30` is a
valid address but the wrong one, because an earlier line already bound that
variable to something else.

Output is a JSON report for machines and a table for humans.

## What it checks

| Check | Example of what it catches |
|---|---|
| Value format | A hostname where a port belongs |
| Unbound holes | A variable in the template with nothing in front of it |
| Missing / extra lines | A line the template has and the real file does not |
| Block structure | A device or section block absent, extra, or out of order |
| Consistency | One variable taking two different values in the same scope |
| Arithmetic | `{{First_IP}+1}` not actually one past `{First_IP}` |
| Range / pool membership | An address outside the subnet it was declared in |
| Literal text | A difference in a line with no variables at all |

One check from the original requirements is **not** implemented: detecting
relational anomalies between structures, such as a mismatch between the number
of downlink port channels and the number of downlink device blocks.

## What it does not do yet

**Your vocabulary: yes. Your syntax: no.**

The vocabulary is fully yours. Variable names, value types and their regexes,
arithmetic, consistency scopes, subnet families and address pools are all
declared in a YAML schema you supply. Nothing about them is hardcoded, and
`tests/test_schema_generality.py` demonstrates it by running a web-server
vocabulary that shares no variable, type, pool, or regex with the bundled Cisco
one.

The *block syntax* is not yours yet. How a device block or a section is
recognized is still matched by module-level regexes inside `extract.py`,
`section.py`, `line_analyzer.py` and `section_comparer.py`. The schema has a
`syntax:` section, and it is parsed and validated, but the engine does not read
it. So your files must currently use the Cisco-shaped markers shown below, even
when everything inside them is your own.

There is a second, smaller limit worth knowing before you try your own files: a
variable must be its own whitespace-delimited token. Lines are split on
whitespace, and a word counts as a hole only when the variable pattern matches
the whole word. So nginx's `listen {Listen_port};` does **not** work, because the
trailing semicolon makes the token `{Listen_port};`. Written as
`listen {Listen_port}`, it does.

If you need either of those, the work is scoped in
[docs/repurposing-plan.md](./docs/repurposing-plan.md).

## Install

```
python -m pip install conftee
```

Or from a local build, which is how it is tested today:

```
poetry build
python -m pip install dist/conftee-0.1.5-py3-none-any.whl
```

Python 3.9 or newer. The dependencies (`colored`, `PyYAML`, `pandas`) install
with it.

For working *on* the tool rather than with it, see
[Addendum A](#addendum-a-development-setup).

## Writing a template

A template is your config with values replaced by `{Variable}` holes, plus the
block markers the engine looks for.

```
~~~~~~~ site01-hub1 ~~~~~~~
! ########### VRF START ###########
  ip vrf {VRF_name}
  ip address {Vrfglue_prefix_1st_IP} {Vrfglue_prefix_netmask}
  standby ip {{Vrfglue_prefix_1st_IP}+1}
! ########### VRF END ###########
```

The rules, which are the syntax limitation described above:

- The file must start with `~` (leading whitespace is fine) and contain at least
  one device title and one section title.
- A device title starts with at least three tildes: `~~~ name ~~~`.
- A section starts with exactly `! #` and looks like `! # CONTEXT START #`. The
  matching `END` line is optional.
- Holes are `{Name}`, and names are **case sensitive**: `{User_prefix}` and
  `{User_Prefix}` are two different variables.
- Arithmetic nests the braces and takes integer operands only:
  `{{Vrfglue_prefix_1st_IP}+1}`.
- Device names must match exactly. `al1asa` against `al1asaX` is a structure
  mismatch, not a value mismatch.

## Describing your vocabulary

The schema declares what your variables mean. This is the part that is fully
general. A fragment:

```yaml
types:
  port:
    regex: '(80|443|8080|[1-9][0-9]{3})'
    arithmetic: int
  hostname:
    regex: '[a-z][a-z0-9\-]*\.example\.(com|net)'
  ipv4:
    regex: '([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.(...)'
    arithmetic: ipv4

pools:
  backend_net: {kind: ipv4, ip: '10.20.0.0', mask: '/16'}

variables:
  Listen_port: port
  Server_name: hostname
  Backend_first: {type: ipv4, pool: backend_net}
  Backend_mask: {type: subnet_mask, role: netmask}
  Root_path: {type: fs_path, scope: none}

groups:
  backend_pool:
    members: [Backend_first, Backend_second, Backend_mask]
```

Three things to notice, because each replaces a convention the engine used to
impose on your names:

- `role: netmask` marks the netmask. The engine used to test for the substring
  `netmask` in the variable's own name.
- `groups:` declares a subnet family outright. The engine used to infer families
  from a shared name prefix, so members had to be named alike.
- `scope: none` exempts a variable from the "one value throughout" rule, for
  things like paths that legitimately differ line to line.

[`conftee/schemas/cisco-campus.yaml`](./conftee/schemas/cisco-campus.yaml) is the
bundled schema, commented as the worked reference.

### A non-Cisco example

That fragment is from a real schema. Here is a web-server vocabulary end to end,
sharing nothing with the Cisco one. The template:

```
~~~~~~~ web01 edge proxy ~~~~~~~
! ########### UPSTREAM START ###########
worker_processes {Workers}
listen {Listen_port}
server_name {Server_name}
upstream backend {Backend_first} {Backend_mask}
upstream backup {{Backend_first}+1} {Backend_mask}
root {Root_path}
! ########### UPSTREAM END ###########
```

A file carrying `server_name app.internal.local` produces:

```json
{
  "web01": {
    "UPSTREAM": [
      ["value-mistach", {
        "expected": "server_name {Server_name}",
        "actual": "server_name app.internal.local",
        "explanations": [
          "app.internal.local for {Server_name} mismatches the format; unfortunately there is no known valid value for it"
        ],
        "line": 5
      }]
    ]
  }
}
```

Note what is being checked. `app.internal.local` is a perfectly well-formed
hostname; it is wrong only against *this* schema's `hostname` type. Equally,
`upstream backup` is verified to be exactly one address past `upstream backend`,
which no amount of regex checking would catch.

The full schema and both configs live in
[`tests/test_schema_generality.py`](./tests/test_schema_generality.py), where
they run on every test invocation, so this example cannot quietly stop working.

## Running it standalone

```
python main.py
```

It lists the golden configs in `examples/golden/`, asks for one by name, and
compares it against the same-named file in `examples/user/`. Given a name it
cannot find, it falls back to a built-in pair rather than failing.

The four bundled pairs run from a 3-line minimal case to a 73-line
production-shaped config, and are described in
[`examples/README.md`](./examples/README.md). To use your own, drop matching
filenames into `examples/golden/` and `examples/user/`.

Results: a JSON report printed to the terminal, and a table written to `out.csv`
in the repository root.

## Using it as a library

```python
from conftee.models.config_compare import ConfigCompare
from conftee.models.extract import Extract
from conftee.models.outline import Outline
from conftee.models.gen_summary import GenSummary
from conftee.utils.read_config import ReadConfig
from conftee.utils import schema as schema_module

schema = schema_module.load("./conftee/schemas/cisco-campus.yaml")

golden = ReadConfig.read_config_from_txt("./examples/golden/test_file_one_section_bad.txt")
user = ReadConfig.read_config_from_txt("./examples/user/test_file_one_section_bad.txt")

extract_golden, extract_user = Extract._extract_structs(golden, user)
outline_golden = Outline(golden, extract_golden, True)
outline_user = Outline(user, extract_user, False)

comparer = ConfigCompare(
    (extract_golden, extract_user),
    (outline_golden, outline_user),
    schema,
)
results = comparer.calculate_diff()

summary, diff_result_df, json_report = GenSummary(schema).generate_reports(
    outline_golden, outline_user, results
)
print(json_report)

# summary is a list of [count, label] pairs; the first is value mismatches.
for count, label in summary:
    print(f"{count} {label}")
```

That pair is deliberately non-conforming, so it reports `2 value mismatches`. In
a gate, assert on the counts you care about:

```python
assert summary[0][0] == 0, f"Expected 0 {summary[0][1]}, but got {summary[0][0]}"
```

Both `ConfigCompare` and `GenSummary` take the schema. `schema_module.loads()`
accepts the YAML as a string instead of a path.

`calculate_diff()` also accepts `infra_prefixes`, a list of address prefixes to
treat as infrastructure rather than user space when checking pool membership.

The user side does not have to come from a file.
`ReadConfig.read_config_from_response()` takes a `dict[str, list[str]]` of device
name to config lines, as returned by an API, and converts it to the same internal
form by synthesizing the device title lines.

`generate_reports` returns three views of one result: `summary` (counts by
category), `diff_result_df` (a pandas DataFrame, one row per line, carrying the
per-line diff opcodes, the variables found, and their bound values), and
`json_report` (the nested device/section structure shown above).

## Project history

Built for a university network operations simulation project, since retired, and
published here in a generalized, sanitized form.

| Period | What happened |
|---|---|
| Aug 2023 - Dec 2023 | **v1** by a previous student developer. Not in this repository; see [docs/v1-retrospective.md](./docs/v1-retrospective.md) for its architecture and the lessons taken from it. |
| Apr 2024 - Jul 2024 | **v2**, the code here: a full rewrite into the layered design in [docs/architecture.md](./docs/architecture.md). |
| (undated) | Retired from production use; no longer deployed anywhere. |
| Sep 2026 | Repurposing for public release: predecessor code removed, identifying sample data replaced, regression tests added, vocabulary moved from hardcoded constants into a schema. See [docs/repurposing-plan.md](./docs/repurposing-plan.md). |

The version number (0.1.5) dates from the original development. The initial
commit is when this repository was created for publication; it says nothing
about how long the tool took to write.

***

#### Addendum A: Development setup

From the repository root:

```
python -m venv .venv
.venv\Scripts\activate.bat          # Windows cmd; use activate.ps1 in PowerShell,
                                     # or source .venv/bin/activate on Linux/macOS
python -m pip install -r requirements.txt
```

Dependencies are declared as lower bounds rather than exact pins, so the install
picks wheels built for whichever Python you are on. Pinning exact versions ties
the project to the interpreter versions current when those versions shipped.

**On pandas.** It is a real dependency of the current code: `differ_o`,
`section_comparer`, `gen_summary` and `config_compare` all build and read
DataFrames, so installing without it will not work. But that is a design choice,
not a requirement of the problem. The DataFrame is the intermediate structure
passed between those modules, and the source of readable output such as
`out.csv`. What it is *not* used for is anything pandas is actually good at:
there are no joins, group-bys or vectorized numerics in the pipeline, and every
`.apply` is a row-wise Python lambda, which is a loop by another name. Any
similarly shaped record structure plus hand-written access logic would produce
identical results. Swapping it out is a contained refactor of those four
modules, not a redesign.

#### Addendum B: Running the tests

From that environment, add pytest and run it:

```
python -m pip install pytest
python -m pytest
```

Prefer `python -m pip` and `python -m pytest` over bare `pip` and `pytest`. The
`-m` form resolves through the interpreter you are actually running, so it cannot
silently act on a different Python than the one you intend.

The package does not need to be installed first. `pyproject.toml` sets
`pythonpath = ["."]`, which puts the repository root on `sys.path` so
`import conftee` resolves during development.

The suites answer different questions.

`tests/test_regression.py` runs all 63 golden/user config pairs through the full
pipeline and compares the result against recorded summary counts and report
hashes in `tests/fixtures/baseline.json`. The corpus spans two roots: four pairs
sit in `examples/` as documentation and the rest in `tests/fixtures/corpus/`. The
baseline was generated from the engine's own output, so these tests assert that
behavior has not *changed*, not that it is correct. A failure means something
shifted; investigate the change rather than regenerating the baseline.

The same file holds `test_no_identifying_strings`, which walks the sample
configs, `resources/` and `docs/` for identifiers removed when this repository
was published. It stores them as salted hashes rather than plaintext, so the
check runs without the names being present, and `test_guard_itself_works`
brute-forces a sample to prove the check actually fires.

`tests/test_schema_generality.py` runs the foreign vocabulary described above.

Useful variations:

```
python -m pytest tests/test_regression.py   # one suite
python -m pytest -k schema                  # tests matching a name
python -m pytest -x                         # stop at the first failure
python -m pytest -q                         # one line per file instead of per test
```
