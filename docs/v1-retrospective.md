# v1 retrospective: why the predecessor was rewritten

**Timeline:** v1 was developed roughly Aug 2023 – Dec 2023. The rewrite (v2, the
code in this repository) followed in Apr 2024 – Jul 2024.

**Status:** The v1 source code has been removed from this repository. This document
preserves its architecture and the engineering lessons learned from it.

**Why the code is gone:** v1 was written by a previous developer on the project. This
document extracts what was learned (architecture, failure modes, anti-patterns)
without republishing someone else's work under this repository's license.

**Scope note:** v1 was an early prototype built under school-project time pressure, and
it did establish the core insight this tool still rests on: that a "golden" config is a
*template with typed holes*, and the job is to bind those holes to real values and check
them. Every criticism below is about structure, not about the idea, which was sound and
which v2 kept.

---

## 1. v1 Architecture

Five modules, no classes, with state shared through module-level globals.

```
                    start_config_compare.py
                       (CLI entry point)
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
  config_diff_compare   first_run_for_    deal_with_variable_
      (1121 lines)       variable.py         dict.py
          |               (430 lines)        (257 lines)
          |                   |                   |
    difflib.Differ      get_global_          filter_variable_
    compare_paragraphs   variable()             dict()
    highlight_          (walks diff text)   (validates values)
     differences_word
          |                   |                   |
          +---------> module-level globals <------+
                word_bracket_type, Vlan_name,
                User_prefix, variable_dict

  file_prepare.py       interactive file creation (unused by main flow)
  change_bracket.py     one-off corpus migration script
```

### Data flow

```
golden.txt + user.txt
   |
   v
compare_paragraphs()  -> difflib.Differ().compare()
   |
   v
DIFF AS A SINGLE STRING  ("- line\n+ line\n?  ^^^\n  line...")
   |
   v
get_global_variable(differences)   <-- re-parses that string
   |                                   line-by-line, counting
   |                                   leading spaces to infer
   |                                   structure
   v
variable_dict {'{Var}': {'value': {'count': n, 'line_numbers': [...]}}}
   |
   v
filter_variable_dict()  -> (good_dict, bad_dict)
   |
   v
highlight_differences_word()  -> ANSI-colored string
   |
   v
string .replace() surgery:
   .replace("\n","") .replace("next","\n") .replace("+","") .replace("-","",1)
   |
   v
print()
```

---

## 2. What prevented it from doing correct work

### 2.1 The diff was consumed as text, not as data

`compare_paragraphs()` joined difflib's output into one string, and every downstream
stage re-parsed that string. Structural facts difflib already knew (which line is an
insert, which a delete, the opcode spans) were thrown away and then guessed back via
`count_leading_nonletters()`, `next_lines_start_with()`, and `is_end_of_paragraph()`.

Any config line whose *content* resembled diff syntax could be misread as a diff marker.
The pipeline had no way to distinguish "this is a `-` from difflib" from "this line
happens to begin with `-`".

> **v2's fix:** `DifferO.seperate_line_ops()` converts diff output into a DataFrame with
> explicit `Line num 1` / `Line num 2` / `Line tag` columns *once*, at the boundary.
> Everything downstream reads typed columns, never re-parsed text.

### 2.2 Output was built by string mutation, not by rendering a model

The final output in `start_config_compare.py` was assembled by chained `.replace()`
calls, including `.replace("next", "\n")`, which corrupts any config containing the
literal word "next", and `.replace("-", "", 1)`, which deletes the first hyphen in the
entire report regardless of what it belonged to.

Because presentation and analysis were fused, there was exactly one possible output
(colored text for a terminal). Producing JSON for another system meant re-deriving
everything from scratch.

> **v2's fix:** `GenSummary.generate_reports()` returns three views (summary tuple,
> DataFrame, JSON) from one computed result. Analysis never touches formatting.

### 2.3 Correctness depended on global mutable state

`word_bracket_type`, `Vlan_name`, and `User_prefix` were module-level globals reassigned
deep inside per-word loops (`process_word`, `process_line`, `check_variable_format`).
`Vlan_name` in particular did double duty as *both* a flag and a stored first-seen value,
implementing consistency checking as a side effect:

```python
if word_bracket_type == '{Vlan_name}':
    if Vlan_name is None:
        Vlan_name = word      # first sighting: remember
    else:
        return Vlan_name == word   # later: compare
```

Consequences: results depended on traversal order; a second comparison in the same
process would see state left over from the first; and the logic could not be unit-tested
in isolation because correctness lived in interpreter-global variables.

> **v2's fix:** Values are bound into per-scope structures (`Outline`, `Section`) and
> compared explicitly. Consistency scope is a property of the comparison, not a leftover
> global.

### 2.4 Semantic rules hardcoded as string equality on template fragments

`check_variable_format()` dispatched on the *entire surrounding template text*:

```python
if word_bracket_type == "64000:{RD_ID}" and ':' in word:
    word = word.split(':', 1)[-1]
if word_bracket_type == "VRF_{VRF_name}_Subnets" and word.count('_') == 2:
    word = word.split('_')[1]
if word_bracket_type == "Vlan{Vlan_ID}":
    word = word[4:]           # strip literal "Vlan" by index
```

