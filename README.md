# HPIT — HPC Interactive Terminal

A lightweight terminal dashboard for HPC clusters. Built for NUS Hopper
(PBS Professional, Python 3.9), with all scheduler and filesystem logic in
one shared backend so the CLI and TUI (and later a web UI) show the same data.

HPIT only runs cheap, read-only system commands (`qstat`, `df`, `find`,
`tail`). Slow ones (`du`, recursive `find`) only run when you ask.

## Features

- **Overview** — running / queued / held jobs, GPUs in use, scratch quota
- **Jobs** — table of your jobs, filter with `/`, toggle finished jobs with `h`
- **Job details** — resources, node, project, script, working directory, log paths
- **Logs** — tail stdout / stderr using the paths PBS reports; follow mode
- **Storage** — scratch usage bar (instant, `df`) and per-folder sizes (`du`, cached)
- **Files** — read-only browser with sizes, dates, and a "files over 1 GB" search
- **Tools** — doctor page: versions, paths, configuration
- **Cancel job** — `k`, always behind a confirmation showing the exact job ID and name
- **Mock mode** — realistic fake data for developing without PBS

## Installation (Hopper)

Uses the system Python 3.9; no virtualenv needed.

```bash
git clone https://github.com/sangnt1552314/hpit.git
cd hpit
pip install --user -e .
```

Make sure `~/.local/bin` is on your `PATH`.

## CLI

```bash
hpit jobs [-a]              # your jobs (-a includes finished jobs)
hpit job <job-id>           # details of one job
hpit logs <job-id> [-e] [-n 100]   # tail stdout (or stderr with -e)
hpit storage [path] [--scan]       # scratch usage; folder sizes from cache or a new du scan
hpit doctor                 # environment and configuration check
hpit tui                    # terminal UI
```

## TUI

```bash
hpit tui
```

| Key | Action |
| --- | --- |
| `↑` `↓` / `Enter` | Move / open |
| `Esc` | Back |
| `1`–`6` | Jump to a page |
| `r` | Refresh |
| `?` | Help |
| `q` | Quit |

Page-specific keys (search, logs, scan, …) are shown in the footer only
where they work. Job lists refresh automatically every 60 seconds.

## Configuration

All optional, set as environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `HPIT_CLUSTER_NAME` | `Hopper` | Name shown in the header |
| `HPIT_SCRATCH` | `/scratch/$USER` | Scratch root for Storage and Files |
| `HPIT_REFRESH_INTERVAL` | `60` | Seconds between job refreshes (`0` = off) |
| `HPIT_LOG_LINES` | `200` | Lines shown when tailing logs |
| `HPIT_MOCK` | off | Use fake data instead of PBS |
| `HPIT_DEBUG` | off | Show full tracebacks instead of short errors |

Storage scans are cached in `~/.cache/hpit/storage.json`.

## Mock mode

```bash
HPIT_MOCK=1 hpit tui
```

Shows fake jobs, job details, logs, storage, and files, so you can work on
the UI on a laptop. (Real mode relies on GNU `find`/`du`, as on Linux.)

## Architecture

```text
CLI (cli.py) / TUI (tui/)
        ↓
core/api.py          picks real backend or mock, once
        ↓
core/pbs.py          qstat / qdel  (JSON output: qstat -f -F json)
core/logs.py         tail
core/storage.py      df, du (+ cache)
core/files.py        find
core/system.py       doctor info
        ↓
core/command.py      subprocess with timeout; no shell=True
```

`core/models.py` holds the dataclasses (`Job`, `JobDetails`, `StorageScan`,
`FileEntry`, …) that every UI consumes. UIs never call scheduler commands
directly.

## Security

- Everything is read-only except job cancellation, which needs explicit
  confirmation in the TUI.
- Commands are run with argument lists, never through a shell.
- Keep personal access tokens out of `git remote` URLs on shared machines.

## Roadmap

- [x] CLI: jobs, job, logs, storage, doctor
- [x] TUI: overview, jobs, job details, logs, storage, files, tools
- [x] Mock mode
- [ ] Streamlit web UI (`hpit web`, read-only)
- [ ] Slurm support
