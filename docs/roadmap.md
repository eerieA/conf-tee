# Roadmap

Open work, and the decisions behind the current design. The repurposing that
turned a retired, organization-specific tool into this repository is complete;
its step-by-step record is in git history.

---

## Optional polish

Only if the work still appeals.

- [ ] Diff performance: replace `difflib` with Myers or patience diff.
      *Interesting, but optimizes something nobody was waiting on.* Last, or never.
      `difflib.Differ._fancy_replace` is O(n·m) with a per-pair ratio
      computation, but inputs are device configs of a few hundred lines, and
      `Extract` segments files into blocks *before* diffing, so n and m are
      small. Real runtime is well under a second.
- [ ] Refactor Pandas out. It is used for readability and structure, not for
      anything pandas is good at; see "On pandas" in `README.md`.
- [ ] Revisit `links` as a general constraints system (`a == b`, `a < b`,
      `a in subnet(b)`), if anyone needs it. `links` was cross-variable
      equality conditioned on section; see the decisions table for why it was
      cut.
- [ ] Complete the one unfinished client requirement: structural relational
      anomalies (e.g. inconsistent counts of downlink portchannels vs downlink
      device blocks).
- [ ] Decide on `replace_device_titles_in_response` (`utils/helpers.py:173`),
      which has no caller. It is the surviving sibling of
      `replace_device_titles_in_golden`, removed with the dead HTML output
      path, and looks like the same kind of fixture helper.
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
      unlike the rest of this list this is a correctness limit rather than
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

## Decisions made, with reasoning

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
