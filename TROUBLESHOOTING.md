# TROUBLESHOOTING - every error we have seen so far, and the fix

> **Update for 3.0.0b3 (one-command install):** the wheel now ships the Windows file-locking fix inside the package, so errors 2 and 3 below should no longer appear with the pip install. The installer-era entries are kept because every fix here was verified on a real machine.
Link this file from the top of the README. Every entry below is a real
error observed during the Windows pilot (November 2026), with the fix
that was verified on that machine.

Golden rule for users: **take a screenshot of the whole black window**
before asking for help. The screenshot usually contains the answer.

---

## 1. "Python is not recognized" (Windows)

The computer has no Python yet.

- Double-click `RUN-ME-WINDOWS.bat` - it opens the Python download page
  for you.
- Run the Python installer. On the FIRST screen, tick the box at the
  bottom: **Add python.exe to PATH**.
- After installing, close every black window and open a new one
  (old windows do not see the new Python).

## 2. `ModuleNotFoundError: No module named 'fcntl'` (Windows)

The engine needs a small file-locking helper that Windows does not ship.

- Double-click `RUN-ME-WINDOWS.bat` - it detects this and writes the
  helper automatically, then continues.
- Manual fix (only if you are doing it by hand): create a file named
  `fcntl.py` inside your Python user site-packages folder with:
  `LOCK_SH = 1`, `LOCK_EX = 2`, `LOCK_NB = 4`, `LOCK_UN = 8` and empty
  `flock` / `lockf` functions. Easiest path: use the installer.

## 3. `NameError: name 's' is not defined` - and even `pip` now crashes

The fcntl helper file got corrupted (a stray character inside it).
Because Python's own `subprocess` module reads this file, a BROKEN file
is worse than a MISSING one: pip, pathlib and more all crash.

Fix - delete the file, then re-run the installer:

```powershell
del "$env:APPDATA\Python\Python314\site-packages\fcntl.py"
```

(The folder name `Python314` changes with your Python version - adjust,
or find it with `python -c "import site; print(site.getusersitepackages())"`.)

Deleting it is safe. The installer will recreate it cleanly.

## 4. `WinError 10061` / `ConnectionRefusedError` when running a command

The conscience (the background brain) is not running. Commands like
`impulse` talk to it on `127.0.0.1:7717`.

Fix: open a second window and start it:

```
python -m cerberus_gate serve
```

Keep that window open. Then run your command again.
(Fixed more gently in b3: the command will print this hint instead of
a raw traceback.)

## 5. "no mind yet - run init" / `seals` says `NO_MEMORY`, entries 0

A fresh install has no mind yet. From b3 the first `serve` (or your AI
tool's MCP spawn) creates it automatically - this message only appears
if you run a read command before the first awakening. Run:

```
python -m cerberus_gate serve
```

then try again. On b2 or older, run `python -m cerberus_gate init` once.
Then bring the ledger alive: write the first impulse and `seals` flips
to `INTACT`:

```
python -m cerberus_gate impulse write realm/hello.txt --text "hi" --why "first words"
python -m cerberus_gate seals
```

## 6. Dashboard does not open

The dashboard lives at **http://127.0.0.1:7717/dash** (port 7717).
Some older documents say 7750 - 7717 is correct. It only works while
`serve` is running, and it is reachable from this machine only.

## 7. pip warning: "The scripts cerb.exe and cerberus.exe are not on PATH"

Cosmetic only. Ignore it - all commands in the docs use the long form
`python -m cerberus_gate`, which always works.

## 8. Windows SmartScreen blocked the installer ("protected your PC")

Click **More info** -> **Run anyway**. This appears because the
installer is a plain script without a paid code-signing certificate.

## 9. The banner says "licensed to" a wrong or placeholder name

The license step used a placeholder instead of the real customer name.
Customers: ask the founder for the exact activation line and run it.
Founder: fix the baking step - the customer name must be baked at
build time (pilot finding #7).

## 10. `python3: command not found` (Mac/Linux)

Install Python from https://www.python.org/downloads/ , or on a fresh
Mac run `xcode-select --install` first. Then use `python3 -m cerberus_gate ...`

---

## How to report a bug (when the fixes above do not help)

Send the founder (or, later, open a GitHub Issue) with:

1. A screenshot of the whole window with the error
2. The output of: `python -m cerberus_gate seals`
3. Your operating system and the output of: `python --version`
4. What you clicked / typed right before the error

Planned for b3/b4: a `python -m cerberus_gate doctor` command that
collects 1-4 automatically and prints a paste-ready report.
