from temporalio import workflow


@workflow.defn
class SignalTriageWorkflow:
    @workflow.run
    async def run(self, account_id: str) -> str:
        return f"signal-triage:{account_id}"


@workflow.defn
class CommitteeMappingWorkflow:
    @workflow.run
    async def run(self, account_id: str) -> str:
        return f"committee-mapping:{account_id}"


@workflow.defn
class DraftGenerationWorkflow:
    @workflow.run
    async def run(self, draft_id: str) -> str:
        return f"draft-generation:{draft_id}"


@workflow.defn
class ComplianceReviewWorkflow:
    @workflow.run
    async def run(self, draft_id: str) -> str:
        return f"compliance-review:{draft_id}"


@workflow.defn
class HumanApprovalWorkflow:
    @workflow.run
    async def run(self, draft_id: str) -> str:
        return f"human-approval:{draft_id}"


@workflow.defn
class ClosedWonHandoffWorkflow:
    @workflow.run
    async def run(self, account_id: str) -> str:
        return f"closed-won-handoff:{account_id}"

