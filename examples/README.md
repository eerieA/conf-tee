# Examples

Four golden/user pairs, ordered from smallest to richest. Each `golden/NAME` is
a template with `{Variable}` holes; each `user/NAME` is a config checked against
it. Run the demo driver and pick one by name:

```
python main.py
```

The driver lists `golden/` and pairs your choice with the identically named file
in `user/`.

| Pair | Lines | What it shows |
|---|---|---|
| `test_file_one_line_bad.txt` | 3 | The smallest possible failure: one line, one value that does not match its variable's type. |
| `test_file_one_section_bad.txt` | 12 | One section, four kinds of finding at once: wrong values, a value that contradicts itself elsewhere, a missing line, and commands that differ. |
| `add a user vlan in blg rt-hsrp network type 6.txt` | 73 | A real production-shaped config that fully conforms. The useful shape of a clean run. |
| `test_file_structure_bad.txt` | 49 | Every category the tool reports, including structural mismatches where sections appear in the wrong place. |

Start with the first. It fits on a screen and the report has exactly one entry,
so the mapping from finding to cause is unambiguous.

## Why these four and not the whole corpus

The other 59 pairs are in `tests/fixtures/corpus/`. They exist to pin engine
behavior, not to be read: many differ from each other in one line, and the
largest produce reports with 90-plus entries. Keeping them out of here is what
lets these four be read start to finish.

## `sample_corpus.py`

The infrastructure prefixes these configs are checked against. They describe
this corpus and nothing else, which is why they sit here rather than inside the
`conftee` package. In a real deployment the equivalent values come from whatever
the network's source of truth is. The file's own docstring explains how it
differs from a schema.
