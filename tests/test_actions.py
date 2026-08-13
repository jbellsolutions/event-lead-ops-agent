from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from event_lead_ops.db import (
    begin_approved_action,
    create_approval,
    create_proposed_action,
    create_retry_proposed_action,
    finish_action,
    iso,
    mark_action_submitting,
    record_authorized_approver,
    record_source_health,
    record_source_policy,
    upsert_campaign,
)
from event_lead_ops.models import (
    ExecutionReservation,
    HealthStatus,
    OperationMode,
    ProposedAction,
    RuntimeIdentity,
)
from event_lead_ops.policy import PolicyViolation, canonical_json, payload_hash
from event_lead_ops.profile_lock import ProfileLock

PAYLOAD = {
    "title": "Tampa event package",
    "description": "A synthetic test payload.",
    "price": 500,
    "location": "Tampa, FL",
}
APPROVER = "U_SYNTHETIC_OWNER"


def runtime_identity(db) -> RuntimeIdentity:
    database_path = db.execute("PRAGMA database_list").fetchone()[2]
    root = Path(database_path).parent
    profile = root / "profiles" / "craigslist"
    evidence_root = root / "artifacts" / "craigslist"
    evidence_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    return RuntimeIdentity(
        source="craigslist",
        account_alias="default",
        route="direct-vps",
        provider="playwright",
        egress_identity="synthetic-vps-egress",
        proxy_identity="none",
        profile_dir=str(profile.resolve()),
        browser_major_version="synthetic-1",
        display_mode="headed",
        viewport="1440x900",
        evidence_root=str(evidence_root.resolve()),
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("route", ""),
        ("provider", "   "),
        ("egress_identity", ""),
        ("proxy_identity", ""),
        ("browser_major_version", ""),
        ("display_mode", ""),
        ("viewport", ""),
        ("profile_dir", "relative/profile"),
        ("evidence_root", "relative/evidence"),
    ],
)
def test_runtime_identity_rejects_empty_or_relative_fields(db, field, value):
    values = runtime_identity(db).as_dict()
    values[field] = value
    with pytest.raises(ValueError, match="runtime identity"):
        RuntimeIdentity(**values)


def configure_source(
    db,
    *,
    mode: OperationMode = OperationMode.APPROVED_WRITE,
    certified_at: datetime | None = None,
    ttl_hours: int = 24,
    timeout_minutes: int = 15,
) -> RuntimeIdentity:
    certified_at = certified_at or datetime.now(UTC)
    runtime = runtime_identity(db)
    record_source_policy(
        db,
        source="craigslist",
        mode=mode,
        certification_ttl_hours=ttl_hours,
        execution_timeout_minutes=timeout_minutes,
    )
    with ProfileLock(runtime.profile_dir) as lock:
        record_source_health(
            db,
            source="craigslist",
            status=HealthStatus.HEALTHY,
            route="direct-vps",
            certified_at=certified_at,
            runtime=runtime,
            profile_lock=lock,
        )
    return runtime


def write_evidence(
    runtime: RuntimeIdentity,
    *,
    action_id: str,
    proposed: ProposedAction,
    outcome: str,
    platform_external_id: str | None = None,
    platform_url: str | None = None,
    name: str = "confirmation.json",
) -> Path:
    evidence = Path(runtime.evidence_root) / name
    evidence.write_text(
        json.dumps(
            {
                "source": proposed.source,
                "account_alias": proposed.account_alias,
                "proposed_action_id": proposed.id,
                "action_id": action_id,
                "runtime_fingerprint": runtime.fingerprint,
                "outcome": outcome,
                "platform_external_id": platform_external_id,
                "platform_url": platform_url,
            },
            sort_keys=True,
        )
    )
    evidence.chmod(0o600)
    return evidence


def begin_action(db, *, proposed, approval, runtime, **kwargs):
    with ProfileLock(runtime.profile_dir) as lock:
        return begin_approved_action(
            db,
            proposed=proposed,
            current_payload=kwargs.pop("current_payload", proposed.payload),
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
            **kwargs,
        )


@contextmanager
def executing_action(db, *, proposed, approval, runtime, **kwargs):
    with ProfileLock(runtime.profile_dir) as lock:
        reservation = begin_approved_action(
            db,
            proposed=proposed,
            current_payload=kwargs.pop("current_payload", proposed.payload),
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
            **kwargs,
        )
        yield reservation.action_id, reservation, lock


