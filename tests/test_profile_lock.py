from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from event_lead_ops.profile_lock import LOCK_FILENAME, ProfileLock, ProfileLockError


def stop_lock_owner(lock: ProfileLock) -> None:
    assert lock._owner_process is not None
    lock._owner_process.terminate()
    lock._owner_process.wait(timeout=5)


def test_profile_lock_is_exclusive_across_processes(tmp_path: Path):
    profile = tmp_path / "facebook"
    with ProfileLock(profile):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "event_lead_ops.profile_lock",
                "--profile",
                str(profile),
                "--",
                sys.executable,
                "-c",
                "print('must not run')",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 73
    assert "already owned" in result.stderr
    assert "must not run" not in result.stdout


def test_profile_lock_releases_after_context(tmp_path: Path):
    profile = tmp_path / "craigslist"
    with ProfileLock(profile):
        with pytest.raises(ProfileLockError):
            with ProfileLock(profile):
                pass
    with ProfileLock(profile):
        assert (profile / ".event-lead-ops.lock").exists()


def test_profile_lock_attests_exact_profile_only_while_held(tmp_path: Path):
    profile = tmp_path / "craigslist"
    lock = ProfileLock(profile)
    with lock:
        lock.assert_owned(profile)
        with pytest.raises(ProfileLockError, match="different profile"):
            lock.assert_owned(tmp_path / "facebook")
    with pytest.raises(ProfileLockError, match="not held"):
        lock.assert_owned(profile)


def test_profile_lock_rejects_replaced_pathname(tmp_path: Path):
    profile = tmp_path / "craigslist"
    with ProfileLock(profile) as first:
        first.lock_path.unlink()
        with ProfileLock(profile) as second:
            second.assert_owned(profile)
            with pytest.raises(ProfileLockError, match="replaced"):
                first.assert_owned(profile)


def test_profile_lock_rejects_preexisting_symlink_without_touching_target(tmp_path: Path):
    profile = tmp_path / "craigslist"
    profile.mkdir()
    target = tmp_path / "target"
    target.write_text("do-not-touch", encoding="utf-8")
    (profile / LOCK_FILENAME).symlink_to(target)

    with pytest.raises(ProfileLockError):
        with ProfileLock(profile):
            pass

    assert target.read_text(encoding="utf-8") == "do-not-touch"


def test_profile_lock_rejects_preexisting_hardlink_without_touching_target(tmp_path: Path):
    profile = tmp_path / "craigslist"
    profile.mkdir()
    target = tmp_path / "target"
    target.write_text("do-not-touch", encoding="utf-8")
    (profile / LOCK_FILENAME).hardlink_to(target)

    with pytest.raises(ProfileLockError):
        with ProfileLock(profile):
            pass

    assert target.read_text(encoding="utf-8") == "do-not-touch"


def test_profile_lock_rejects_stale_object_after_kernel_unlock(tmp_path: Path):
    profile = tmp_path / "craigslist"
    first = ProfileLock(profile)
    with first:
        stop_lock_owner(first)
        with ProfileLock(profile):
            with pytest.raises(ProfileLockError, match="kernel lock"):
                first.assert_owned(profile)


def test_profile_lock_rejects_kernel_unlock_without_competing_owner(tmp_path: Path):
    profile = tmp_path / "craigslist"
    lock = ProfileLock(profile)
    with lock:
        stop_lock_owner(lock)
        with pytest.raises(ProfileLockError, match="kernel lock"):
            lock.assert_owned(profile)
        with ProfileLock(profile):
            pass


def test_profile_lock_rejects_different_owner_with_unchanged_marker(tmp_path: Path):
    profile = tmp_path / "craigslist"
    lock = ProfileLock(profile)
    with lock:
        stop_lock_owner(lock)
        contender = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "import fcntl, os, sys, time; "
                    "fd=os.open(sys.argv[1], os.O_RDWR); "
                    "fcntl.lockf(fd, fcntl.LOCK_EX); "
                    "print('ready', flush=True); time.sleep(30)"
                ),
                str(lock.lock_path),
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert contender.stdout is not None
            assert contender.stdout.readline().strip() == "ready"
            with pytest.raises(ProfileLockError, match="kernel lock"):
                lock.assert_owned(profile)
        finally:
            contender.terminate()
            contender.wait(timeout=5)


def test_profile_lock_rejects_changed_lease_marker(tmp_path: Path):
    profile = tmp_path / "craigslist"
    with ProfileLock(profile) as lock:
        lock.lock_path.write_text("pid=other\nlease_id=other\n")
        with pytest.raises(ProfileLockError, match="lease marker"):
            lock.assert_owned(profile)


def test_profile_lock_owner_query_failure_rejects_ownership(tmp_path: Path, monkeypatch):
    profile = tmp_path / "craigslist"
    with ProfileLock(profile) as lock:
        monkeypatch.setattr(lock, "_kernel_lock_owner_pid", lambda: None)
        with pytest.raises(ProfileLockError, match="kernel lock"):
            lock.assert_owned(profile)


def test_profile_lock_failed_startup_attestation_releases_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    profile = tmp_path / "craigslist"
    original = ProfileLock._kernel_lock_owner_pid
    monkeypatch.setattr(ProfileLock, "_kernel_lock_owner_pid", lambda self: None)
    with pytest.raises(ProfileLockError, match="kernel lock"):
        with ProfileLock(profile):
            pass
    monkeypatch.setattr(ProfileLock, "_kernel_lock_owner_pid", original)
    with ProfileLock(profile):
        pass


def test_profile_lock_marker_identifies_kernel_owner_and_lease(tmp_path: Path):
    profile = tmp_path / "craigslist"
    with ProfileLock(profile) as lock:
        assert lock._owner_process is not None
        marker = lock.lock_path.read_text()
        assert marker == f"pid={lock._owner_process.pid}\nlease_id={lock.lease_id}\n"
