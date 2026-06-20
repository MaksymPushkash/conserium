import argparse
import json
from pathlib import Path

from src.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="openapi.json")
    args = parser.parse_args()

    output = Path(args.output)
    output.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