def proposal(db, payload: dict | None = None):
    upsert_campaign(
        db,
        campaign_id="campaign-synthetic",
        name="Synthetic campaign",
        business_alias="synthetic-business",
        offer_id="synthetic-offer",
    )
    return create_proposed_action(
        db,
        source="craigslist",
        action_type="publish_listing",
        payload=payload or PAYLOAD,
        campaign_id="campaign-synthetic",
    )


def approve(db, proposed, *, expires_at: datetime | None = None):
    record_authorized_approver(
        db,
        external_user_id=APPROVER,
        operator_alias="owner",
    )
    return create_approval(
        db,
        proposed,
        approver=APPROVER,
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=30),
    )


def test_approved_action_executes_exactly_once(db, tmp_path):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with ProfileLock(runtime.profile_dir) as lock:
        reservation = begin_approved_action(
            db,
            proposed=proposed,
            current_payload=PAYLOAD,
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
        )
        action_id = reservation.action_id
        assert reservation.should_execute is True
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        platform_url = (
            "https://tampa.craigslist.org/evg/d/tampa-test/1234567890.html"
        )
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="succeeded",
            platform_external_id="1234567890",
            platform_url=platform_url,
        )
        finish_action(
            db,
            action_id,
            status="succeeded",
            platform_external_id="1234567890",
            platform_url=platform_url,
            evidence_path=str(evidence),
            runtime=runtime,
            profile_lock=lock,
        )

    duplicate = begin_action(
        db,
        proposed=proposed,
        approval=approval,
        runtime=runtime,
    )
    assert duplicate.action_id == action_id
    assert duplicate.should_execute is False
    assert db.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 1


def test_execution_reservation_uses_immutable_database_payload_snapshot(db):
    approved_payload = {
        **PAYLOAD,
        "details": {"flags": [1, True]},
    }
    approved_payload_json = canonical_json(approved_payload)
    approved_snapshot = json.loads(approved_payload_json)
    runtime = configure_source(db)
    proposed = proposal(db, approved_payload)
    approval = approve(db, proposed)
    current_payload = json.loads(approved_payload_json)

    with ProfileLock(runtime.profile_dir) as lock:
        reservation = begin_approved_action(
            db,
            proposed=proposed,
            current_payload=current_payload,
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
        )

        proposed.payload["price"] = 1
        proposed.payload["details"]["flags"][0] = 2
        current_payload["price"] = 2
        current_payload["details"]["flags"][1] = False

        assert reservation.should_execute is True
        assert reservation.payload_json == approved_payload_json
        assert reservation.payload["price"] == approved_snapshot["price"]
        assert reservation.payload["details"]["flags"] == (1, True)
        with pytest.raises(TypeError):
            reservation.payload["price"] = 3
        with pytest.raises(TypeError):
            reservation.payload["details"]["flags"][0] = 3

        stored = db.execute(
            """SELECT payload_json, payload_hash, execution_token_hash
            FROM actions WHERE id=?""",
            (reservation.action_id,),
        ).fetchone()
        assert stored["payload_json"] == approved_payload_json
        assert stored["payload_hash"] == payload_hash(approved_snapshot)
        assert reservation.execution_token not in tuple(stored)
        assert stored["execution_token_hash"] == hashlib.sha256(
            reservation.execution_token.encode()
        ).hexdigest()

        altered = ExecutionReservation(
            action_id=reservation.action_id,
            payload_json=canonical_json({**approved_snapshot, "price": 1}),
            payload_hash=reservation.payload_hash,
            execution_token=reservation.execution_token,
        )
        with pytest.raises(RuntimeError, match="payload does not match"):
            mark_action_submitting(
                db,
                altered,
                runtime=runtime,
                profile_lock=lock,
            )

        class HostileReservation:
            action_id = reservation.action_id
            payload_json = reservation.payload_json
            payload_hash = reservation.payload_hash
            execution_token = reservation.execution_token
            should_execute = True
            payload = {"price": "attacker-controlled"}

        class ReservationSubclass(ExecutionReservation):
            pass

        class HostileString(str):
            def __eq__(self, other):
                return True

        hostile_string_claims = tuple(
            ExecutionReservation(
                action_id=(
                    HostileString(reservation.action_id)
                    if field == "action_id"
                    else reservation.action_id
                ),
                payload_json=(
                    HostileString(reservation.payload_json)
                    if field == "payload_json"
                    else reservation.payload_json
                ),
                payload_hash=(
                    HostileString(reservation.payload_hash)
                    if field == "payload_hash"
                    else reservation.payload_hash
                ),
                execution_token=(
                    HostileString(reservation.execution_token)
                    if field == "execution_token"
                    else reservation.execution_token
                ),
            )
            for field in (
                "action_id",
                "payload_json",
                "payload_hash",
                "execution_token",
            )
        )
        forged_claims = (
            HostileReservation(),
            ReservationSubclass(
                action_id=reservation.action_id,
                payload_json=reservation.payload_json,
                payload_hash=reservation.payload_hash,
                execution_token=reservation.execution_token,
            ),
            *hostile_string_claims,
        )
        for forged in forged_claims:
            with pytest.raises(TypeError, match="exact|plain built-in"):
                mark_action_submitting(
                    db,
                    forged,
                    runtime=runtime,
                    profile_lock=lock,
                )
            assert db.execute(
                "SELECT execution_token_hash FROM actions WHERE id=?",
                (reservation.action_id,),
            ).fetchone()[0] is not None

        missing_token = ExecutionReservation(
            action_id=reservation.action_id,
            payload_json=reservation.payload_json,
            payload_hash=reservation.payload_hash,
        )
        with pytest.raises(RuntimeError, match="execution claim"):
            mark_action_submitting(
                db,
                missing_token,
                runtime=runtime,
                profile_lock=lock,
            )
        assert db.execute(
            "SELECT execution_token_hash FROM actions WHERE id=?",
            (reservation.action_id,),
        ).fetchone()[0] is not None

        submitted_payload = mark_action_submitting(
            db,
            reservation,
            runtime=runtime,
            profile_lock=lock,
        )
        assert submitted_payload == reservation.payload
        with pytest.raises(TypeError):
            submitted_payload["price"] = "attacker-controlled"
        assert db.execute(
            "SELECT execution_token_hash FROM actions WHERE id=?",
            (reservation.action_id,),
        ).fetchone()[0] is None
        with pytest.raises(RuntimeError, match="execution claim"):
            mark_action_submitting(
                db,
                reservation,
                runtime=runtime,
                profile_lock=lock,
            )


