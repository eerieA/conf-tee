# Architecture

Describes the current (v2) design, written Apr 2024 – Jul 2024. For the
predecessor it replaced, see [v1-retrospective.md](./v1-retrospective.md).

Text rather than an image, so it is diffable and can be updated alongside the
code. It replaces a `class_diagram.jpg` that predated the removal of the OpenAI
structure extractor and is no longer in the repository.

---

## Pipeline

```
  golden.txt                user.txt
      |                        |
      +-----------+------------+
                  |
                  v
          ReadConfig                     utils/read_config.py
          read_config_from_txt(.)
          read_config_from_response(.)   <- for callers holding parsed API data
                  |
                  |  list[str]  (one element per line)
                  v
          Extract                        models/extract.py
          _extract_structs(.)            segments BOTH files into blocks
          extract_struct(.)
                  |
                  |  list[tuple[start, end, name, 'd'|'s']]
                  |  e.g. (1, 1, 'fw25-ctx', 'd'), (2, 5, 'USER PREFIX', 's')
                  v
          Outline                        models/outline.py
          _init_blocks(.)                wraps each block as a Section
          _extract_device_name(.)
                  |
                  |  Outline holds 1..n Section
                  v
          ConfigCompare                  models/config_compare.py
          compare_structs()              aligns device/section blocks
          calculate_diff()               then compares matched sections
                  ^
                  |  Schema (see below): every vocabulary question
                  |  is answered from it, not from the code
                  |
                  v
          SectionComparer                models/section_comparer.py
          inspect_lines(.)               line alignment within one section
          compare_sentences(.)           value binding + validation
             |            |
             |            +--> LineAnalyzer            models/line_analyzer.py
             |                 word_extract_variables(.)   binds {Var} -> value
             |                 variable_is_value_match(.)  regex check
             |                 mask_variables(.)
             |
             +--> DifferO                models/differ_o.py
                  compare(.)  (difflib.Differ subclass)
                  seperate_line_ops(.)   -> DataFrame with explicit
                                            Line num 1 / Line num 2 / Line tag
                  |
                  v
          GenSummary                     models/gen_summary.py
          create_summary_dataframe(.)
          create_summary_list(.)
          create_summary_json(.)
          generate_reports(.)
                  |
        +---------+---------+---------+
        v                   v         v
    summary list      diff DataFrame   JSON report
    (counts)          (tabular view)   (integration)
```

## Supporting types

```
  Section                   models/section.py
  _adjust_first_line(.)     one device or section block: its lines + metadata
  is_empty()

  DifferO(difflib.Differ)   models/differ_o.py
  _fancy_replace(.)         overridden only to make the line-similarity
  _fancy_helper(.)          cutoff configurable (default 0.75)
  get_line_op_blocks(.)     classifies '-?+?' / '-?+' / '-+?' op patterns
  seperate_line_ops(.)      converts diff text -> typed DataFrame, ONCE
```

## The schema

The vocabulary is not in the code. A caller loads a YAML schema and passes it
in; `ConfigCompare` and `GenSummary` both take it as a constructor argument and
thread it down to the checks.

```
  schema.yaml  (caller-supplied; conftee/schemas/cisco-campus.yaml is bundled)
        |
        v
  schema.load(path) / schema.loads(text)      utils/schema.py
  validates, compiles every regex, raises SchemaError with a path
        |
        |  Schema
        v
  ConfigCompare(file_data, outline_data, schema)
  GenSummary(schema)
        |
        v
  the checks, via seven accessors:

  regex_for(var)                what a value must look like
  arithmetic_for(var)           int or ipv4, for {{Var}+1}
  variables_with_arithmetic(k)  all variables of one arithmetic kind
  variables_with_scope(s)       section / file / none consistency
  is_netmask(var)               role, not a name test
  group_of(var)                 declared subnet family
  pool_for(var)                 declared address range
```

Each accessor replaces an inference the engine used to make from variable
*names*. That is what made the tool specific to one organization: a user had to
name variables in a magic convention to get correct behavior.

| Question | Formerly inferred by | Now |
|---|---|---|
| family membership | name-prefix match plus union-find, in a `ConstantsSingleton` and `DisjointSet` | `groups:` declared outright |
| "is a netmask" | `"netmask" in var` substring test | `role: netmask` |
| VLAN pool check | `if var == "Vlan_ID_user"` | `pools:` keyed by the pool's own name |
| arithmetic kind | membership in `IPV4_VARIABLES` / `INT_VARIABLES` | `arithmetic:` on the type |
| consistency scope | subtraction from the regex dict | `scope:` on the variable |
| IP pool membership | membership in `IPV4_VARIABLES_USER` / `_INFRA` | `pool:` on the variable |
| value binding by type | membership in `IPV4_VARIABLES` | `types:` carrying regex and arithmetic together |

`models/constants_singleton.py`, which held the first row, is gone.
`utils/constants.py` still exists but the engine no longer reads the vocabulary
half of it; that half and the equivalence test pinning it retire together. See
[repurposing-plan.md](./repurposing-plan.md), Phase 3a.

### What the schema does not yet control

`syntax:` is parsed and validated, and then nothing reads it. Block and line
recognition is still matched against module-level patterns: two in
`extract.py`, three in `section.py`, two in `line_analyzer.py`, one in
`section_comparer.py`. So a foreign *vocabulary* works today and a foreign
*block syntax* does not. `tests/test_schema_generality.py` is scoped to the
half that works and says so.

## Notes

- `Extract` segments **before** diffing. This is the main structural advantage
  over the predecessor: a shifted section no longer cascades misalignment
  through the rest of the file. See [v1-retrospective.md](./v1-retrospective.md).
- `DifferO` parses diff output into typed columns exactly once, at the boundary.
  Nothing downstream re-parses diff text.
- `GenSummary` derives all three outputs from one computed result, so analysis
  never depends on presentation.
