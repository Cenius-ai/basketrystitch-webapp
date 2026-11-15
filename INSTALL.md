# Installing BasketryStitch

BasketryStitch is a single Python file with no third-party dependencies. There
is no database, no service, no account and no configuration file — the log is
just a JSON file next to you.

## Prerequisites (install these yourself, if missing)

| Requirement | Why | Check |
| --- | --- | --- |
| Python **3.9 or newer** | the only runtime | `python3 --version` |

Nothing else is needed: no compiler, no `pip install` of a framework, no
`sqlite3-dev`, no system packages, no `sudo`.

## Steps

1. **Set up the project (installs nothing, verifies the toolchain, then exits).**

   ```sh
   sh install.sh
   ```

   Expected tail of the output:

   ```
   python 3.x.y ok
   basketrystitch 1.0.0 ok
   Setup complete. ...
   ```

   `sh install.sh` is idempotent and offline-safe: it checks the interpreter
   version, honours `requirements.txt` (which declares no runtime packages),
   and imports the module once so a broken environment fails here rather than
   at first use. It never starts anything.

2. *(optional)* **Install the test runner** if you prefer `pytest` over the
   standard library runner:

   ```sh
   sh install.sh --dev        # pip install -r requirements-dev.txt (pytest 8.3.4)
   ```

3. **There is no database to migrate and no seed to run.** The first
   successful `add` creates the log file. The repository ships a small demo log
   (`basketrystitch_log.json`) so `list` shows real samples immediately; delete
   it whenever you want to start your own log:

   ```sh
   rm basketrystitch_log.json
   ```

4. **Run it.** There is nothing to start — this is a command line tool:

   ```sh
   python3 basketrystitch.py --help
   python3 basketrystitch.py list
   ```

   (On Windows use `python basketrystitch.py ...`.)

5. **Check it works end to end.**

   ```sh
   sh smoke.sh          # add -> list -> estimate, must print 440.00 mm
   sh demo.sh           # longer, narrated demo in a throw-away directory
   ```

6. **Run the test suite.**

   ```sh
   python3 -m unittest discover -s tests
   ```

## Uninstalling

Delete `basketrystitch.py` (and `basketrystitch_log.json` if you do not want to
keep your samples). Nothing was installed outside the project directory.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `error: python3 not found` | install Python 3.9+ and re-run `sh install.sh` |
| `error: <path> is not valid JSON (line N, column M: ...)` | the log was hand-edited into invalid JSON; restore it from a backup or delete it to start a fresh log — the file is never rewritten behind your back |
| `error: cannot read <path>: Permission denied` | the log is readable only by another user; `chmod 644` it or point `--log` somewhere you own |
| `error: no entry with id 7` | `python3 basketrystitch.py list` shows the ids that exist |
| `error: give exactly one of --target-rows or --target-height` | `estimate` needs one target, not both, not neither |
