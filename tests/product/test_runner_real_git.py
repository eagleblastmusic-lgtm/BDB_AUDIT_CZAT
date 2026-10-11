from pathlib import Path
import subprocess
import sys

from bdb_audit.runner.specs import ToolRunSpec
from bdb_audit.runner.supervisor import ToolSupervisor


def test_real_git_metadata_not_copied_and_cleanup_succeeds(tmp_path: Path):
    source = tmp_path / "target"
    source.mkdir()
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    (source / "input.txt").write_text("exact input", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-m", "input"], check=True, capture_output=True)
    result = ToolSupervisor().run(ToolRunSpec(run_id="real-git", source_root=str(source), evidence_dir=str(tmp_path / "evidence"), argv=(sys.executable, "-c", "from pathlib import Path; assert not Path('.git').exists(); assert Path('input.txt').read_text() == 'exact input'")))
    assert result.supervisor_status == "SUCCESS"
    assert result.cleanup_status == "CLEAN"
    assert (source / ".git").is_dir()
