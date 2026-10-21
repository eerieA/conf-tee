# Repurposing Plan

**Status:** in progress
**Repurposing started:** 2026-09-11
**Last updated:** 2026-10-17

**Prior history:** v1 Aug 2023 – Dec 2023 (previous developer, not included here);
v2 Apr 2024 – Jul 2024 (the code in this repository); retired from production some
time after. The dates in this document from 2026 onward refer to the repurposing
effort only.

This document is the working plan for turning this retired, organization-specific
tool into something a stranger can use. It exists so the plan survives
interruptions: if work stops for weeks, this file should be enough to pick it
back up without re-deriving the reasoning.

---

## 1. Why do this at all

The tool was built for one university network team, was retired when that team
stopped using it, and has no current users.

**The goal is not wide adoption.** It is, in the author's words, to commemorate a
past piece of work while hoping a couple of people find it useful. Adoption
beyond that is upside, not the success criterion. So polish that serves the
artifact is in scope; speculative feature work is not.

### What the tool actually is

Read past the network-specific naming and it is a **template-conformance checker
with a value-inference engine**:

- The "golden" config is a template with `{Variable}` holes.
- A real config is aligned against it, and each hole is *bound* to the value
  found there.
- Bound values are then validated: against a regex, for consistency across a
  section or file, for arithmetic relationships (`{{Vrfglue_prefix_1st_IP}+1}`),
  and for range/subnet membership.

This is the inverse of Jinja2: templates render *forward*, this extracts values
*back out* of rendered output and checks their relationships. That inverse
direction is what is worth generalizing.

### Framing for a general audience

> A reverse-template validator: given a template with typed, named holes and
> constraints between them, check whether a real text file conforms, and report
> which holes are wrong and why.

That covers Cisco configs, but also Kubernetes manifests, Terraform output,
nginx/systemd configs, CI YAML: anywhere files should share a shape with values
varying under rules.

### Why *not* the obvious optimization

The initial instinct was to replace `difflib` with a faster diff algorithm.
Deliberately rejected as the wrong first move. `difflib.Differ._fancy_replace`
is O(n·m) with per-pair ratio computation, but inputs are device configs of a few
hundred lines, and `Extract` segments files into blocks *before* diffing, so n and
m are small. Real runtime is well under a second.

The actual adoption blocker is that variable vocabulary and semantics are
hardcoded to one organization. Fix that first. Diff performance is optional
polish, and belongs last if at all.

---

## 2. Completed work

### Phase 0: cleanup and sanitization (done)

**v1 predecessor: analyzed, then deleted.**
The previous developer's version (~1900 lines, 5 modules, no classes) was
analyzed into [`v1-retrospective.md`](./v1-retrospective.md) and then removed.
Rationale: the *lesson* is the author's to keep; the *code* is someone else's to
not republish. The retrospective captures the architecture, data flow, five
concrete failure modes with evidence, a 10-item anti-pattern catalogue, and what
v1 got right that v2 kept.

**OpenAI structure-extractor: stripped.**
Removed `_openai_prerequisite`, `_make_prompt`, `_call_openai_api`,
`_parse_response`, `openai_extract_struct`, plus three helpers used only by that
path. `_extract_structs()` lost its `struct_parser` argument. Dropped 17
transitive dependencies, deleted `.env.json` files. Also attempted to re-save
`requirements.txt` as UTF-8, since UTF-16 breaks `pip install -r`. That did not
take: the file was committed still UTF-16LE, and was corrected during Phase 2.

**Sanitization: organization and person identifiers removed.**
Two rounds, ~1,500 occurrences across the corpus:

| Category | Now looks like |
|---|---|
| Organization domain | `example.net` |
| Building-derived device names | `site01-hub1`, `bldg03-sw11` |
| Uppercase building codes in VLAN names | `BLDE01`, `BLDC01` |
| Person-derived FW context names | `NOVA22`, `NOVA33` |
| Person-derived VRF names | `NOVA-LINK22`, `NOVA-WLAN31` |
| Firewall/ASA device names | `fw25-ctx` |

(The retired originals are deliberately not restated here; see the identifier
guard below. The replacement column is enough to recognize the convention.)

Replacements preserve the shapes that `WORD_TYPE_REGEXES` validates (e.g.
`FW_context_name` must stay `[A-Z]{4}\d{2}`), verified by dry-run before applying.

Also deleted: two ~120KB API captures containing a real person's name, username
and email; the stale `dist/` wheels (built from pre-sanitization code); and the
class-diagram JPG (superseded by [`architecture.md`](./architecture.md)).

**Gotcha worth remembering:** `\b` does not match between `_` and a letter, since
`_` is a word character. The first rule set therefore silently left compound
identifiers like `VRF_<name>_Subnets` completely unchanged, and half-renamed
others like `<name>_access_in`, replacing the first component but leaving the
second. Fixed with explicit lookarounds treating `_` as a boundary. The lesson
generalizes: when sanitizing, dry-run the rules against real samples and assert
on the *output*, rather than trusting `\b` to mean what it looks like it means.

**Regression baseline and test suite.**
`tests/fixtures/baseline.json` records summary counts and JSON-report hashes for
all 63 corpus pairs. `tests/test_regression.py` enforces them: 129 tests, ~5s.

Sanitization produced zero behavioral drift: aggregate stayed exactly
`[45, 20, 12, 316, 95]` (value mismatches, struct mismatches, inconsistencies,
missing/extra lines, command mismatches) before and after renaming.

> **Note on the baseline:** it records what the engine *does*, not what is
> *correct*. The corpus was written by the original supervisor to contain
> deliberate bad files, bad snippets and typos, so non-zero findings are expected
> and the numbers are plausible. But these tests protect against regressions, not
> against pre-existing bugs. If a report changes during the schema refactor, that
> is a regression to investigate, **not** a baseline to regenerate.

