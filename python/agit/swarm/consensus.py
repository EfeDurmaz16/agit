"""Voting-based conflict resolution for multi-agent merges."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agit.engine.executor import ExecutionEngine


class VoteChoice(Enum):
    """Possible vote choices for a merge proposal."""

    OURS = "ours"
    THEIRS = "theirs"
    ABSTAIN = "abstain"


@dataclass
class Vote:
    """A single agent's vote on a merge proposal.

    Attributes
    ----------
    agent_id:
        Identifier of the voting agent.
    choice:
        The :class:`VoteChoice` cast by this agent.
    reason:
        Optional free-text justification for the vote.
    confidence:
        Confidence weight in the range ``[0.0, 1.0]`` (default ``1.0``).
    """

    agent_id: str
    choice: VoteChoice
    reason: str = ""
    confidence: float = 1.0

    def weight(self) -> float:
        """Effective voting weight (confidence clamped to [0, 1])."""
        return max(0.0, min(1.0, self.confidence))


@dataclass
class MergeProposal:
    """A pending merge proposal awaiting votes.

    Attributes
    ----------
    id:
        Unique proposal identifier.
    branches:
        List of branch names involved in the merge (first is *ours*, second is *theirs*).
    votes:
        Votes cast so far.
    status:
        One of ``"open"``, ``"accepted"``, ``"rejected"``, ``"tied"``.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    branches: list[str] = field(default_factory=list)
    votes: list[Vote] = field(default_factory=list)
    status: str = "open"

    def tally(self) -> dict[str, float]:
        """Return weighted vote totals per choice."""
        totals: dict[str, float] = {c.value: 0.0 for c in VoteChoice}
        for vote in self.votes:
            if vote.choice != VoteChoice.ABSTAIN:
                totals[vote.choice.value] += vote.weight()
        return totals

    def winning_choice(self) -> VoteChoice | None:
        """Return the winning :class:`VoteChoice`, or ``None`` if tied."""
        tally = self.tally()
        ours = tally.get(VoteChoice.OURS.value, 0.0)
        theirs = tally.get(VoteChoice.THEIRS.value, 0.0)
        if ours > theirs:
            return VoteChoice.OURS
        if theirs > ours:
            return VoteChoice.THEIRS
        return None  # tie

    def quorum_reached(self, quorum: float, eligible_voters: int) -> bool:
        """Return True if the fraction of non-abstaining votes meets *quorum*."""
        if eligible_voters == 0:
            return False
        non_abstaining = sum(1 for v in self.votes if v.choice != VoteChoice.ABSTAIN)
        return (non_abstaining / eligible_voters) >= quorum


