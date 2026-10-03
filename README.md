# HPIT — HPC Interactive Terminal

A lightweight terminal dashboard for HPC clusters. Built for NUS Hopper
(PBS Professional, Python 3.9), with all scheduler and filesystem logic in
one shared backend so the CLI and TUI (and later a web UI) show the same data.

HPIT only runs cheap, read-only system commands (`qstat`, `df`, `find`,
`tail`). Slow ones (`du`, recursive `find`) only run when you ask.

## Features

- **Overview** — your jobs, free GPUs on the cluster, home/scratch quota, project GPU-hours left
- **Jobs** — table of your jobs, filter with `/`, toggle finished jobs with `h`
- **Projects** — GPU-hours left, reserved, end date; members' running/queued jobs and usage for any period (`[` `]` month, `c` calendar; default this month)
- **Cluster** — free GPUs per node and running/waiting jobs per queue (like `hpc gstat`)
- **Job details** — resources, node, project, script, working directory, log paths
- **Logs** — tail stdout / stderr using the paths PBS reports; follow mode
- **Storage** — home, scratch and your project folders (`/scratch/Projects/…`, `/Project_Storage/…`) with quotas (from the reports `hpc space` uses); open one with `→` to see folder sizes (`du`, cached), `←` to go back
- **Files** — read-only browser (`→` open, `←` back) with sizes, dates, and a "files over 1 GB" search
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
hpit storage [path] [--scan]       # quotas for home, scratch, project folders; folder sizes (cache or new du scan)
hpit projects               # GPU-hours left per project (needs amgr login)
hpit usage <project> [start] [end] # members' usage + live jobs; start/end YYYY-MM-DD, or YYYY-MM for a month (default: this month)
hpit cluster                # free GPUs and queue status
hpit login                  # log in to amgr (asks for your password; stores nothing)
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

Settings can live in a `.env` file (see `.env.example`). HPIT reads the
file named by `HPIT_ENV_FILE` (default `~/.config/hpit/.env`); real
environment variables win over the file.

```bash
cp .env.example .env && chmod 600 .env
echo "export HPIT_ENV_FILE=$PWD/.env" >> ~/.bashrc
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `HPIT_ENV_FILE` | `~/.config/hpit/.env` | Where to read settings from |
| `HPIT_AMGR_PASSWORD` | empty | NUS password for automatic `amgr login` (`.env` only) |
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

## Project credits (amgr)

Project data comes from `amgr` (Altair Budgets), which needs a token from
`amgr login`. The token is cached in `~/.am/` and expires. Either:

- run `hpit login` (or `amgr login`) when it expires, or
- put `HPIT_AMGR_PASSWORD` in your `.env`, and HPIT logs in for you.

HPIT passes the password to `amgr` on stdin, never as a command-line
argument (which other users could see with `ps`), tries at most once per
session (to avoid locking your account with a wrong password), and ignores
the password if the `.env` file is readable by anyone but you.

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
core/accounting.py   amgr: projects, usage, login
core/cluster.py      pbsnodes + the site's qstat snapshot
core/quota.py        home / scratch quota reports
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
- `.env` is git-ignored; keep it `chmod 600` (HPIT refuses the password otherwise).
- Keep personal access tokens out of `git remote` URLs on shared machines.

## Roadmap

- [x] CLI: jobs, job, logs, storage, projects, usage, cluster, login, doctor
- [x] TUI: overview, jobs, projects, cluster, job details, logs, storage, files, tools
- [x] Mock mode
- [ ] Streamlit web UI (`hpit web`, read-only)
- [ ] Slurm support