**Identifier guard.**
`test_no_identifying_strings` fails if any retired identifier reappears. Tokens
are stored as salted SHA-256 digests rather than plaintext, so retiring names
from the data does not mean republishing them in the test file. Matching is
word-based (whole word, plus 4-char prefix), which also avoids a false positive
where one retired building code appeared as a substring of an ordinary English
word used throughout these docs.

*Honest limitation:* these are 16-hex-char digests of short words with the salt
in the same file. Brute-forcible: the accompanying `test_guard_itself_works`
does exactly that to build its probe. It is courtesy toward a former colleague,
not a security control.

---

## 3. Remaining work

### Phase 1: pre-push fixes (done)

Blocking the first push to a remote. The push is the irreversible step: once
content reaches a public remote, it stays reachable in forks and caches even
after a force-push. The repo had no commits beforehand, so the first commit
contains only sanitized content, with no history to scrub.

- [x] **Renamed the project to `conf-tee`** (package `conftee`), a nod to the
      `conf t` shorthand every Cisco operator has typed. The previous name
      promised a diff tool, which is the wrong expectation. See §1.
      Also fixed along the way: `__init_.py` had a single trailing underscore so
      it was never a package marker, and the subpackages had no `__init__.py` at
      all. The package worked only via implicit namespace packages.
- [x] **Added a `LICENSE` file.** MIT, copyright `eerieA`, with a paragraph
      noting the project is a rewrite of a university co-op tool whose
      predecessor code is not included here.
