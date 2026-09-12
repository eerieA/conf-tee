# Architecture

Text version of the class diagram (replaces `resources/class_diagram.jpg`, which
predates the removal of the OpenAI structure extractor). Kept as text so it is
diffable and can be updated alongside the code.

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

## Configuration / constants (being replaced)

```
  utils/constants.py
  WORD_TYPE_REGEXES     {variable name -> regex}
  IPV4_VARIABLES        which variables take IPv4 arithmetic
  INT_VARIABLES         which variables take integer arithmetic
  IPV4_VARIABLES_USER   pool membership
  IPV4_VARIABLES_INFRA  pool membership
  SUBNET_CLUSTERS       prefixes that define a subnet family
        |
        v
  ConstantsSingleton        models/constants_singleton.py
  get_clusters_dict()       RECOVERS variable families at runtime by
  determine_cluster(.)      string-prefix matching on variable NAMES
        |
        v
  DisjointSet
  find(.) / union(.)        union-find over name prefixes
```

> **Note — this branch is scheduled for deletion.**
> `ConstantsSingleton` + `DisjointSet` exist only to *infer* which variables
> belong to the same subnet family, by matching shared name prefixes
> (`Vrfglue_prefix`, `Vrfglue_prefix_1st_IP`, `Vrfglue_prefix_netmask` -> one
> family). Related inferences are scattered elsewhere as string tests:
>
> | Inference | Where | How |
> |---|---|---|
> | family membership | `constants_singleton.py` | name prefix match + union-find |
> | "is a netmask" | `diff_helpers.py:432` | `"netmask" in var` |
> | VLAN pool check | `diff_helpers.py:370` | `if var == "Vlan_ID_user"` |
> | arithmetic kind | `section_comparer.py:55` | membership in `IPV4_VARIABLES` / `INT_VARIABLES` |
> | consistency scope | `diff_helpers.py:22` | computed by *subtraction* from the regex dict |
>
> Declaring families, roles and scopes explicitly in a schema file makes all of
> the above data rather than inference, and removes the requirement that a user
> *name* their variables in a magic convention to get correct behavior. See
> the schema work superseding `utils/constants.py`.

## Notes

- `Extract` segments **before** diffing. This is the main structural advantage
  over the predecessor: a shifted section no longer cascades misalignment
  through the rest of the file. See [v1-retrospective.md](./v1-retrospective.md).
- `DifferO` parses diff output into typed columns exactly once, at the boundary.
  Nothing downstream re-parses diff text.
- `GenSummary` derives all three outputs from one computed result, so analysis
  never depends on presentation.