def test_duplicate_or_forged_reservation_cannot_cross_submit_boundary(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)

    with ProfileLock(runtime.profile_dir) as lock:
        reservation = begin_approved_action(
            db,
            proposed=proposed,
            current_payload=PAYLOAD,
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
        )
        duplicate = begin_approved_action(
            db,
            proposed=proposed,
            current_payload=PAYLOAD,
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
        )
        assert duplicate.should_execute is False

        with pytest.raises(RuntimeError, match="execution claim"):
            mark_action_submitting(
                db,
                ExecutionReservation(
                    action_id=duplicate.action_id,
                    payload_json=duplicate.payload_json,
                    payload_hash=duplicate.payload_hash,
                    execution_token="forged-execution-token",
                ),
                runtime=runtime,
                profile_lock=lock,
            )

        submitted_payload = mark_action_submitting(
            db,
            reservation,
            runtime=runtime,
            profile_lock=lock,
        )
        assert submitted_payload == reservation.payload


def test_forged_proposed_action_cannot_be_approved(db):
    proposed = proposal(db)
    forged = ProposedAction(
        id=proposed.id,
        source=proposed.source,
        action_type=proposed.action_type,
        payload={**PAYLOAD, "price": 1},
        payload_hash="forged",
        idempotency_key=proposed.idempotency_key,
        campaign_id=proposed.campaign_id,
    )
    with pytest.raises(RuntimeError, match="stored payload"):
        approve(db, forged)


def test_unauthorized_approver_is_rejected(db):
    proposed = proposal(db)
    with pytest.raises(PermissionError, match="not authorized"):
        create_approval(
            db,
            proposed,
            approver="U_NOT_ALLOWED",
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )


def test_database_health_is_required(db):
    record_source_policy(
        db,
        source="craigslist",
        mode=OperationMode.APPROVED_WRITE,
    )
    runtime = runtime_identity(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with pytest.raises(RuntimeError, match="database source health"):
        begin_action(db, proposed=proposed, approval=approval, runtime=runtime)


def test_database_mode_is_authoritative(db):
    runtime = configure_source(db, mode=OperationMode.OBSERVE)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with pytest.raises(PolicyViolation, match="mode"):
        begin_action(db, proposed=proposed, approval=approval, runtime=runtime)


def test_expired_route_certification_blocks_write(db):
    runtime = configure_source(
        db,
        certified_at=datetime.now(UTC) - timedelta(hours=2),
        ttl_hours=1,
    )
    proposed = proposal(db)
    approval = approve(db, proposed)
    with pytest.raises(RuntimeError, match="certification expired"):
        begin_action(db, proposed=proposed, approval=approval, runtime=runtime)


def test_source_policy_rejects_certification_ttl_over_24_hours(db):
    with pytest.raises(ValueError, match="at most 24 hours"):
        record_source_policy(
            db,
            source="craigslist",
            mode=OperationMode.OBSERVE,
            certification_ttl_hours=25,
        )


def test_health_certification_rejects_future_timestamp(db):
    runtime = runtime_identity(db)
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(ValueError, match="future"):
            record_source_health(
                db,
                source="craigslist",
                status=HealthStatus.HEALTHY,
                route=runtime.route,
                certified_at=datetime.now(UTC) + timedelta(minutes=1),
                runtime=runtime,
                profile_lock=lock,
            )


def test_health_certification_rejects_naive_timestamp(db):
    runtime = runtime_identity(db)
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(ValueError, match="timezone-aware"):
            record_source_health(
                db,
                source="craigslist",
                status=HealthStatus.HEALTHY,
                route=runtime.route,
                certified_at=datetime.now(),
                runtime=runtime,
                profile_lock=lock,
            )


def test_approval_expiry_must_be_positive_and_at_most_30_minutes(db):
    proposed = proposal(db)
    record_authorized_approver(
        db,
        external_user_id=APPROVER,
        operator_alias="owner",
    )
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="future"):
        create_approval(
            db,
            proposed,
            approver=APPROVER,
            expires_at=now - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="30 minutes"):
        create_approval(
            db,
            proposed,
            approver=APPROVER,
            expires_at=now + timedelta(minutes=31),
        )


def test_approval_expiry_rejects_naive_timestamp(db):
    proposed = proposal(db)
    record_authorized_approver(
        db,
        external_user_id=APPROVER,
        operator_alias="owner",
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        create_approval(
            db,
            proposed,
            approver=APPROVER,
            expires_at=datetime.now(),
        )


def test_execution_reservation_rejects_naive_clock(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(ValueError, match="timezone-aware"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=PAYLOAD,
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
                now=datetime.now(),
            )


def test_runtime_mismatch_or_missing_lock_blocks_write(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    changed = replace(runtime, route="changed-route")
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="certified runtime"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=PAYLOAD,
                approval=approval,
                runtime=changed,
                profile_lock=lock,
            )
    changed_egress = replace(runtime, egress_identity="different-egress")
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="certified runtime"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=PAYLOAD,
                approval=approval,
                runtime=changed_egress,
                profile_lock=lock,
            )
    released = ProfileLock(runtime.profile_dir)
    with pytest.raises(Exception, match="not held"):
        begin_approved_action(
            db,
            proposed=proposed,
            current_payload=PAYLOAD,
            approval=approval,
            runtime=runtime,
            profile_lock=released,
        )


def test_edited_proposed_payload_cannot_reach_executor(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    edited = replace(proposed, payload={**PAYLOAD, "price": 1})
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="executor payload"):
            begin_approved_action(
                db,
                proposed=edited,
                current_payload=PAYLOAD,
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
            )


@pytest.mark.parametrize(
    ("approved_value", "edited_value"),
    [
        (1, True),
        (0, False),
        (1, 1.0),
        ({"nested": [1, True]}, {"nested": [1, 1]}),
    ],
)
def test_json_distinct_proposed_payload_cannot_reach_executor(
    db, approved_value, edited_value
):
    approved_payload = {**PAYLOAD, "value": approved_value}
    runtime = configure_source(db)
    proposed = proposal(db, approved_payload)
    approval = approve(db, proposed)
    edited = replace(proposed, payload={**approved_payload, "value": edited_value})
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="executor payload"):
            begin_approved_action(
                db,
                proposed=edited,
                current_payload=approved_payload,
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
            )