- [x] **Fixed authorship metadata** and the package description (was "diff
      check", which reinforced the wrong framing).
- [x] **Set git identity.**
- [x] **Added a remote and pushed.** `origin` is a private GitHub repo; two
      commits so far. Reviewed as rendered there before any public flip.
- [x] *Optional:* `.gitattributes` with `* text=auto eol=lf` to avoid CRLF churn.
      Added after the first commits rather than before, so it needed a
      `--renormalize` pass. That pass staged nothing: every text file was already
      LF in the index, and only the working tree held CRLF, from `core.autocrlf`
      converting on checkout. The whole change is the one-line file.
- [x] Flip the remote to public once Phase 2 lands.

**Pre-flight checks passed** (re-run if the staged set changes):
169 files staged; no ignored-category files; 0 identifier hits scanning *staged
blob content*; no secrets, keys, JWTs or credentials; no file >100KB; tests pass
from a clean `git checkout-index` export.

> The guard salt in `tests/test_regression.py` still contains the old project
> name. That is deliberate; the reasoning is recorded alongside the salt itself.

### Phase 2: externalize the schema (the core work)

This is the change that makes the tool usable outside its original organization.

**The problem.** The engine infers semantics from variable *names* by string
matching, in five scattered places:

| Inference | Where | How |
|---|---|---|
| Family membership | `models/constants_singleton.py` | name-prefix match + union-find |
| "is a netmask" | `utils/diff_helpers.py:432` | `"netmask" in var` |
| VLAN pool check | `utils/diff_helpers.py:370` | `if var == "Vlan_ID_user"` |
| Arithmetic kind | `models/section_comparer.py:55` | membership in `IPV4_VARIABLES` / `INT_VARIABLES` |
| Consistency scope | `utils/diff_helpers.py:22` | computed by *subtraction* from the regex dict |
| IP pool membership | `utils/diff_helpers.py:360`, `:365` | membership in `IPV4_VARIABLES_USER` / `IPV4_VARIABLES_INFRA` |
| Value binding by type | `models/line_analyzer.py:290` | membership in `IPV4_VARIABLES` |

`ConstantsSingleton` + `DisjointSet` exist purely to *recover* at runtime which
variables form a subnet family (`Vrfglue_prefix`, `Vrfglue_prefix_1st_IP`,
`Vrfglue_prefix_netmask` → one family) from their shared name prefix. That means
a user must *name* variables in a magic convention to get correct behavior.

**The fix.** Declare all of it explicitly in a user-supplied YAML schema. Format
decision: **YAML** over JSON, because the file is meant to be hand-edited and comments
carry most of its documentation value. Costs one `pyyaml` dependency, accepted.

Schema sections (v1):

1. `syntax`: variable delimiters and block/section regexes (currently hardcoded
   in `extract.py` / `section.py`), so non-Cisco users can describe their own
   markers.
2. `types`: reusable value kinds carrying both regex and arithmetic engine.
   Replaces the `IPV4_VARIABLES` / `INT_VARIABLES` membership lists, and makes
   "variable in neither list" unrepresentable rather than a runtime error.
3. `variables`: the user's vocabulary. `scope: section|file|none` replaces the
   subtract-to-compute `VAR_CONS_*` lists. `role: netmask` replaces the
   `"netmask" in var` substring test.
4. `groups`: the change that does most of the work. Explicit family membership replaces the
   DisjointSet inference, freeing users from the naming convention.
5. `pools`: named IP/integer ranges, replacing hardcoded pool constants.

**Which constants file the schema is built from.** There are three:
`constants.py` (local development), `constants.api.py` (byte-identical to it,
kept so integration testing could mutate it independently), and
`constants.desired.py` (the client's intended production values). The schema is
transcribed from `constants.py`, for two reasons: it is what
`tests/fixtures/baseline.json` was generated against, so any other choice starts
Phase 2 by breaking its own regression net; and `constants.desired.py` carries
known regex errors, two of which are annotated inline in `constants.py` itself
(the `int_#` pattern, and `net_type_6_Vlan_name` missing escapes). The other two
files have no importer anywhere in the package, so they are deleted as part of
this phase rather than reconciled.

**Pools are in scope, and cannot simply be dropped.** `TEMP_UPLINK_PREFIXES`
(`diff_helpers.py:31`) and `get_legit_ip_pools()` / `get_legit_vlan_pools()`
(`helpers.py:161`, `:176`) all hold values belonging to the original
organization. The uplink prefixes are already overridable: `calculate_diff()`
takes an `infra_prefixes` argument and falls back to the constant only when the
caller passes nothing, which is what the corpus does. The two pool helpers are
not overridable at all, and return ranges (`10.45.0.0/16`, VLANs 1 to 4096) wide
enough that the checks they feed rarely fire. Deleting them would therefore look
behavior-neutral while actually removing a check. They become the `pools` schema
section, and absent pools must mean "do not check", not "check against a
built-in default". Note also that `INFRA_VLAN_POOL` / `USER_VLAN_POOL` are
computed at import time (`diff_helpers.py:39`), so this is module-level state a
threaded schema object has to displace.

**Latent bugs the transcription surfaced.** Preserved as-is through the
migration, because the equivalence test's job was to prove the schema matched
then-current behavior, bugs included. All three are now fixed, as a separate and
deliberate change made after the migration was proven faithful. The two
deviations from the constants are marked in `tests/test_schema_equivalence.py`
as named exceptions, so that file still pins everything else:

- `Vlan_ID_vpnglue` was absent from `INT_VARIABLES` while its three siblings
  (`Vlan_ID_fwglue`, `Vlan_ID_vrfglue`, `Vlan_ID_user`) were present, despite
  sharing their regex. Writing `{{Vlan_ID_vpnglue}+1}` therefore raised
  `ValueError` from `_evaluate_expression` rather than evaluating. No corpus file
  uses a VLAN in an expression, so nothing caught it. The schema first encoded
  this as a distinct `vlan_id_no_arithmetic` type to make the anomaly visible;
  the fix points the variable at `vlan_id` and drops that type, now unreferenced.
- `netmask_29` and `wildcard_29` carried `arithmetic: ipv4` despite being fixed
  literals (`255.255.255.248`, `0.0.0.7`) that nothing computes on. The
  declaration is now dropped from both.
- Fixing the one above exposed a third bug that it had been masking.
  `gather_variables` decides whether a golden line contains an IPv4 variable by
  testing `var[1:-1]`, which works for a plain `{name}` but not for an
  expression `{{name}-2}`, where it leaves `{name}-2` and never matches. So
  expression variables never set `has_ipv4_g`, and the flag was only true on
  those lines because a netmask variable sat beside them wearing the wrong
  arithmetic. The fix matches `VARIABLE_REGEX` inside the token, covering both
  forms.

  The two interact, so they had to be fixed together: dropping the arithmetic
  alone turned the flag off on six golden lines, changing how `SequenceMatcher`
  aligns them. Fixed as a pair, the flag is restored on those six and newly
  turned on for 8 lines across the corpus where an expression sits beside a
  hardcoded mask rather than a variable one, which is bug three having been live
  and undetected there. Every flip is in the safe direction (off to on), and all
  63 reports are byte-identical, so the extra masking changes alignment without
  changing any verdict.

**Residual org-coupling the new tests surfaced.** Both were invisible to the
suite as it stood, because every test loaded `cisco-campus.yaml`, which is the
one schema that cannot expose them. Each is now pinned by exactly one test:
reverting either fix fails that test and nothing else.

- Optional sections (`pools:`, `groups:`) written as a list escaped as a bare
  `AttributeError` with no path, while every neighbouring mistake produced a
  clean `SchemaError`. They were reached by `.get()` rather than by the helper
  that type-checks the mandatory sections. A `_optional_section` helper now
  gives all four sections identical treatment.
- `_value_is_in_pool` looked its finding label up in a hardcoded table keyed on
  the bundled schema's four pool names, so any schema naming a pool anything
  else raised `KeyError` the moment a value fell outside it. The label is now
  derived from the pool's own name, which reproduces all four original strings
  exactly, leaving reports unchanged.

**The limit of generality today: vocabulary yes, dialect no.** The engine reads
every vocabulary question from the schema (regexes, arithmetic, scopes, netmask
roles, groups, pools; 10 call sites). It reads no syntax question from it:
`extract.py`, `section.py`, `line_analyzer.py` and `section_comparer.py` match
against their own module-level regexes across 11 call sites, and `schema.syntax`
is parsed, validated, and then never consulted by anything but the equivalence
test. So a foreign vocabulary works today and a foreign block syntax does not.
`tests/test_schema_generality.py` is scoped to the half that works and says so,
rather than quietly asserting less than its name implies.

A related limit, recorded as a test rather than fixed: a variable must be its
own whitespace-delimited token. Words are split on whitespace and a word counts
as a variable slot only when the variable regex matches the whole of it, so
nginx's `listen {Listen_port};` leaves the variable embedded in a longer token
and the line compares as literal text. Supporting such dialects means matching
variables inside a word rather than across the whole of it.

**Environment faults found while setting the suite up to run.** None are schema
work; they were blocking anyone from running the tests at all, so they were fixed
first:

- `requirements.txt` was still UTF-16LE despite Phase 0 recording it as re-saved
  UTF-8, which makes `pip install -r` fail outright.
- The test suite only ran under `python -m pytest`, which puts the working
  directory on `sys.path`, and failed under a bare `pytest`, which does not. The
  package is not installed during development, so `import conftee` had nothing to
  resolve against. Fixed with `pythonpath = ["."]` in a new
  `[tool.pytest.ini_options]` section. Worth noting because the two invocations
  look interchangeable and the failure blames the test module rather than the
  path.
- Every dependency was an exact `==` pin, which made
  `pip install -r requirements.txt` fail on Python 3.14: `pandas==2.1.4` has no
  wheel for it, so pip fell back to compiling from source and the Cython build
  failed, aborting the whole file. Relaxed to lower bounds in both
  `requirements.txt` and `pyproject.toml`, and verified by building a fresh venv
  and running the suite against the newest resolve (pandas 3.0.5, numpy 2.5.3,
  colored 2.3.2), with the full suite passing. The pandas notes were also
  reworded, since
  "does not strictly need pandas" read as "not imported" when the intended
  meaning was "replaceable with a hand-rolled record structure". See the
  Environment section of `README.md`, which owns that explanation.

`links` (cross-variable equality conditioned on section) was cut from v1,
because it existed for a single `LNK_RELATIONS` entry. Revisit later as a general
`constraints` system (`a == b`, `a < b`, `a in subnet(b)`) if anyone needs it.

Draft sketch lives in the session scratchpad; reconstruct from this section if
lost. The five sections above are the substance.

**Steps:**

Ordered so that transcription errors surface before any behavior can move. The
first three steps add code without changing what runs, so a mistake in the
56-regex transcription is caught by a direct comparison rather than debugged
later through a shifted report.

Threading the schema through the engine is then split into one step per module,
so a regression points at a single module rather than at three converted at once.
The schema is passed explicitly as a constructor or function argument, never read
from a module-level global; see §4 for why. It still *flows* top-down at runtime,
entry point to `SectionComparer` to `LineAnalyzer`, as the constants do today.
The modules are converted leaves-first, which is the opposite order, so that each
one's dependents are still stable while it changes.

During those steps the schema argument was optional, defaulting to the bundled
`cisco-campus.yaml`, because a required argument would have broken all five
construction sites at once and collapsed them back into one. The default was
scaffolding, and the step that makes the argument required was its removal
trigger: while it existed there were two code paths, and leaving it in place would
have amounted to the global this design rejected. It has since been deleted, so
omitting a schema is now a `TypeError` at every seam rather than a silent fallback.

- [x] `schema.py`: parse and validate YAML into internal structures, with clear
      errors for malformed schemas. Cross-references (variable to type, group
      member to variable, variable to pool) are resolved at load time, so a
      schema that loads is known to be internally consistent.
- [x] `schemas/cisco-campus.yaml`: `constants.py` expressed in the new format.
      (Renamed from the original org-specific name.) Generated from the constants
      rather than hand-transcribed. 50 variables collapse to 22 named types,
      since most of the regex dict was the same IPv4 pattern repeated.
- [x] Equivalence test: `tests/test_schema_equivalence.py`, 61 tests, asserting
      the loaded schema reproduces today's constants exactly. Regex per variable,
      `IPV4_*` / `INT_VARIABLES` membership in both directions, computed
      `VAR_CONS_*` scopes, `ConstantsSingleton` clusters, pool assignments, and
      the syntax regexes hardcoded across `extract.py`, `section.py`,
      `line_analyzer.py` and `section_comparer.py`. Verified by mutation: seven
      classes of deliberate schema corruption each fail it.
- [x] `LineAnalyzer`: replace `WORD_TYPE_REGEXES` lookups (`:39`, `:426`) and the
      `IPV4_VARIABLES` membership test (`:290`) with `regex_for` and
      `variables_with_arithmetic`. Smallest of the three, so the seam's shape is
      settled here before it is repeated.
- [x] `SectionComparer`: arithmetic kind by type rather than by
      `IPV4_VARIABLES` / `INT_VARIABLES` membership (`:55`).
- [x] `diff_helpers`: the awkward one, and last for that reason. Beyond threading,
      it has module-level state that no argument can displace: `VAR_CONS_FILE` is
      computed by subtraction at import time (`:22`-`:24`), and the VLAN pools at
      `:39`. The subtraction becomes `variables_with_scope`, which is a semantic
      change rather than a reroute, so it is isolated here with the other two
      modules already converted and passing.
- [x] Make the schema argument required and delete the default, once every caller
      passes one explicitly. `GenSummary` gained a constructor to hold the schema,
      as `ConfigCompare` already did; `main.py` and the regression test now load
      `cisco-campus.yaml` and pass it in, so the choice of vocabulary is made at the
      entry point rather than defaulted to deep in the engine.
- [x] Move pools into the schema, with absent pools meaning "do not check".
      Retired `get_legit_ip_pools()` and `get_legit_vlan_pools()`, whose ranges
      now live as test data in the equivalence test. `_value_is_in_pool` reads
      `pool_for` and lost its section-conditional VLAN branch: that branch chose
      between two pools holding the identical range, so it could not change a
      verdict, and expressing it would have meant a per-section pool construct
      built for a distinction nothing makes. `TEMP_UPLINK_PREFIXES` was not pool
      data at all, so it moved rather than retired: it supplies correct values for
      four infra prefix variables and describes the sample corpus, so it now lives
      in `examples/sample_corpus.py` and both entry points pass it explicitly. The
      silent fallback is gone, matching the schema argument above.
- [x] `_value_is_wrong_sourced`: subnet membership now comes from
      `schema.group_of` rather than `ConstantsSingleton` clusters and
      `SUBNET_CLUSTERS`, and `schema.is_netmask` replaces the `"netmask" in var`
      substring test, in both the member scan and the mask lookup. The finding
      type is built from the group's name, so it follows the schema rather than a
      recovered cluster name. This was the prerequisite the list previously
      omitted: the function was the last reader of `ConstantsSingleton`, which is
      now unimported anywhere in the package. The clusters assertion in the
      equivalence test became inline data at the same time, as the scope lists and
      pool ranges did, so it compares the schema against the old behavior instead
      of against itself.

      Worth recording, because it looks like a regression and is not: the schema
      lists group members alphabetically, while the union-find produced them in
      `WORD_TYPE_REGEXES` order. The member scan stops at the first member whose
      correct value is a pool-legal IPv4 address and treats it as the subnet base,
      so the two orders pick a different address on 286 of 420 in-group calls
      across the corpus (`user_prefix` starts at `User_prefix`, the network
      address, under the old order and at `User_Prefix_last_IP`, a host inside it,
      under the new one). Every report is nonetheless byte-identical, because
      `calc_ipv4_range` masks the base down to the network: any host in the subnet
      yields the same range. Order is therefore not part of the contract, and the
      equivalence test compares membership as sets to say so.
- [x] Delete `models/constants_singleton.py` (`ConstantsSingleton`, `DisjointSet`,
      `determine_cluster`) and the scattered string-inference tests. The item
      above removed its last reader, so this was a straight deletion.
- [x] Delete `utils/constants.api.py` and `utils/constants.desired.py`, which
      have no importer. `constants.api.py` was byte-identical to `constants.py`,
      so nothing was lost with it. `constants.desired.py` was not: it held the
      client's intended production regexes, differing in six patterns, of which
      only two (`int_#` and `net_type_6_Vlan_name`) are annotated inline in
      `constants.py`. The other four (`VRF_name`, `FW_context_name`,
      `IP_local_pool_name`, and the extra `test_int_#`) differ because
      `constants.py` deliberately loosened them for test fixtures rather than
      because the client was wrong. Deleting the file was chosen deliberately
      over recording that diff: the values are reachable in git history, and the
      schema's transcription source is already settled above.
- [x] Decide what remains of `utils/constants.py`. Decision: keep the file, split
      it in the docstring, delete nothing yet. The contents fall into three
      groups, and only the first is the engine's own. `GENERAL_IPV4_REGEX`,
      `GENERAL_CIDR_MASK_REGEX` and `BLOCK_TYPE_*` (8 of 118 lines) are read by
      seven modules and describe how a value or block is *written* rather than
      what a network calls things. They are syntax-level and structural rather
      than vocabulary, so they are user-independent and stay.
      `WORD_TYPE_REGEXES`, `IPV4_VARIABLES*` and `INT_VARIABLES` are vocabulary
      the schema has fully replaced; no engine module reads them, but
      `tests/test_schema_equivalence.py` does, and deleting them would gut the
      test whose job is pinning the schema against them. They retire together
      with that test, once the regression suite is the sole pin; scheduled as
      Phase 3a. `SUBNET_CLUSTERS`
      has no reader at all, kept only as the source the test's subnet families
      were derived from. The module docstring now records this split, replacing a
      header that described the file as being for API integration tests and
      pointed at the now-deleted `constants.desired.py`.
- [x] Verify the suite still passes. Unchanged reports prove the migration was
      faithful. 190 pass: the 129 this item was written against are
      `tests/test_regression.py`, joined since by 61 in
      `tests/test_schema_equivalence.py`. Four checks, because the suite alone
      does not cover all of it: `tests/fixtures/baseline.json` is untouched, so
      all 63 report SHAs are byte-identical; every module in the package imports
      cleanly, which the suite would not catch on an untested path; no engine
      module or entry point references the retired vocabulary constants; and all
      63 corpus pairs run end to end through the real pipeline.

### Phase 3: make it presentable

Ordered so that files move before anything cites them. The README is the most
valuable item here and the obvious one to reach for first, but it will reference
example configs by path, and the reorganization below changes those paths. The
corpus item already carries a note about not moving files twice; writing their
paths twice has the same cost, so the moves come first and the prose follows.

- [x] **Reorganize the corpus** into a few representative pairs in `examples/`
      as user-facing documentation, the rest in `tests/fixtures/corpus/`.
      *(Deferred from Phase 0 to avoid moving files twice.)*
      Done: 4 pairs in `examples/{golden,user}/`, 59 plus 3 unpaired strays in
      `tests/fixtures/corpus/{golden,user}/`. `sample_corpus.py` moved to
      `examples/`, out of the shipped package, which settles the half of the
      packaging item below that concerned it. `examples/__init__.py` makes it
      importable; the repo root is already on `sys.path` via `pythonpath`.
      Verified: 254 tests pass, `tests/fixtures/baseline.json` byte-identical,
      all 63 report SHAs unchanged on a full end-to-end run, package import walk
      clean, and `main.py` runs against the new layout.

      Two roots, not one, and the harness spans them. `tests/fixtures/baseline.json`
      keys are bare filenames, so a pair is now located by searching the roots
      rather than by joining onto a single golden and user directory. The
      alternative, copying the four example pairs so each root is
      self-contained, was rejected: eight duplicated files that drift silently
      and leave a reader unable to tell which copy is authoritative. A new
      `test_corpus_roots_are_disjoint` enforces the uniqueness the lookup
      assumes.

      The four examples were chosen from the baseline rather than by eye, as a
      ladder: 3 lines with a single finding, 12 lines covering four finding
      kinds, 73 lines of real production-shaped config that fully conforms, and
      49 lines exercising every category including structural mismatches.
      `examples/README.md` describes them in that order.

      `test_no_identifying_strings` needed widening, not just repointing. It
      listed one directory level, and the corpus now sits one level below its
      root, so a flat listing would have scanned the example README and none of
      the configs. It now walks recursively and covers 141 files, up from the
      129 corpus files it reached before. This guard matters more now the repo
      is public, so it is worth noting that the move could have silently
      hollowed it out.
- [x] **Verify packaging.** Done. Contents were already right: the wheel ships
      `conftee/` with `schemas/cisco-campus.yaml` and the html templates, and no
      corpus file, `sample_corpus.py`, test or `main.py`. The predicted problem
      did not exist. Poetry's `packages = [{ include = "conftee" }]` takes the
      whole package directory, not just `*.py`, so no explicit include rule was
      needed for the schema.

      Three real defects showed up instead, none of them about file selection,
      and all found only by installing the wheel rather than listing it:

      1. **The wheel was uninstallable.** `[project].dependencies` listed
         `"python >= 3.9"`, which is an interpreter constraint written as if it
         were a package. It became `Requires-Dist: python (>=3.9)`, and pip
         failed with `No matching distribution found for python>=3.9`.
      2. **No runtime dependency shipped at all.** Poetry 2.x reads `[project]`
         in preference to `[tool.poetry]`, so the real list under
         `[tool.poetry.dependencies]` was ignored and the wheel declared none of
         colored, Mako, Jinja2, PyYAML or pandas. Installing it into a clean
         environment produced an immediately broken install.
      3. **The license was published as proprietary.** `license = {file = ...}`
         in `[project]` overrode `license = "MIT"` in `[tool.poetry]`, yielding
         `Classifier: License :: Other/Proprietary License` on an MIT project.
         The worst of the three for a public repo, since it contradicts
         `LICENSE` where a reader is least likely to look.

      All three had one cause: metadata duplicated across `[project]` and
      `[tool.poetry]`, where the `[project]` copy silently wins. The comment
      above `[project]` asserted the opposite, that the section "will not be
      read since currently built through poetry", which is how the duplicates
      went unnoticed. Fixed by making `[project]` the single source of truth and
      reducing `[tool.poetry]` to the `packages` build setting.

      Verify: build, install the wheel into a clean venv, and use it from
      outside the repository. That last step is what proves the shipped schema
      is loadable by path from the installed package rather than merely present
      in the archive.
- [x] **Rewrite `README.md`** around the reverse-template framing. Done. It
      opens on the inverse-of-Jinja2 framing and on the questions a diff cannot
      answer, which is the part worth generalizing, then gives the checks as a
      table. The old opening described the tool as comparing a config "against a
      manually defined standard format", which named the mechanism and not the
      capability.

      "What it does not do yet" is its own section, third, above installation,
      so the vocabulary-yes/dialect-no limit is visible before a reader invests
      any time. It also records the whitespace-token limit, since that one bites
      on the first realistic attempt at a foreign file.

      Two corrections fell out of writing it. The old integration example
      constructed `ConfigCompare(extractData, outlineData)` and `GenSummary()`
      with no schema, which both now require: the documented example could not
      have run since Phase 2. And it carried a disclaimer that it "might not
      actually work", which is now unnecessary, because the replacement is
      executed verbatim out of the README as part of verifying this item.
      The old sample also asserted zero mismatches against a deliberately
      non-conforming pair, so a reader copying it would have hit an
      AssertionError; it now prints the counts and shows the assertion form
      separately.
- [x] **Add a worked non-Cisco example.** Done, merged into the README as
      predicted. It is the web-server vocabulary from
      `tests/test_schema_generality.py`, with the schema fragment, the template,
      and a real failing report produced by running it rather than written by
      hand. The README points at the test as the source, so the example is
      covered by the suite and cannot quietly stop working.

      The report shown is a `hostname` type rejecting `app.internal.local`, a
      well-formed hostname that is wrong only against that schema. That makes
      the point the framing rests on better than a malformed value would: the
      tool is checking conformance to a declared vocabulary, not validity in
      general.
- [x] Unpin over-specific dependency versions. Done ahead of schedule during
      Phase 2, because the exact `==` pins were blocking the test suite from
      installing at all; see the environment faults noted there.
- [x] **Remove the three unpaired corpus strays.** Done, deleted rather than
      paired. Both `.json` files are API-response shaped, a `results` list
      wrapping a device-to-lines dict, which is the format
      `read_config_from_response` takes; pairing them would have meant
      reviving the removed API path to generate a golden side for fixtures
      nothing asks for.

      Each precondition was rechecked rather than taken from this entry before
      deleting: no `.py`, `.json`, `.md` or `.toml` file outside this plan names
      any of the three, and none of the 63 baseline keys matches them. After
      deletion the corpus is symmetric, 59 and 59 under `tests/fixtures/corpus/`
      and 4 and 4 under `examples/`, and `baseline.json` is untouched.
      The suite still passes 254 tests and the identifier guard drops from 141
      files to 138, which is the expected three and confirms it was scanning
      them.
- [x] **Update `docs/architecture.md`.** Done. The whole
      "Configuration / constants (being replaced)" section described code that
      no longer exists: `models/constants_singleton.py` and its `DisjointSet`
      are gone, and the seven-row table of name-based inferences listed line
      numbers for tests the engine no longer makes.

      Replaced with a "The schema" section showing the real current shape: the
      caller loads a YAML schema, `ConfigCompare` and `GenSummary` take it as a
      constructor argument, and the checks reach it through seven accessors
      (`regex_for`, `arithmetic_for`, `variables_with_arithmetic`,
      `variables_with_scope`, `is_netmask`, `group_of`, `pool_for`), across 11
      call sites. The inference table was kept but turned into a
      formerly/now mapping, since what each row replaced is the useful part and
      the old line numbers were not.

      Added a subsection for the dialect limit, so the architecture doc states
      it where someone reading the design will meet it: `syntax:` is validated
      and then unread, and block recognition still comes from eight
      module-level patterns across `extract.py` (2), `section.py` (3),
      `line_analyzer.py` (2) and `section_comparer.py` (1).

      The pipeline diagram was checked rather than assumed stale: all 23 methods
      it names still exist, so it was left alone apart from showing the schema
      entering at `ConfigCompare`. One unrelated correction: the header pointed
      at `resources/class_diagram.jpg`, which is no longer in the repository.

### Phase 3a: retire dead code

Separate from the items above because it is cleanup rather than presentation,
and because it is deliberately sequenced after them. Two kinds of dead code,
retired together because the commits are independent and small: scaffolding
this migration put up and is now done with, and features that were already
dead when the repository was published.

- [x] Retire `tests/test_schema_equivalence.py` together with the vocabulary
      half of `conftee/utils/constants.py` (`WORD_TYPE_REGEXES`,
      `IPV4_VARIABLES*`, `INT_VARIABLES`, `SUBNET_CLUSTERS`), as one commit.
      Done. `constants.py` went from 140 lines to 14, the three surviving
      definitions byte-identical. 194 tests pass, down from 254 by the 61
      retired and up by the one carried over; `tests/fixtures/baseline.json`
      is untouched, so all 63 report SHAs are unchanged.

      One test was kept rather than retired. `test_syntax_regexes_match_hardcoded`
      was the only member of that file reading no vocabulary constant: it pins
      the bundled schema's eight `syntax:` regexes against the module-level
      patterns in `extract.py`, `section.py`, `line_analyzer.py` and
      `section_comparer.py`. It now lives at the bottom of
      `tests/test_schema_generality.py` as `test_bundled_syntax_matches_hardcoded`,
      which is the file whose docstring cited it by name. Keeping it matters
      because `syntax:` is validated and then unread, so drift between the two
      representations is otherwise silent.

      Six live files cited the retired test and were repointed, not left
      dangling: `cisco-campus.yaml` and `utils/schema.py` (now naming the
      regression corpus and the past tense respectively), `utils/diff_helpers.py`
      (the pool-range claim restated as a fact checkable in the schema, and
      re-verified: both `ipv4` pools are declared `10.45.0.0` `/16`),
      `tests/test_schema_validation.py` in two places, and
      `tests/test_schema_generality.py`. The `README.md` paragraph describing
      the file as scaffolding was removed, since its stated removal trigger
      just fired.
      They retire together or not at all: the constants have no engine reader
      left, and the test exists to pin the schema against them, so removing
      either alone leaves the other pointless. The syntax half of
      `constants.py` stays; it has real readers.
      Deferred until after the reorganization above, not before, because the
      test is the last remaining check that the Cisco schema's regexes still say
      what the working tool said, and Phase 3 moves the corpus and
      `sample_corpus.py` underneath it. Leaving it in place through that churn
      costs nothing and keeps a second opinion available while files move.

- [x] Retire the dead HTML output path. `_generate_html`
      (`conftee/models/gen_summary.py:651`) has a body that is entirely one
      commented-out string literal, and nothing calls it. Its own docstring
      says the HTML visualization "is currently broken and not in use because
      of both requirement changes and implementation changes". With it go
      `OUTPUT_DIR` and `JINJA_TEMPLATE_DIR` (`:44`, `:45`), whose only
      references are inside that commented block.

      The cluster is larger than the function, and the parts should go in one
      commit because each is dead only while the others are:

      - `conftee/html_templates/main_diff_check.html` and `styles.css`. Named
        nowhere but inside the dead block, and they currently ship in the wheel.
      - The `Jinja2` dependency. Not imported anywhere in the package: the
        `Environment` and `FileSystemLoader` calls at `:668` are commented out,
        and so is the `pathlib` use at `:666`, which no live import even
        satisfies.
      - The `Mako` dependency, and `replace_device_titles_in_golden`
        (`conftee/utils/helpers.py:186`), which is its only user and is itself
        uncalled. It is a separate feature from the HTML output but has the
        same status and the same one-line fix.

      Confirmed rather than assumed: with `jinja2` and `mako` both made
      unimportable, the full suite still passes 254 tests. Two of the five
      declared runtime dependencies are therefore unused, which a reader
      installing the package pays for in install size and supply-chain surface.

      Deferred to this phase rather than done when it was spotted, because it
      is unrelated to the item that surfaced it: the generated artifact
      `conftee/html_output/main_diff_check_result.html` was untracked and
      ignored on its own, which was enough to stop it shipping. Removing live
      code is a larger change than fixing an ignore rule and belongs with the
      other retirements. Verify: suite passes, the wheel no longer carries
      `html_templates/`, and `Requires-Dist` lists three dependencies.

      Done, and all three verifications hold: 194 tests pass, the wheel carries
      no `html_templates/` entry, and `Requires-Dist` is exactly `PyYAML`,
      `colored` and `pandas`. `gen_summary.py` went from 688 lines to 645,
      `helpers.py` from 244 to 227. Checked further than the plan asked: the
      wheel was installed into a clean venv, where neither Jinja2 nor Mako is
      present, every module imported, and the README's own sample ran from
      outside the repo and printed the `2 value mismatches` the README promises.

      One correction to the entry above. It described the Mako use as having
      "the same one-line fix" as the Jinja2 one, but the two were not alike:
      `from mako.template import Template` was a live top-level import at
      `utils/helpers.py:2`, not a commented-out line, so Mako was genuinely
      required at import time until `replace_device_titles_in_golden` went with
      it. The Jinja2 references really were all inside the dead string literal.

      Two leftovers went too, both reachable only from the removed code: the
      now-empty `conftee/html_templates/` and `conftee/html_output/`
      directories, and with the latter the `.gitignore` rule added in
      `5c80208` to ignore what that renderer used to write.

      Noted, not acted on: `replace_device_titles_in_response`
      (`utils/helpers.py:173`) has no caller either. It is the surviving
      sibling of the function removed here and looks like the same kind of
      fixture helper, but it is pre-existing dead code rather than an orphan
      this change created, so it stays until someone decides on it.

### Phase 4: optional polish

Only if the earlier phases are done and the work still appeals.

- [ ] Diff performance: replace `difflib` with Myers or patience diff.
      *Interesting, but optimizes something nobody was waiting on.* Last, or never.
- [ ] Refactor Pandas out. The original README notes it is not strictly needed;
      it is used for readability and structure.
- [ ] Revisit `links` as a general constraints system.
- [ ] Complete the one unfinished client requirement: structural relational
      anomalies (e.g. inconsistent counts of downlink portchannels vs downlink
      device blocks).
- [ ] Make device title recognition configurable: `DEVICE_TITLE_LINE_REGEX`,
      `DEVICE_TITLE_REGEX` and `COMMON_TERMS` (`models/extract.py:11`, `:12`,
      `:13`). This is the syntax half of what the schema migration did for
      vocabulary, and the same argument applies: a user should not have to
      adopt one organization's conventions to get correct results.

      The two regexes and the word list are not in the same state, and the
      second is the one that matters.

      The regexes are already declared, in `syntax.blocks.device` of every
      schema, byte-identical to the constants and pinned by
      `test_bundled_syntax_matches_hardcoded`. So that part is wiring rather
      than design: read them from the schema instead of the module, and delete
      the pin once nothing is left to pin. The same is true of the six
      syntax constants in `section.py`, `line_analyzer.py` and
      `section_comparer.py`, which is why this is really one piece of work and
      not three.

      `COMMON_TERMS` has no schema representation at all, and it is not
      cosmetic. `_like_common_term` decides whether the first word of a device
      title is a hostname or a role word, by `SequenceMatcher` ratio against a
      16-entry list of English networking words with a 0.75 cutoff. The device
      name it yields reaches the comparison as `missing_device_names` and
      `extra_device_names`, so the word list can change a verdict. The failure
      is quiet and plausible: `~ switch01 Core Uplink ~`, `~ access2 Floor 3 ~`
      and `~ distribution-a Main ~` each lose their device name, because the
      hostname resembles a listed word closely enough to be read as a role.
      Those are ordinary hostnames, not contrived ones.

      The word list is also a symptom rather than the root. It exists to split
      a device title into name and role, which is a job that only makes sense
      because the top level is specifically a *device*. See the item below.

      *Worth recording, not worth doing yet.* Nobody has asked, and the tool
      works for anyone whose device titles look like the bundled dialect. But
      unlike the rest of Phase 4 this is a correctness limit rather than
      polish, so if a second dialect ever shows up this is the item that
      blocks it. See the dialect note in
      [architecture.md](./architecture.md) and the scoping statement in
      `tests/test_schema_generality.py`.
- [ ] Generalize the block hierarchy itself: two fixed levels named "device"
      and "section" become N levels of nested blocks. The current names are
      not just vocabulary, they are the structure, so this is the item the
      three constants above ultimately belong to.

      How deep the assumption goes, which is the reason to record it rather
      than attempt it casually:

      - `BLOCK_TYPE_DEVICE` / `BLOCK_TYPE_SECTION` are `"d"` and `"s"`, two
        values branched on with `if`/`elif` in `outline.py`,
        `struct_helpers.py` and `config_compare.py`.
      - `_build_hierarchy_from_struct` returns `dict[str, list[str]]`: one
        device maps to a flat list of sections. A third level has nowhere to
        go. The keys are composite strings built by `_hrch_key_format` as
        `f"{device}, {section}"`, which assumes exactly two components.
      - `Outline` keeps `self.sections` and `self.device_titles` as separate
        lists rather than a tree.
      - The error types are paired per level: `ERR_TYPE_MISSING_DEVICE` and
        `ERR_TYPE_MISSING_SECTION`, likewise for extras.
      - The JSON report names the levels in its own fields, including
        `missing_device_names` and `extra_device_names`, so changing the model
        is a breaking change to the output contract rather than an internal
        refactor.

      The natural shape is a recursive block with a declared level name, so a
      schema could describe device/section, or section/subsection, or any
      depth, and the engine would compare siblings at each level without
      knowing what the levels are called. `_like_common_term` disappears in
      that design: splitting a title into "name" and "role" is a device-shaped
      question, and a generic block has a title and children.

      *Recorded because it is the real ceiling, not because it should be done.*
      It touches every structural module, rewrites the report format, and the
      63-pair corpus pins the current output exactly, so the baseline would
      have to be regenerated and re-reviewed by hand rather than trusted. That
      is a rewrite with a user-visible format break, for a generality nobody
      has yet asked for. Worth doing only if a second dialect arrives and the
      configurable-title item above proves insufficient, which it would, for
      any config whose nesting is not two levels deep.

---

## 4. Decisions made, with reasoning

Recorded so they are not silently re-litigated later.

| Decision | Reasoning |
|---|---|
| Generalize the schema, not the diff algorithm | Org-coupling blocks adoption; performance does not. |
| Delete v1 after extracting analysis | Lesson is the author's; code is a predecessor's. |
| Keep all 63 corpus pairs, renamed | They are the only regression coverage; discarding them loses the safety net. |
| Rename identifiers rather than regenerate corpus | Renaming proved semantically transparent (zero drift); regeneration would risk losing the deliberate bad-file coverage. |
| YAML over JSON for schemas | Hand-edited file; comments carry the documentation. One dependency accepted. |
| Cut `links` from schema v1 | Bespoke construct serving one entry; a general constraints system is the better eventual answer. |
| Hash guard tokens rather than gitignore the test | A gitignored test never runs, so it stops being enforcement. Hashing addresses presentation without losing the guard. |
| Strip the OpenAI path entirely | Experimental, optional, added an API-key requirement and 17 dependencies to a tool that works without it. |
| Rename to `conf-tee` / `conftee` | The old name promised a diff tool, setting the wrong expectation for what this does. `conf-tee` keeps the networking origin story through shared muscle memory (`conf t`) while reading harmlessly to outsiders, and does not trap the tool in the networking niche. Renamed while the project had zero users, when lock-in was zero. |
| Build the schema from `constants.py`, not `constants.desired.py` | It is what the regression baseline pins, and the client's intended values carry known regex errors. |
| Make pools optional rather than deleting them | The hardcoded ranges are org-specific, but they feed real checks; a bare delete would remove a check while looking behavior-neutral. |
| Pass the schema explicitly, not via a module-level accessor | An accessor is one global slot, so two schemas in one process are impossible and the test suites share mutable state. It also keeps the import-time problem alive as "was the schema set before this ran?", which an argument makes unrepresentable. Costs a wider diff and a parameter threaded through callers that do not read it. |
| Keep the guard salt unchanged after the rename | It is an opaque constant; changing it would invalidate every digest. See the note in `tests/test_regression.py`. |

---

## 5. Honest assessment

Wide adoption is unlikely. Networking teams are conservative, and a generic
version competes with Batfish, NAPALM, Nornir, and Jinja2-render-then-diff
pipelines. Realistic expectation: few users, possibly none.

That is an accepted premise, not a problem to solve. A cleaned-up, generalized,
tested version is a substantially better artifact than an archived school tool.
Taking a 1121-line monolith and producing a layered, documented, importable
module is also hard to show on a resume. If the template-conformance niche turns
up a handful of users, that is upside.
