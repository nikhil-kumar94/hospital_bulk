"""Tests for the batch failure-resolution policies (app/failure_policy.py).

These policies decide what happens to a creation batch AFTER the create
fan-out when AT LEAST ONE create failed. Each policy performs its batch-level
downstream action and returns a PolicyOutcome.

No real network calls are made: a lightweight duck-typed FakeClient records
which batch ids were activated or deleted.
"""
import pytest

from app.failure_policy import (
    FailurePolicy,
    LeavePolicy,
    PartialActivatePolicy,
    PolicyOutcome,
    RollbackPolicy,
    get_failure_policy,
)


class FakeClient:
    """Duck-typed stand-in for DirectoryClient that records calls."""

    def __init__(self):
        self.activated = []
        self.deleted = []

    async def activate_batch(self, batch_id):
        self.activated.append(batch_id)

    async def delete_batch(self, batch_id):
        self.deleted.append(batch_id)


async def test_rollback_deletes_and_labels():
    fake = FakeClient()
    out = await RollbackPolicy().resolve("b", fake)
    assert fake.deleted == ["b"]
    assert fake.activated == []
    assert out == PolicyOutcome(False, "rolled_back")


async def test_leave_is_a_no_op():
    fake = FakeClient()
    out = await LeavePolicy().resolve("b", fake)
    assert fake.deleted == []
    assert fake.activated == []
    assert out == PolicyOutcome(False, "created")


async def test_partial_activates():
    fake = FakeClient()
    out = await PartialActivatePolicy().resolve("b", fake)
    assert fake.activated == ["b"]
    assert fake.deleted == []
    assert out == PolicyOutcome(True, "created_and_activated")


def test_factory_maps_names():
    assert get_failure_policy("rollback").name == "rollback"
    assert get_failure_policy("leave").name == "leave"
    assert get_failure_policy("partial").name == "partial"


def test_factory_returns_matching_types():
    assert isinstance(get_failure_policy("rollback"), RollbackPolicy)
    assert isinstance(get_failure_policy("leave"), LeavePolicy)
    assert isinstance(get_failure_policy("partial"), PartialActivatePolicy)


def test_factory_rejects_unknown():
    with pytest.raises(ValueError):
        get_failure_policy("nope")


def test_policies_are_failure_policies():
    assert isinstance(RollbackPolicy(), FailurePolicy)
    assert isinstance(LeavePolicy(), FailurePolicy)
    assert isinstance(PartialActivatePolicy(), FailurePolicy)


def test_abstract_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        FailurePolicy()


def test_factory_returns_fresh_instances():
    assert get_failure_policy("rollback") is not get_failure_policy("rollback")
