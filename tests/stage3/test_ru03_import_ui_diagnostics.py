from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from bdb_audit.orchestration.native_ensemble import E1_LANE_SLOTS
from bdb_audit.ui import InteractiveAuditUI
from bdb_audit.workflow.inbox import (
    ImportFileResult,
    ImportedResultSummary,
    LaneInboxStatus,
)


def test_d19_ui_surfaces_unknown_lane_rejection_and_next_action(tmp_path: Path) -> None:
    foreign_path = tmp_path / "foreign_result.zip"
    summary = ImportedResultSummary(
        campaign_id="campaign_expected",
        stage_id="E1",
        total_required_lanes=len(E1_LANE_SLOTS),
        accepted_count=0,
        missing_lanes=list(E1_LANE_SLOTS),
        lane_statuses={slot: LaneInboxStatus(slot, "MISSING") for slot in E1_LANE_SLOTS},
        file_results=[
            ImportFileResult(
                path=str(foreign_path.resolve()),
                lane_slot="UNKNOWN",
                status="REJECTED",
                code="FOREIGN_CAMPAIGN",
                reason="FOREIGN_CAMPAIGN: campaign_FOREIGN does not match campaign_expected",
                raw_digest="a" * 64,
                next_action="SELECT_CORRECT_CAMPAIGN",
            )
        ],
    )

    class FakeOrchestrator:
        def import_results(self, paths):
            assert paths == [foreign_path]
            return summary

    ui = InteractiveAuditUI.__new__(InteractiveAuditUI)
    ui.settings_mgr = SimpleNamespace(
        settings=SimpleNamespace(auto_open_zip_selector=False, output_work_dir=str(tmp_path))
    )
    ui.orchestrator = FakeOrchestrator()
    ui.platform = SimpleNamespace()

    output: list[str] = []
    ui._execute_result_import(lambda _prompt: str(foreign_path), output.append)
    rendered = "\n".join(output)

    assert "Per-file import report:" in rendered
    assert "foreign_result.zip: REJECTED [FOREIGN_CAMPAIGN] lane=UNKNOWN" in rendered
    assert "campaign_FOREIGN does not match campaign_expected" in rendered
    assert "next=SELECT_CORRECT_CAMPAIGN" in rendered
