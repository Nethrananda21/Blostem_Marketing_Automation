"""Temporal worker placeholder.

The pilot uses synchronous workflow execution inside the API today, but the
workflow definitions and queue names are pinned here so they can be promoted to
real Temporal workers without rewriting domain logic.
"""

TASK_QUEUES = {
    "signal-triage": "blostem-signal-triage",
    "committee-mapping": "blostem-committee-mapping",
    "draft-generation": "blostem-draft-generation",
    "compliance-review": "blostem-compliance-review",
    "human-approval": "blostem-human-approval",
    "closed-won-handoff": "blostem-closed-won-handoff",
}

