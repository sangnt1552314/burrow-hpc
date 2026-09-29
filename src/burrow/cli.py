import sys


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
        print("Jobs coming soon")

    elif command == "storage":
        print("Storage coming soon")

    elif command == "tui":
        print("TUI coming soon")

    elif command == "web":
        print("Web UI coming soon")

    else:
        print(f"Unknown command: {command}")