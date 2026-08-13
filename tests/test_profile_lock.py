from __future__ import annotations

import fcntl
import subprocess
import sys
from pathlib import Path

import pytest

from event_lead_ops.profile_lock import ProfileLock, ProfileLockError


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


def test_profile_lock_rejects_stale_object_after_kernel_unlock(tmp_path: Path):
    profile = tmp_path / "craigslist"
    first = ProfileLock(profile)
    with first:
        assert first._file is not None
        fcntl.flock(first._file.fileno(), fcntl.LOCK_UN)
        with ProfileLock(profile):
            with pytest.raises(ProfileLockError, match="kernel lock"):
                first.assert_owned(profile)
