import argparse
import sys

from hpit import __version__
from hpit.core import api, config
from hpit.core.errors import HPITError
from hpit.core.units import human_bytes


def cmd_jobs(args: argparse.Namespace) -> None:
    jobs = api.get_jobs(include_finished=args.all)

    if not jobs:
        print("No active jobs.")
        return

    print(
        f"{'JOB ID':<25} "
        f"{'NAME':<50} "
        f"{'QUEUE':<10} "
        f"{'STATE':<6} "
        f"{'RUNTIME':<10}"
    )

    for job in jobs:
        print(
            f"{job.job_id:<25} "
            f"{job.name:<50} "
            f"{job.queue:<10} "
            f"{job.state:<6} "
            f"{job.runtime:<10}"
        )


def cmd_job(args: argparse.Namespace) -> None:
    details = api.get_job_details(args.job_id)
    job = details.job
    stderr = "merged into stdout" if details.stderr_joined else details.stderr_path

    rows = [
        ("Name", job.name),
        ("Status", job.state_name),
        ("Job ID", job.job_id),
        ("Queue", job.queue),
        ("Node", details.node),
        ("GPU / CPU", f"{job.gpus} / {job.cpus}"),
        ("Memory", f"{details.memory_used} used of {job.memory}"),
        ("Walltime", f"{job.runtime} of {job.requested_walltime}"),
        ("Project", details.project),
        ("Script", details.script),
        ("Working directory", details.workdir),
        ("stdout", details.stdout_path or "--"),
        ("stderr", stderr or "--"),
    ]
    for label, value in rows:
        print(f"{label:<20}{value}")


def cmd_logs(args: argparse.Namespace) -> None:
    stream = "stderr" if args.stderr else "stdout"
    log = api.tail_job_log_by_id(args.job_id, stream, args.lines)

    print(f"==> {log.path} <==", file=sys.stderr)
    if log.note:
        print(log.note, file=sys.stderr)
    for line in log.lines:
        print(line)


def cmd_storage(args: argparse.Namespace) -> None:
    path = args.path or config.SCRATCH
    usage = api.get_disk_usage(config.SCRATCH)
    print(
        f"Scratch {config.SCRATCH}: {usage.percent:.0f}% used "
        f"({human_bytes(usage.used_bytes)} of {human_bytes(usage.total_bytes)})"
    )

    if args.scan:
        print(f"Scanning {path} with du (this can take minutes)...", file=sys.stderr)
        scan = api.scan_directory(path)
    else:
        scan = api.load_cached_scan(path)
        if scan is None:
            print(f"\nNo folder sizes for {path} yet. Run: hpit storage --scan")
            return

    print(f"\n{scan.path}  ({human_bytes(scan.total_bytes)} total)")
    for entry in scan.entries:
        print(f"  {human_bytes(entry.size_bytes):>10}  {entry.name}")


def cmd_doctor(args: argparse.Namespace) -> None:
    for name, value in api.get_doctor():
        print(f"{name:<24}{value}")


def cmd_tui(args: argparse.Namespace) -> None:
    from hpit.tui.app import HPITApp

    HPITApp().run()


def cmd_web(args: argparse.Namespace) -> None:
    print("Web UI coming soon")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hpit",
        description="HPIT - HPC Interactive Terminal",
    )
    parser.add_argument("--version", action="version", version=f"hpit {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="<command>")

    jobs = commands.add_parser("jobs", help="list your jobs")
    jobs.add_argument("-a", "--all", action="store_true", help="include finished jobs")
    jobs.set_defaults(func=cmd_jobs)

    job = commands.add_parser("job", help="show details of one job")
    job.add_argument("job_id")
    job.set_defaults(func=cmd_job)

    logs = commands.add_parser("logs", help="tail a job's stdout or stderr")
    logs.add_argument("job_id")
    logs.add_argument("-e", "--stderr", action="store_true", help="show stderr instead of stdout")
    logs.add_argument("-n", "--lines", type=int, default=config.LOG_LINES)
    logs.set_defaults(func=cmd_logs)

    storage = commands.add_parser("storage", help="scratch usage and folder sizes")
    storage.add_argument("path", nargs="?", help="folder to show (default: scratch)")
    storage.add_argument("--scan", action="store_true", help="measure folder sizes now with du (slow)")
    storage.set_defaults(func=cmd_storage)

    doctor = commands.add_parser("doctor", help="check environment and configuration")
    doctor.set_defaults(func=cmd_doctor)

    tui = commands.add_parser("tui", help="open the terminal UI")
    tui.set_defaults(func=cmd_tui)

    web = commands.add_parser("web", help="open the web UI (not implemented yet)")
    web.set_defaults(func=cmd_web)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    try:
        args.func(args)
    except HPITError as exc:
        if config.DEBUG:
            raise
        print(f"hpit: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
