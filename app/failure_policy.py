"""Batch failure-resolution policies (Strategy pattern).

When the create fan-out for a batch finishes and AT LEAST ONE create failed,
the caller delegates to one of these policies to decide the fate of the whole
batch. (On full success the caller activates directly, which is NOT handled
here.) Each policy performs its batch-level downstream action against the
directory client and returns a :class:`PolicyOutcome`.

The ``client`` is type-hinted as ``DirectoryClient`` for readers, but the type
is NOT enforced at runtime: any object exposing async ``activate_batch`` and
``delete_batch`` methods (a duck-typed fake in tests, for example) works.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.downstream import DirectoryClient


@dataclass
class PolicyOutcome:
    """Result of resolving a partially-failed batch.

    Attributes:
        batch_activated: Whether the batch was activated downstream.
        succeeded_status: Status label to record for the created hospitals.
    """

    batch_activated: bool
    succeeded_status: str


class FailurePolicy(ABC):
    """Strategy for resolving a batch after a partial-failure fan-out."""

    name: str = ""

    @abstractmethod
    async def resolve(self, batch_id: str, client: "DirectoryClient") -> PolicyOutcome:
        """Perform this policy's batch-level action and return the outcome.

        Only ever called when >= 1 create in the batch failed.
        """
        raise NotImplementedError


class RollbackPolicy(FailurePolicy):
    """Delete the whole batch so no hospitals survive a partial failure."""

    name = "rollback"

    async def resolve(self, batch_id: str, client: "DirectoryClient") -> PolicyOutcome:
        await client.delete_batch(batch_id)
        return PolicyOutcome(batch_activated=False, succeeded_status="rolled_back")


class LeavePolicy(FailurePolicy):
    """Leave the successfully-created hospitals in place, inactive (no-op)."""

    name = "leave"

    async def resolve(self, batch_id: str, client: "DirectoryClient") -> PolicyOutcome:
        return PolicyOutcome(batch_activated=False, succeeded_status="created")


class PartialActivatePolicy(FailurePolicy):
    """Activate the batch so the successfully-created hospitals go live."""

    name = "partial"

    async def resolve(self, batch_id: str, client: "DirectoryClient") -> PolicyOutcome:
        await client.activate_batch(batch_id)
        return PolicyOutcome(
            batch_activated=True, succeeded_status="created_and_activated"
        )


_POLICIES = {
    RollbackPolicy.name: RollbackPolicy,
    LeavePolicy.name: LeavePolicy,
    PartialActivatePolicy.name: PartialActivatePolicy,
}


def get_failure_policy(name: str) -> FailurePolicy:
    """Return a fresh policy instance for ``name``.

    Raises:
        ValueError: if ``name`` is not a known policy.
    """
    try:
        policy_cls = _POLICIES[name]
    except KeyError:
        raise ValueError(f"Unknown failure policy: {name!r}")
    return policy_cls()
