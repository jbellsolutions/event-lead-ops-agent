from __future__ import annotations

import argparse
import fcntl
import os
import select
import stat
import struct
import subprocess
import sys
import uuid
from pathlib import Path
from types import TracebackType

LOCK_FILENAME = ".event-lead-ops.lock"


class ProfileLockError(RuntimeError):
    pass


class ProfileLock:
    """Hold an exclusive, PID-attestable lock for one browser profile."""

    def __init__(self, profile_dir: str | Path) -> None:
        self.profile_dir = Path(profile_dir).resolve()
        self.lock_path = self.profile_dir / LOCK_FILENAME
        self._file = None
        self._lease_id: str | None = None
        self._owner_process: subprocess.Popen[str] | None = None
        self._controller_fd: int | None = None

    def _open_lock_file(self):
        flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            fd = os.open(self.lock_path, flags, 0o600)
        except OSError as exc:
            raise ProfileLockError("profile lock file cannot be opened safely") from exc
        try:
            descriptor_stat = os.fstat(fd)
            if not stat.S_ISREG(descriptor_stat.st_mode) or descriptor_stat.st_nlink != 1:
                raise ProfileLockError("profile lock file is not a private regular file")
            os.fchmod(fd, 0o600)
            return os.fdopen(fd, "r+", encoding="utf-8")
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _descriptor_is_private_regular_file(descriptor_stat: os.stat_result) -> bool:
        return stat.S_ISREG(descriptor_stat.st_mode) and descriptor_stat.st_nlink == 1

    @staticmethod
    def _owner_program() -> str:
        return (
            "import fcntl, os, sys\n"
            "fd = int(sys.argv[1])\n"
            "controller = int(sys.argv[2])\n"
            "try:\n"
            "    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "except BlockingIOError:\n"
            "    print('busy', flush=True)\n"
            "    raise SystemExit(73)\n"
            "print('ready', flush=True)\n"
            "try:\n"
            "    while os.read(controller, 1):\n"
            "        pass\n"
            "finally:\n"
            "    fcntl.lockf(fd, fcntl.LOCK_UN)\n"
        )

    def _stop_owner_process(self) -> None:
        if self._controller_fd is not None:
            try:
                os.close(self._controller_fd)
            except OSError:
                pass
            self._controller_fd = None
        if self._owner_process is not None:
            try:
                self._owner_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._owner_process.kill()
                self._owner_process.wait(timeout=5)
            self._owner_process = None

    def _start_owner_process(self) -> None:
        assert self._file is not None
        control_read, control_write = os.pipe()
        owner: subprocess.Popen[str] | None = None
        try:
            owner = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    self._owner_program(),
                    str(self._file.fileno()),
                    str(control_read),
                ],
                pass_fds=(self._file.fileno(), control_read),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                close_fds=True,
            )
            os.close(control_read)
            control_read = -1
            assert owner.stdout is not None
            readable, _, _ = select.select([owner.stdout], [], [], 5)
            status = owner.stdout.readline().strip() if readable else ""
            owner.stdout.close()
            if status == "busy":
                owner.wait(timeout=5)
                raise ProfileLockError(f"profile already owned: {self.profile_dir}")
            if status != "ready" or owner.poll() is not None:
                raise ProfileLockError("profile lock owner failed to start")
            self._owner_process = owner
            self._controller_fd = control_write
            control_write = -1
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ProfileLockError("profile lock owner failed to start") from exc
        finally:
            if control_read >= 0:
                os.close(control_read)
            if control_write >= 0:
                os.close(control_write)
            if self._owner_process is None and owner is not None:
                if owner.poll() is None:
                    owner.kill()
                owner.wait(timeout=5)

    def __enter__(self) -> ProfileLock:
        self.profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.profile_dir, 0o700)
        self._file = self._open_lock_file()
        try:
            self._start_owner_process()
        except BaseException:
            self._file.close()
            self._file = None
            raise
        try:
            self._file.seek(0)
            self._file.truncate()
            self._lease_id = uuid.uuid4().hex
            assert self._owner_process is not None
            self._file.write(f"pid={self._owner_process.pid}\nlease_id={self._lease_id}\n")
            self._file.flush()
            os.fsync(self._file.fileno())
            self.assert_owned(self.profile_dir, lease_id=self._lease_id)
        except (OSError, ProfileLockError):
            self._stop_owner_process()
            self._file.close()
            self._file = None
            self._lease_id = None
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop_owner_process()
        if self._file is not None:
            self._file.close()
            self._file = None
            self._lease_id = None

    def _lease_marker_matches(self) -> bool:
        assert self._file is not None
        assert self._lease_id is not None
        try:
            self._file.seek(0)
            marker = self._file.read()
        except OSError:
            return False
        if self._owner_process is None:
            return False
        return marker == f"pid={self._owner_process.pid}\nlease_id={self._lease_id}\n"

    def _kernel_lock_owner_pid(self) -> int | None:
        """Return the conflicting whole-file write-lock owner without changing it."""
        assert self._file is not None
        try:
            if sys.platform == "darwin":
                layout = "qqihh"
                request = struct.pack(layout, 0, 0, 0, fcntl.F_WRLCK, os.SEEK_SET)
                response = struct.unpack(
                    layout, fcntl.fcntl(self._file.fileno(), fcntl.F_GETLK, request)
                )
                lock_type, owner_pid = response[3], response[2]
            elif sys.platform.startswith("linux"):
                layout = "hhqqi4x"
                request = struct.pack(layout, fcntl.F_WRLCK, os.SEEK_SET, 0, 0, 0)
                response = struct.unpack(
                    layout, fcntl.fcntl(self._file.fileno(), fcntl.F_GETLK, request)
                )
                lock_type, owner_pid = response[0], response[4]
            else:
                return None
        except (OSError, struct.error):
            return None
        if lock_type != fcntl.F_WRLCK or owner_pid <= 0:
            return None
        return owner_pid

    def _kernel_owner_matches(self) -> bool:
        return (
            self._owner_process is not None
            and self._owner_process.poll() is None
            and self._kernel_lock_owner_pid() == self._owner_process.pid
        )

    def assert_owned(
        self, profile_dir: str | Path, *, lease_id: str | None = None
    ) -> None:
        if (
            self._file is None
            or self._file.closed
            or self._lease_id is None
            or self._owner_process is None
        ):
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
        if (
            not self._descriptor_is_private_regular_file(descriptor_stat)
            or not self._descriptor_is_private_regular_file(pathname_stat)
            or (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
            )
            != (pathname_stat.st_dev, pathname_stat.st_ino)
        ):
            raise ProfileLockError("profile lock pathname was replaced")
        if not self._kernel_owner_matches():
            raise ProfileLockError("profile kernel lock is not owned")
        if not self._lease_marker_matches():
            raise ProfileLockError("profile lock lease marker does not match")
        try:
            pathname_stat = self.lock_path.lstat()
        except FileNotFoundError as exc:
            raise ProfileLockError("profile lock pathname changed during attestation") from exc
        descriptor_stat = os.fstat(self._file.fileno())
        if (
            not self._descriptor_is_private_regular_file(descriptor_stat)
            or not self._descriptor_is_private_regular_file(pathname_stat)
            or (
            descriptor_stat.st_dev,
            descriptor_stat.st_ino,
            )
            != (pathname_stat.st_dev, pathname_stat.st_ino)
        ):
            raise ProfileLockError("profile lock pathname changed during attestation")
        if not self._lease_marker_matches():
            raise ProfileLockError("profile lock lease marker changed during attestation")
        if not self._kernel_owner_matches():
            raise ProfileLockError("profile kernel lock changed during attestation")

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
