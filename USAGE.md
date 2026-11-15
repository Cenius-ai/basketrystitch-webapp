# Using BasketryStitch

Three commands: `add`, `list`, `estimate`. Everything below is copy-pasteable
and every number is real output of the tool.

## 1. Record a finished sample

You have woven a 10-row sample on 4 in reed. Before finishing it measured
100 mm; after finishing (soaked, packed and dried) it measures 88 mm.

```sh
python3 basketrystitch.py add --name "Willow Coil" --reed-width 4 --unit in \
    --sample-rows 10 --row-height-before 100 --row-height-after 88
```

```
Added entry 1: Willow Coil
reed width: 4.00 in (101.60 mm)
```

Notes:

- `--row-height-before` and `--row-height-after` are the **total** height of the
  whole sample in millimetres, not the height of one row. Measure the swatch on
  the table; the tool divides by `--sample-rows` for you.
- `--reed-width` accepts decimals (`0.25`, `3.5`). `--unit` is `in`, `cm` or
  `mm` and defaults to `in`; the width is stored normalised to millimetres so
  samples in different units stay comparable in one list.
- A blank (or whitespace-only) `--name` is refused with exit code 2 and the log
  is left exactly as it was:

  ```sh
  python3 basketrystitch.py add --name "   " --reed-width 4 --sample-rows 10 \
      --row-height-before 100 --row-height-after 88
  # error: --name must not be blank; give the sample a name     (exit 2)
  ```

## 2. Compare the log

```sh
python3 basketrystitch.py list
```

```
BasketryStitch log — 4 samples · basketrystitch_log.json

ID  NAME                 REED WIDTH            ROWS  BEFORE (mm)  AFTER (mm)  SHRINK
──  ───────────────────  ────────────────────  ────  ───────────  ──────────  ──────
 1  Willow Coil          4.00 in (101.60 mm)     10       100.00       88.00   12.0%
 2  Bulrush Tray         10.00 cm (100.00 mm)     8        80.00       72.00   10.0%
 3  Rattan Pouch         3.50 mm (3.50 mm)       14        63.50       55.30   12.9%
 4  Sedge Garden Basket  0.25 in (6.35 mm)       12       132.00      118.40   10.3%
```

Empty log (no file yet, or no entries):

```
No entries yet.
Log: /home/you/basketrystitch_log.json

Add your first sample:
  python basketrystitch.py add --name "Willow Coil" --reed-width 4 --unit in --sample-rows 10 --row-height-before 100 --row-height-after 88
```

That example is copy-pasteable as printed, and that command exits `0`.

Corrupt or unreadable log — the path and the parse problem, exit `1`, and the
file is not touched:

```
error: basketrystitch_log.json is not valid JSON (line 1, column 28: Expecting value)
```

## 3. Project the side you are planning

The sample above lost 12.0%: 100 mm → 88 mm over 10 rows, i.e. 8.80 mm of
finished height per row. Planning a 50-row side:

```sh
python3 basketrystitch.py estimate --id 1 --target-rows 50
```

```
Entry 1: Willow Coil
reed width: 4.00 in (101.60 mm)
sample: 10 rows, 100.00 mm before, 88.00 mm after
per-row after: 8.80 mm
shrinkage: 12.0%
target rows: 50
projected finished height: 440.00 mm
```

Planning a side that must finish 440 mm tall:

```sh
python3 basketrystitch.py estimate --id 1 --target-height 440
```

```
Entry 1: Willow Coil
reed width: 4.00 in (101.60 mm)
sample: 10 rows, 100.00 mm before, 88.00 mm after
per-row after: 8.80 mm
shrinkage: 12.0%
target height: 440.00 mm
projected rows: 50
```

`estimate` never writes to the log — it is read-only.

Errors (all exit `2`, one line on stderr):

```sh
python3 basketrystitch.py estimate --id 99 --target-rows 10
# error: no entry with id 99 (the log holds: 1, 2, 3, 4)
python3 basketrystitch.py estimate --id 1 --target-rows abc
# error: --target-rows must be a whole number, got 'abc'
python3 basketrystitch.py estimate --id 1
# error: give exactly one of --target-rows or --target-height
```

With an empty log, `estimate` exits `1` and asks for a sample first:

```
error: No entries yet — add one first: python basketrystitch.py add --name "Willow Coil" ...
```

## Other log files, and scripting

```sh
python3 basketrystitch.py --log ~/samples.json list      # global flag ...
python3 basketrystitch.py list --log ~/samples.json      # ... or after the command
python3 basketrystitch.py list --json | jq '.entries[].name'
python3 basketrystitch.py estimate --id 1 --target-rows 50 --json
```

`--json` is stable enough to pipe: `list` returns `{log, count, entries}` with
each entry plus `shrinkage_pct` and `per_row_after_mm`; `estimate` returns the
projection fields. Output is plain text (no colour, no spinner) whenever stdout
is not a terminal, so `list > log.txt` and `diff` behave.

## What the tool deliberately does not do

No editing or deleting entries, no charts, no reed inventory, no per-fibre
shrinkage models, no CSV import/export, no sync. `add`, `list`, `estimate` is
the whole tool — the log is a plain JSON file you can read, copy and back up.