def test_payload_key_order_does_not_change_approved_json_identity(db):
    approved_payload = {"title": "Synthetic", "price": 100, "location": "Tampa"}
    runtime = configure_source(db)
    proposed = proposal(db, approved_payload)
    approval = approve(db, proposed)
    reordered_payload = {
        "location": approved_payload["location"],
        "price": approved_payload["price"],
        "title": approved_payload["title"],
    }
    with ProfileLock(runtime.profile_dir) as lock:
        reservation = begin_approved_action(
            db,
            proposed=replace(proposed, payload=reordered_payload),
            current_payload=reordered_payload,
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
        )
    stored = db.execute(
        "SELECT proposed_action_id FROM actions WHERE id=?", (reservation.action_id,)
    ).fetchone()
    assert reservation.should_execute is True
    assert stored["proposed_action_id"] == proposed.id


def test_edited_current_payload_cannot_reach_executor(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="executor payload"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload={**PAYLOAD, "price": 1},
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
            )


@pytest.mark.parametrize(
    ("approved_value", "edited_value"),
    [
        (1, True),
        (0, False),
        (1, 1.0),
        ({"nested": [1, True]}, {"nested": [1, 1]}),
    ],
)
def test_json_distinct_current_payload_cannot_reach_executor(
    db, approved_value, edited_value
):
    approved_payload = {**PAYLOAD, "value": approved_value}
    runtime = configure_source(db)
    proposed = proposal(db, approved_payload)
    approval = approve(db, proposed)
    edited_payload = {**approved_payload, "value": edited_value}
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="executor payload"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=edited_payload,
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
            )


def test_execution_rejects_future_dated_certification_in_database(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    db.execute(
        "UPDATE source_health SET certified_at=? WHERE source=? AND account_alias=?",
        (
            iso(datetime.now(UTC) + timedelta(days=1)),
            proposed.source,
            proposed.account_alias,
        ),
    )
    db.commit()
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="future-dated"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=PAYLOAD,
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
            )


