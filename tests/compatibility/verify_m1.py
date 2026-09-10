"""Run the complete local M1 gate and retain an exact-input qualification record."""
import json
import argparse
import os
import platform
import subprocess
import sys

from corpus_support import CORPUS, ROOT, SOURCE, SOURCE_SHA, sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--record",action="store_true",help="Explicitly refresh the pre-commit qualification record")
    args=parser.parse_args()
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTEST_ADDOPTS="-p no:cacheprovider")
    commands=[]
    for command in [[sys.executable,"-m","pytest","tests/compatibility","-q"],
                    [sys.executable,"-B",str(SOURCE),"--self-test"]]:
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
        print(result.stdout,end="")
        if result.stderr:
            print(result.stderr,file=sys.stderr,end="")
        commands.append({"argv":command,"exit_code":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
        if result.returncode:
            raise SystemExit(result.returncode)
    runtime=json.loads(commands[-1]["stdout"])
    assert runtime["status"]=="PASS" and runtime["errors"]==[]
    manifest=json.loads((CORPUS/"manifest.json").read_bytes())
    assert manifest["unresolved_expectation_conflicts"]==[]
    assert sha(SOURCE.read_bytes())==SOURCE_SHA
    paths=[CORPUS/"manifest.json",CORPUS/"EXPECTATION_BASIS.md",CORPUS/"EXPECTATION_INPUTS.json",
           ROOT/"tests/compatibility/corpus_support.py",ROOT/"tests/compatibility/build_corpus.py",
           ROOT/"tests/compatibility/test_compatibility_corpus.py",ROOT/"tests/compatibility/verify_m1.py"]
    gates={"REQUIRED_FIXTURE_BYTES_PINNED":"YES","LEGACY_OBSERVED_OUTCOMES_RECORDED":"YES",
           "INDEPENDENT_SAFE_EXPECTATIONS_QUALIFIED":"YES","KNOWN_LEGACY_BUGS_CLASSIFIED":"YES",
           "UNRESOLVED_EXPECTATION_CONFLICTS":0}
    record={"schema":"BDB_M1_PRE_HISTORY_QUALIFICATION_V1","repository":"eagleblastmusic-lgtm/bdb-audit",
        "qualification_scope":"Synthetic M1 corpus only; not independent foundation freeze, real audit, release approval or v2 compatibility qualification",
        "head_at_verification":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "branch":subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
        "legacy_source_sha256":SOURCE_SHA,"python":platform.python_version(),"platform":platform.platform(),
        "qualified_input_sha256":{str(p.relative_to(ROOT)).replace("\\","/"):sha(p.read_bytes()) for p in paths},
        "commands":commands,"valid_count":8,"invalid_count":17,"extra_count":0,
        "known_legacy_bugs":[],"intentional_v2_hardening":[],"gates":gates,"verdict":"PASS","m2_started":False}
    assert record["branch"]=="bdb-v2"
    if args.record:
        (CORPUS/"M1_QUALIFICATION.json").write_bytes((json.dumps(record,indent=2,sort_keys=True)+"\n").encode())
    else:
        retained=json.loads((CORPUS/"M1_QUALIFICATION.json").read_bytes())
        assert retained["qualified_input_sha256"]==record["qualified_input_sha256"], "M1 qualification inputs changed"
        assert retained["gates"]==gates and retained["verdict"]=="PASS"
    print(json.dumps(gates,indent=2));print("M1 = PASS")


if __name__=="__main__":
    main()
