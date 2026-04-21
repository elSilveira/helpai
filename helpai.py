"""Console entry point for pip-installed HelpAI."""


def main() -> None:
    from launcher import main as launcher_main

    launcher_main()


if __name__ == "__main__":
    main()