class ConsensusMerger:
    """Resolve multi-agent merge conflicts via weighted voting.

    Agents cast votes on a :class:`MergeProposal`; once a quorum is reached
    the winning branch is merged and the outcome committed to the agit
    repository.

    Parameters
    ----------
    repo_path:
        Path to the agit repository.
    quorum:
        Minimum fraction of registered voters (excluding abstentions) that
        must vote for the resolution to proceed (default ``0.5``).

    Example::

        merger = ConsensusMerger("./repo", quorum=0.6)
        proposal = merger.propose_merge(["feature/agent-1", "feature/agent-2"])

        merger.vote(proposal.id, "agent-1", VoteChoice.OURS, confidence=0.9)
        merger.vote(proposal.id, "agent-2", VoteChoice.THEIRS, confidence=0.7)
        merger.vote(proposal.id, "agent-3", VoteChoice.OURS, confidence=1.0)

        result = merger.resolve(proposal.id)
        print(result["merged_branch"])
    """

    def __init__(self, repo_path: str, quorum: float = 0.5) -> None:
        self._repo_path = repo_path
        self._quorum = quorum
        self._engine = ExecutionEngine(repo_path=repo_path, agent_id="consensus-merger")
        self._proposals: dict[str, MergeProposal] = {}
        # Track which agents are eligible voters per proposal
        self._eligible_voters: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def propose_merge(self, branches: list[str]) -> MergeProposal:
        """Create a new merge proposal for the given *branches*.

        The first branch is treated as *ours* and the second as *theirs* for
        the ``ours`` / ``theirs`` strategy selection.

        Parameters
        ----------
        branches:
            At least two branch names to merge.

        Returns
        -------
        MergeProposal:
            The newly created proposal (status ``"open"``).
        """
        if len(branches) < 2:
            raise ValueError("At least two branches are required for a merge proposal")

        proposal = MergeProposal(branches=branches)
        self._proposals[proposal.id] = proposal
        self._eligible_voters[proposal.id] = set()

        # Commit the proposal to agit
        state = {
            "memory": {
                "proposal_id": proposal.id,
                "branches": branches,
                "status": "open",
            },
            "world_state": {},
        }
        try:
            self._engine.commit_state(
                state,
                message=f"consensus proposal {proposal.id[:8]}: merge {' + '.join(branches[:2])}",
                action_type="system_event",
            )
        except Exception:
            pass

        return proposal

    def vote(
        self,
        proposal_id: str,
        agent_id: str,
        choice: VoteChoice,
        reason: str = "",
        confidence: float = 1.0,
    ) -> Vote:
        """Cast a vote on an open merge proposal.

        Parameters
        ----------
        proposal_id:
            ID of the target :class:`MergeProposal`.
        agent_id:
            ID of the voting agent.
        choice:
            The agent's :class:`VoteChoice`.
        reason:
            Optional justification string.
        confidence:
            Voting weight in ``[0.0, 1.0]``.

        Returns
        -------
        Vote:
            The recorded vote.

        Raises
        ------
        KeyError:
            If *proposal_id* is unknown.
        ValueError:
            If the proposal is not ``"open"`` or the agent has already voted.
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"Unknown proposal: {proposal_id!r}")
        if proposal.status != "open":
            raise ValueError(f"Proposal {proposal_id!r} is already {proposal.status!r}")
        if any(v.agent_id == agent_id for v in proposal.votes):
            raise ValueError(f"Agent {agent_id!r} has already voted on proposal {proposal_id!r}")

        vote = Vote(agent_id=agent_id, choice=choice, reason=reason, confidence=confidence)
        proposal.votes.append(vote)
        self._eligible_voters[proposal_id].add(agent_id)

        return vote

    def register_voter(self, proposal_id: str, agent_id: str) -> None:
        """Pre-register an eligible voter (affects quorum calculation).

        Call before votes are cast when you know the full voter set in advance.
        """
        if proposal_id not in self._proposals:
            raise KeyError(f"Unknown proposal: {proposal_id!r}")
        self._eligible_voters[proposal_id].add(agent_id)

    def resolve(self, proposal_id: str) -> dict[str, Any]:
        """Tally votes and execute the merge if quorum is met.

        Parameters
        ----------
        proposal_id:
            ID of the proposal to resolve.

        Returns
        -------
        dict:
            Resolution summary with keys:
            - ``"proposal_id"``
            - ``"status"`` – ``"accepted"``, ``"rejected"`` (no quorum), or ``"tied"``
            - ``"tally"`` – weighted vote totals
            - ``"winning_choice"`` – ``"ours"`` / ``"theirs"`` / ``None``
            - ``"merged_branch"`` – branch name that was merged (if accepted)
            - ``"merge_commit"`` – agit commit hash (if merge executed)
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"Unknown proposal: {proposal_id!r}")

        eligible_count = len(self._eligible_voters[proposal_id])
        # Fall back to actual voter count if no voters pre-registered
        if eligible_count == 0:
            eligible_count = len(proposal.votes)

        tally = proposal.tally()
        winning = proposal.winning_choice()
        quorum_ok = proposal.quorum_reached(self._quorum, max(eligible_count, len(proposal.votes)))

        result: dict[str, Any] = {
            "proposal_id": proposal_id,
            "tally": tally,
            "winning_choice": winning.value if winning else None,
            "merged_branch": None,
            "merge_commit": None,
        }

        if not quorum_ok:
            proposal.status = "rejected"
            result["status"] = "rejected"
            result["reason"] = "quorum not reached"
            self._commit_resolution(proposal, result)
            return result

        if winning is None:
            proposal.status = "tied"
            result["status"] = "tied"
            result["reason"] = "votes tied – no merge performed"
            self._commit_resolution(proposal, result)
            return result

        # Execute the merge
        strategy = winning.value  # "ours" or "theirs"
        target_branch = proposal.branches[1] if winning == VoteChoice.THEIRS else proposal.branches[0]
        source_branch = proposal.branches[0] if winning == VoteChoice.THEIRS else proposal.branches[1]

        try:
            merge_hash = self._engine.merge(source_branch, strategy=strategy)
            proposal.status = "accepted"
            result["status"] = "accepted"
            result["merged_branch"] = source_branch
            result["merge_commit"] = merge_hash
            result["strategy"] = strategy
            result["target_branch"] = target_branch
        except Exception as exc:
            proposal.status = "rejected"
            result["status"] = "rejected"
            result["reason"] = f"merge failed: {exc}"

        self._commit_resolution(proposal, result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _commit_resolution(self, proposal: MergeProposal, result: dict[str, Any]) -> None:
        state = {
            "memory": {
                "proposal_id": proposal.id,
                "resolution": result,
                "votes": [
                    {
                        "agent_id": v.agent_id,
                        "choice": v.choice.value,
                        "reason": v.reason,
                        "confidence": v.confidence,
                    }
                    for v in proposal.votes
                ],
            },
            "world_state": {},
        }
        try:
            self._engine.commit_state(
                state,
                message=f"consensus resolved {proposal.id[:8]}: {proposal.status}",
                action_type="system_event",
            )
        except Exception:
            pass

    def get_proposal(self, proposal_id: str) -> MergeProposal | None:
        """Return the :class:`MergeProposal` with the given ID, or ``None``."""
        return self._proposals.get(proposal_id)

    def list_proposals(self) -> list[dict[str, Any]]:
        """Return all proposals as plain dicts."""
        return [
            {
                "id": p.id,
                "branches": p.branches,
                "status": p.status,
                "vote_count": len(p.votes),
                "tally": p.tally(),
            }
            for p in self._proposals.values()
        ]
