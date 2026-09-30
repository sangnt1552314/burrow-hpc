import sys

from burrow.core.pbs import get_jobs, get_jobs_raw


def main():
    if len(sys.argv) < 2:
        print("Burrow HPC")
        print()
        print("Usage:")
        print("  burrow jobs")
        print("  burrow storage")
        print("  burrow tui")
        print("  burrow web")
        return

    command = sys.argv[1]

    if command == "jobs":
        jobs = get_jobs()

        print(f"{'JOB ID':<18} {'NAME':<12} {'QUEUE':<8} {'STATE':<6} {'RUNTIME':<10}")

        for job in jobs:
            print(
                f"{job.job_id:<18} "
                f"{job.name:<12} "
                f"{job.queue:<8} "
                f"{job.state:<6} "
                f"{job.runtime:<10}"
            )

    elif command == "storage":
        print("Storage coming soon")

    elif command == "tui":
        print("TUI coming soon")

    elif command == "web":
        print("Web UI coming soon")

    else:
        print(f"Unknown command: {command}")