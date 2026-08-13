from __future__ import annotations

import argparse
import fcntl
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from types import TracebackType

LOCK_FILENAME = ".event-lead-ops.lock"


class ProfileLockError(RuntimeError):
    pass


class ProfileLock:
    """Hold an exclusive POSIX lock for one persistent browser profile."""

    def __init__(self, profile_dir: str | Path) -> None:
        self.profile_dir = Path(profile_dir).resolve()
        self.lock_path = self.profile_dir / LOCK_FILENAME
        self._file = None
        self._lease_id: str | None = None

    def __enter__(self) -> ProfileLock:
        self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.profile_dir, 0o700)
        self._file = self.lock_path.open("a+", encoding="utf-8")
        os.chmod(self.lock_path, 0o600)
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._file.close()
            self._file = None
            raise ProfileLockError(f"profile already owned: {self.profile_dir}") from exc
        self._file.seek(0)
        self._file.truncate()
        self._lease_id = uuid.uuid4().hex
        self._file.write(f"pid={os.getpid()}\nlease_id={self._lease_id}\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None
            self._lease_id = None

    def assert_owned(
        self, profile_dir: str | Path, *, lease_id: str | None = None
    ) -> None:
        if self._file is None or self._file.closed or self._lease_id is None:
            raise ProfileLockError("profile lock is not held")
        if Path(profile_dir).resolve() != self.profile_dir:
            raise ProfileLockError("profile lock belongs to a different profile")
        if lease_id is not None and lease_id != self._lease_id:
            raise ProfileLockError("profile lock lease does not match")
        descriptor_stat = os.fstat(self._file.fileno())
        try:
            pathname_stat = self.lock_path.lstat()
        except FileNotFoundError as exc:
            raise ProfileLockError("profile lock pathname was removed") from exc
        if stat.S_ISLNK(pathname_stat.st_mode) or (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ) != (pathname_stat.st_dev, pathname_stat.st_ino):
            raise ProfileLockError("profile lock pathname was replaced")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ProfileLockError("profile kernel lock is not owned") from exc
        pathname_stat = self.lock_path.lstat()
        descriptor_stat = os.fstat(self._file.fileno())
        if (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
        ) != (pathname_stat.st_dev, pathname_stat.st_ino):
            raise ProfileLockError("profile lock pathname changed during attestation")

    @property
    def lease_id(self) -> str:
        self.assert_owned(self.profile_dir)
        assert self._lease_id is not None
        return self._lease_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one process while exclusively owning a persistent browser profile"
    )
    parser.add_argument("--profile", required=True, help="persistent browser profile directory")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command after --")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("a command is required after --")
    try:
        with ProfileLock(args.profile):
            return subprocess.run(command, check=False).returncode
    except ProfileLockError as exc:
        print(str(exc), file=sys.stderr)
        return 73


if __name__ == "__main__":
    raise SystemExit(main())