Each is a rule about extracting a value from surrounding literal text, a real and
recurring need. But encoding it as equality against one exact template string means the
rule fires only for that byte-for-byte context. Writing `64000: {RD_ID}` with a space, or
`VRF_{VRF_name}_Subnet` (singular), silently disables the rule with no error. `word[4:]`
hardcodes the length of "Vlan" at a call site far from anything explaining why.

Worse, some cases returned a hardcoded `False` where the real logic was never written:

```python
if word_bracket_type == "{User_Prefix_last_IP-1}" ...:
    return False    # "need to change string and calculate correct IP"
if word_bracket_type == '{user_prefix_netmask}':
    return False
```

An unimplemented feature reported as a *validation failure*: the tool actively lied
about the user's config.

> **v2's fix:** `LineAnalyzer` extracts variables positionally against the template, and
> arithmetic is a real evaluator (`_evaluate_expression`) handling `{{Var}+1}` generally
> rather than per-literal-string.

### 2.5 Debug code left in the parsing loop

```python
for line_number, line in enumerate(all_lines):
    if line_number == 11:
        print('debug print')
```

Unconditional output from library code, on every run, for any input over 11 lines.
A reliable sign that the module had no test harness: with one, this would have shown
up as noise in captured output.

---

## 3. What made it un-scalable

| Problem | Effect |
|---|---|
| **1121-line module, 400+ line functions** | `process_edited_lines` and `process_line` took 8–10 positional arguments and mixed parsing, validation, and coloring in one body. No unit could be tested or changed alone. |
| **No block/section awareness** | v1 diffed whole files as flat line sequences. One inserted section near the top shifted every subsequent line, so difflib's alignment cascaded and the rest of the report became noise. Multi-device configs, the actual use case, degraded worst. |
| **Flat global namespace for variables** | One `variable_dict` for the whole file meant no way to express "consistent within this section" vs "consistent across the file". The `Vlan_name`-as-global hack was a symptom: it could only ever express *one* file-global consistency rule, hardcoded for one variable. |
| **Terminal output as the only interface** | No importable API. Integration with another system would require re-implementing everything. |
| **Regex dict duplicated per-variable** | The same 100-character IPv4 regex was pasted ~15 times. A fix to one copy left the others wrong. |
| **No tests** | Nothing pinned behavior, so any refactor was a gamble. |

> **v2's fix for the structural item:** `Extract._extract_structs()` segments both files
> into device/section blocks *first*, then aligns within blocks. A shifted section no
> longer poisons the rest of the file.

---

## 4. Anti-patterns catalogue

Worth recognizing in future code, independent of this project:

1. **Stringly-typed pipeline**: passing rich structure between stages as formatted text,
   forcing each stage to re-parse. Data should stay structured until the final render.
2. **Parse-validate-present fusion**: one function doing all three yields exactly one
   output format and no testable seam.
3. **Globals as implicit parameters**: `global word_bracket_type` reassigned inside
   nested loops makes call order part of the contract.
4. **A variable serving as both sentinel and storage**: `Vlan_name` as `None`-flag *and*
   remembered value conflates "have I seen this?" with "what was it?".
5. **Dispatch on exact literal strings**: `if template == "Vlan{Vlan_ID}"` makes
   behavior depend on incidental formatting; whitespace changes silently disable rules.
6. **Returning a failure value for unimplemented logic**: `return False` with a TODO
   comment reports a *wrong answer* rather than an honest "not supported".
7. **Magic index slicing**: `word[4:]` to strip a known prefix, with the length inlined
   far from its justification.
8. **Output built by chained `.replace()`**: especially `.replace("next", "\n")`, where
   a sentinel collides with real content.
9. **Copy-pasted constants**: the same IPv4 regex duplicated 15 times.
10. **Debug prints left in loops**: a proxy signal for "this code has no test harness".

---

## 5. What v1 got right, and what v2 kept

The rewrite inherited more than it replaced:

- **The core insight**: treating the golden config as a *template with typed holes*, and
  the task as binding holes to real values then validating them. That framing is the
  whole product, and it came from v1.
- **Regex-per-variable-type**: the `WORD_TYPE_REGEXES` dict was carried into v2 nearly
  intact, and is documented there as "directly copied from version 1".
- **Value-consistency checking**: v1's `Vlan_name` hack was the wrong *mechanism*, but
  the requirement it served (a variable keeps one value throughout) was real, and v2
  implements it properly with explicit scopes.
- **Human-readable colored output**: v1 understood the audience was a human reviewer.
  v2 kept that and added machine-readable JSON alongside it.

---

## 6. Summary: the shape of the rewrite

| Dimension | v1 | v2 |
|---|---|---|
| Structure | 5 modules, ~1900 lines, no classes | Layered: `Extract` → `Outline` → `ConfigCompare` → `GenSummary` |
| Largest unit | 1121-line module, 400-line functions | Focused classes, largest ~690 lines |
| State | Module-level mutable globals | Instance state on explicit objects |
| Diff handling | Text re-parsed at each stage | Parsed once into typed DataFrame |
| File structure | Flat line sequence | Device/section block segmentation |
| Consistency scope | One hardcoded global rule | Per-section and per-file scopes |
| Arithmetic | Per-literal-string special cases | General expression evaluator |
| Output | Terminal string only | Summary + DataFrame + JSON |
| Interface | CLI only | CLI + importable module |

The next step in this repository's evolution addresses the one thing *both* versions
share: variable vocabulary and semantics remain hardcoded to one organization's
conventions. See the schema work that supersedes `utils/constants.py`.
