# icgrep I/O Specification (Project)

Used by the combinatorial test oracle.

## Exit codes

- `0`: at least one selected line is produced
- `1`: no selected lines are produced
- `2`: error (invalid regex, unreadable or missing file, usage error)

## Parameters in model

- `source_type`: `inline` or `file_flag`
- `pattern_type`:
  - `literal` -> `foo`
  - `char_class` -> `[f]oo`
  - `negated_class` -> `[^0-9]`
  - `anchor_start` -> `^foo`
  - `anchor_end` -> `foo$`
  - `alternation` -> `foo|bar`
  - `repetition` -> `f+o+`
  - `unicode_property` -> `\p{Ll}+`
  - `empty` -> `` (empty string, any line selected)
  - `invalid` -> `(` (parse error)
- `file_type`:
  - `empty` (no lines)
  - `no_match` (lines that should not match any defined pattern)
  - `one_match` (one matching line)
  - `many_match` (multiple matches)
  - `unicode_content` (UTF-8 content incl. CJK/accented chars)
  - `missing_path` (non-existent file)
- flags: `count`, `invert`, `ignore_case`, `line_numbers`

## Oracle assumptions

- `invalid` pattern -> exit `2`
- `missing_path` -> exit `2`
- otherwise:
  - selected line count > 0 -> exit `0`
  - selected line count == 0 -> exit `1`
- `count` mode expects stdout to be a single integer line (selected-line count).
- `line_numbers` mode expects `N:line` format (1-indexed).
- For `\p{Ll}+` with `-i`, icgrep case-folds; oracle matches any letter in that case.
