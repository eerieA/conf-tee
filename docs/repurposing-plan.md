# Repurposing Plan

**Status:** in progress
**Repurposing started:** 2026-09-11
**Last updated:** 2026-09-12

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
- [ ] *Optional:* `.gitattributes` with `* text=auto eol=lf` to avoid CRLF churn.
      Was easier before the first commit; still worth adding, now with a
      `--renormalize` pass.
- [ ] Flip the remote to public once Phase 2 lands.

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
  colored 2.3.2). The pandas notes were also reworded, since
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

- [ ] `schema.py`: parse and validate YAML into internal structures, with clear
      errors for malformed schemas.
- [ ] `schemas/cisco-campus.yaml`: `constants.py` expressed in the new format.
      (Renamed from the original org-specific name.)
- [ ] Equivalence test: assert the loaded schema reproduces today's constants
      exactly, before anything consumes it. Same regex dict, same `IPV4_*` and
      `INT_VARIABLES` membership, same computed `VAR_CONS_FILE`, same clusters as
      `ConstantsSingleton.get_clusters_dict()`. This is the gate for the steps
      below.
- [ ] Thread a schema object through `LineAnalyzer`, `SectionComparer`,
      `diff_helpers` in place of module-level constant imports. Includes the
      import-time pool computation at `diff_helpers.py:39`.
- [ ] Move pools into the schema, with absent pools meaning "do not check".
      Retire `TEMP_UPLINK_PREFIXES`, `get_legit_ip_pools()`,
      `get_legit_vlan_pools()`.
- [ ] Delete `models/constants_singleton.py` (`ConstantsSingleton`, `DisjointSet`,
      `determine_cluster`) and the scattered string-inference tests.
- [ ] Delete `utils/constants.api.py` and `utils/constants.desired.py`, which
      have no importer.
- [ ] Verify all 129 tests still pass. Unchanged reports prove the migration was
      faithful.

### Phase 3: make it presentable

- [ ] Rewrite `README.md` around the reverse-template framing rather than
      "compare configuration files". Lead with what the tool uniquely does.
- [ ] Add a worked non-Cisco example (nginx or systemd) to demonstrate
      generality. Without one, the general framing is untested.
- [ ] Reorganize the corpus: a few representative pairs in `examples/` as
      user-facing documentation, the rest to `tests/fixtures/corpus/`.
      *(Deferred from Phase 0 to avoid moving files twice.)*
- [ ] Verify packaging: confirm corpus files are excluded from the built wheel.
- [ ] Unpin over-specific dependency versions (currently exact `==` pins from a
      Python 3.9 era).
- [ ] Update `docs/architecture.md` once `constants_singleton.py` is gone.

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
