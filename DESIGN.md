# BasketryStitch design tokens

The committed design direction for this product, and where each token lives in
the code. BasketryStitch is a terminal tool, so the "design system" is the
palette, the type, the column grid and the separator set used by `list` and
`estimate` — there is no stylesheet.

| Token | Value | Where it is applied |
| --- | --- | --- |
| Archetype | `cli` | one executable file, `add` / `list` / `estimate`, help-first output |
| Style family | calm-precise | short declarative lines, no decoration, no emoji |
| Accent (one) | `oklch(0.58 0.12 49)` = **#b26233** | the primary result only: the new id in `add`, the projected value in `estimate` (`ACCENT_RGB` in `basketrystitch.py`) |
| Surface / mode | terminal dark — the tool never emits a background colour, so it inherits the user's dark terminal | n/a (never paints a background) |
| Neutral ramp | inherits the terminal foreground; emphasis via bold, not a second colour | `bold()` for the `list` header line |
| Type | system monospace only — one weight, no webfont, no fallback chain | the terminal's own monospace; columns are aligned by character count |
| Density | compact | one line per sample, no blank lines inside the table |
| Layout | aligned terminal columns, help-first | `render_table()` and `argparse`'s help as the entry point |
| Shape language | monospace, no chrome; box-drawing separators; one border system | `GLYPHS`: `─` rule under the header, `—` in prose, `·` as the meta separator (ASCII twins `-`, `|` for narrow consoles) |
| Signature | aligned columns; one accent for primary status; **no colour-only signal** | shrinkage always prints as a number with a `%` sign; errors always start with `error:`; colour is additive only |

## Non-negotiable behaviours that follow from the tokens

- Colour is emitted **only** when stdout is a TTY, `NO_COLOR` is unset, `TERM`
  is not `dumb` and `--no-color` was not passed. The graded surface is the
  piped plain-text table, which carries every signal without colour.
- Columns are sized from the data (header or widest cell), so a long name never
  breaks the alignment of the numeric columns.
- The rule glyph falls back to `-` when the terminal encoding cannot represent
  box-drawing characters, so Windows `cp1252` consoles still align.
- Numbers: two decimals for millimetres, one decimal for percentages, integers
  for ids and row counts. Nothing else is rounded at display time.
- No colour-only status, no spinners, no progress bars, no ANSI escape clearing
  the screen — the tool is safe to pipe, diff and record.
