from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def sha256_file(path: Path, buffer_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(buffer_size):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_line(executable_name: str, digest: str) -> str:
    return f"{digest}  {Path(executable_name).name}\n"


def write_checksum(path: Path) -> Path:
    executable = path.resolve(strict=True)
    destination = executable.with_name(f"{executable.name}.sha256")
    destination.write_text(
        checksum_line(executable.name, sha256_file(executable)),
        encoding="ascii",
        newline="\n",
    )
    return destination


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("Usage: write_release_checksum.py <executable>", file=sys.stderr)
        return 2
    destination = write_checksum(Path(arguments[0]))
    print(f"Release checksum written: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