def test_naive_database_certification_fails_closed_without_consuming_approval(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    db.execute(
        "UPDATE source_health SET certified_at=? WHERE source=? AND account_alias=?",
        ("2026-08-13T04:00:00", proposed.source, proposed.account_alias),
    )
    db.commit()
    with ProfileLock(runtime.profile_dir) as lock:
        with pytest.raises(RuntimeError, match="source_health.certified_at"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=PAYLOAD,
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
            )
    assert db.execute("SELECT COUNT(*) FROM actions").fetchone()[0] == 0
    assert db.execute(
        "SELECT status FROM approvals WHERE id=?", (approval.approval_id,)
    ).fetchone()[0] == "approved"
    assert db.execute(
        "SELECT status FROM proposed_actions WHERE id=?", (proposed.id,)
    ).fetchone()[0] == "approved"


def test_success_requires_durable_submission_marker(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        with pytest.raises(ValueError, match="submission marker"):
            finish_action(
                db,
                action_id,
                status="succeeded",
                platform_external_id="1234567890",
                platform_url="https://tampa.craigslist.org/evg/d/test/1234567890.html",
                runtime=runtime,
                profile_lock=lock,
            )


def test_success_requires_platform_identity_and_evidence(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        with pytest.raises(ValueError, match="requires an existing evidence"):
            finish_action(
                db,
                action_id,
                status="succeeded",
                platform_external_id="1234567890",
                platform_url=(
                    "https://tampa.craigslist.org/evg/d/test/1234567890.html"
                ),
                runtime=runtime,
                profile_lock=lock,
            )


def test_success_requires_https_platform_url(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        platform_url = "http://localhost/result"
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="succeeded",
            platform_external_id="x",
            platform_url=platform_url,
        )
        with pytest.raises(ValueError, match="must use HTTPS"):
            finish_action(
                db,
                action_id,
                status="succeeded",
                platform_external_id="x",
                platform_url=platform_url,
                evidence_path=str(evidence),
                runtime=runtime,
                profile_lock=lock,
            )


def test_success_rejects_off_platform_or_mismatched_identity(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        off_platform_url = "https://example.com/evg/d/test/1234567890.html"
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="succeeded",
            platform_external_id="1234567890",
            platform_url=off_platform_url,
        )
        with pytest.raises(ValueError, match="Craigslist URL"):
            finish_action(
                db,
                action_id,
                status="succeeded",
                platform_external_id="1234567890",
                platform_url=off_platform_url,
                evidence_path=str(evidence),
                runtime=runtime,
                profile_lock=lock,
            )
        mismatched_url = "https://tampa.craigslist.org/evg/d/test/1234567890.html"
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="succeeded",
            platform_external_id="9999999999",
            platform_url=mismatched_url,
        )
        with pytest.raises(ValueError, match="does not match"):
            finish_action(
                db,
                action_id,
                status="succeeded",
                platform_external_id="9999999999",
                platform_url=mismatched_url,
                evidence_path=str(evidence),
                runtime=runtime,
                profile_lock=lock,
            )


def test_success_requires_existing_evidence_file(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        with pytest.raises(ValueError, match="existing evidence"):
            finish_action(
                db,
                action_id,
                status="succeeded",
                platform_external_id="1234567890",
                platform_url="https://tampa.craigslist.org/evg/d/test/1234567890.html",
                evidence_path=str(Path(runtime.evidence_root) / "missing.json"),
                runtime=runtime,
                profile_lock=lock,
            )


def test_success_rejects_evidence_manifest_for_another_action(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        platform_url = "https://tampa.craigslist.org/evg/d/test/1234567890.html"
        evidence = write_evidence(
            runtime,
            action_id="different-action",
            proposed=proposed,
            outcome="succeeded",
            platform_external_id="1234567890",
            platform_url=platform_url,
        )
        with pytest.raises(ValueError, match="manifest does not match"):
            finish_action(
                db,
                action_id,
                status="succeeded",
                platform_external_id="1234567890",
                platform_url=platform_url,
                evidence_path=str(evidence),
                runtime=runtime,
                profile_lock=lock,
            )


def test_unrelated_approval_cannot_reconcile_stale_execution(db):
    start = datetime.now(UTC) - timedelta(minutes=5)
    runtime = configure_source(db, timeout_minutes=1, certified_at=start)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with ProfileLock(runtime.profile_dir) as lock:
        reservation = begin_approved_action(
            db,
            proposed=proposed,
            current_payload=PAYLOAD,
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
            now=start,
        )
        action_id = reservation.action_id
        forged = type(approval)(
            approval_id="unrelated",
            proposed_action_id=proposed.id,
            approved_payload_hash=proposed.payload_hash,
            approver=approval.approver,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        with pytest.raises(RuntimeError, match="approval is not available"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=PAYLOAD,
                approval=forged,
                runtime=runtime,
                profile_lock=lock,
            )
    status = db.execute(
        "SELECT status FROM actions WHERE id=?", (action_id,)
    ).fetchone()[0]
    assert status == "executing"


def test_campaign_cooldown_allows_idempotent_readback(db):
    first = proposal(db)
    second = proposal(db)
    assert second.id == first.id


def test_campaign_cooldown_blocks_variant_listing(db):
    proposal(db)
    with pytest.raises(RuntimeError, match="cooldown"):
        proposal(db, {**PAYLOAD, "title": "Slightly edited title"})


def test_failed_action_requires_evidenced_confirmed_no_submit(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        with pytest.raises(ValueError, match="confirmed_no_submit"):
            finish_action(
                db,
                action_id,
                status="failed",
                error_class="network_timeout",
                runtime=runtime,
                profile_lock=lock,
            )


def test_failed_action_rejects_platform_result_identity(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="confirmed_no_submit",
            name="confirmed-no-submit.json",
        )
        with pytest.raises(ValueError, match="cannot include"):
            finish_action(
                db,
                action_id,
                status="failed",
                error_class="confirmed_no_submit",
                platform_external_id="1234567890",
                platform_url="https://tampa.craigslist.org/evg/d/test/1234567890.html",
                evidence_path=str(evidence),
                runtime=runtime,
                profile_lock=lock,
            )


def test_marked_submission_cannot_be_recorded_as_confirmed_no_submit(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="confirmed_no_submit",
            name="invalid-no-submit.json",
        )
        with pytest.raises(ValueError, match="cannot be recorded"):
            finish_action(
                db,
                action_id,
                status="failed",
                error_class="confirmed_no_submit",
                evidence_path=str(evidence),
                runtime=runtime,
                profile_lock=lock,
            )
        finish_action(
            db,
            action_id,
            status="needs_reconciliation",
            error_class="ambiguous_after_submit",
            runtime=runtime,
            profile_lock=lock,
        )


def test_reconciliation_rejects_off_platform_identity(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        mark_action_submitting(db, reservation, runtime=runtime, profile_lock=lock)
        with pytest.raises(ValueError, match="Craigslist URL"):
            finish_action(
                db,
                action_id,
                status="needs_reconciliation",
                error_class="ambiguous_after_submit",
                platform_external_id="1234567890",
                platform_url="https://example.com/evg/d/test/1234567890.html",
                runtime=runtime,
                profile_lock=lock,
            )


def test_listing_retry_honors_persisted_campaign_cooldown(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="confirmed_no_submit",
            name="confirmed-no-submit.json",
        )
        finish_action(
            db,
            action_id,
            status="failed",
            error_class="confirmed_no_submit",
            evidence_path=str(evidence),
            runtime=runtime,
            profile_lock=lock,
        )
        terminal = db.execute(
            "SELECT status, execution_token_hash FROM actions WHERE id=?", (action_id,)
        ).fetchone()
        assert tuple(terminal) == ("failed", None)
        with pytest.raises(sqlite3.IntegrityError, match="cannot reopen execution"):
            db.execute("UPDATE actions SET status='executing' WHERE id=?", (action_id,))
        db.rollback()

    with pytest.raises(RuntimeError, match="cooldown"):
        create_retry_proposed_action(db, proposed.id)
    with pytest.raises(RuntimeError, match="cooldown"):
        proposal(db, {**PAYLOAD, "title": "Fresh variant cannot bypass retry"})
    db.execute(
        "UPDATE actions SET finished_at=? WHERE id=?",
        (iso(datetime.now(UTC) - timedelta(hours=25)), action_id),
    )
    db.commit()
    retry = create_retry_proposed_action(db, proposed.id)
    assert retry.retry_of == proposed.id
    assert retry.attempt == 2
    assert retry.idempotency_key != proposed.idempotency_key


def test_retry_rejects_evidence_mutated_after_failure(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="confirmed_no_submit",
            name="confirmed-no-submit.json",
        )
        finish_action(
            db,
            action_id,
            status="failed",
            error_class="confirmed_no_submit",
            evidence_path=str(evidence),
            runtime=runtime,
            profile_lock=lock,
        )
    evidence.write_text('{"tampered": true}')
    evidence.chmod(0o600)
    db.execute(
        "UPDATE actions SET finished_at=? WHERE id=?",
        (iso(datetime.now(UTC) - timedelta(hours=25)), action_id),
    )
    db.commit()
    with pytest.raises(RuntimeError, match="evidence changed"):
        create_retry_proposed_action(db, proposed.id)


def test_retry_blocks_when_fresh_variant_already_pending(db):
    runtime = configure_source(db)
    proposed = proposal(db)
    approval = approve(db, proposed)
    with executing_action(
        db, proposed=proposed, approval=approval, runtime=runtime
    ) as (action_id, reservation, lock):
        evidence = write_evidence(
            runtime,
            action_id=action_id,
            proposed=proposed,
            outcome="confirmed_no_submit",
            name="confirmed-no-submit.json",
        )
        finish_action(
            db,
            action_id,
            status="failed",
            error_class="confirmed_no_submit",
            evidence_path=str(evidence),
            runtime=runtime,
            profile_lock=lock,
        )
    old = iso(datetime.now(UTC) - timedelta(hours=25))
    db.execute("UPDATE actions SET finished_at=? WHERE id=?", (old, action_id))
    db.commit()
    fresh = proposal(db, {**PAYLOAD, "title": "Fresh after cooldown"})
    assert fresh.id != proposed.id
    with pytest.raises(RuntimeError, match="another listing proposal"):
        create_retry_proposed_action(db, proposed.id)


def test_stale_execution_moves_to_reconciliation(db):
    start = datetime.now(UTC)
    runtime = configure_source(db, certified_at=start, ttl_hours=24, timeout_minutes=1)
    proposed = proposal(db)
    approval = approve(db, proposed, expires_at=start + timedelta(minutes=30))
    with ProfileLock(runtime.profile_dir) as lock:
        reservation = begin_approved_action(
            db,
            proposed=proposed,
            current_payload=PAYLOAD,
            approval=approval,
            runtime=runtime,
            profile_lock=lock,
            now=start,
        )
        action_id = reservation.action_id
        with pytest.raises(RuntimeError, match="requires reconciliation"):
            begin_approved_action(
                db,
                proposed=proposed,
                current_payload=PAYLOAD,
                approval=approval,
                runtime=runtime,
                profile_lock=lock,
                now=start + timedelta(minutes=2),
            )
    terminal = db.execute(
        "SELECT status, execution_token_hash FROM actions WHERE id=?", (action_id,)
    ).fetchone()
    assert tuple(terminal) == ("needs_reconciliation", None)
