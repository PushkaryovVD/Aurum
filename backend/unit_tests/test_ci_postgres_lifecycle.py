"""Execute the actual CI shell blocks with fake provisioning tools only."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


FAKE_TOOL = r'''import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
root = pathlib.Path(os.environ["FAKE_ROOT"])
stage = os.environ["FAKE_STAGE"]
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps([name, args]) + "\n")
if name == "sudo":
    assert args[0] == "apt-get"
elif name == "pg_config":
    print(root / "bin")
elif name == "initdb":
    if stage == "before_start":
        sys.exit(41)
    data = pathlib.Path(args[args.index("-D") + 1])
    data.mkdir()
    (data / "PG_VERSION").write_text("17")
elif name == "pg_ctl":
    data = pathlib.Path(args[args.index("-D") + 1])
    pid = data / "postmaster.pid"
    if args[-1] == "start":
        pid.write_text("fake-owned-postmaster")
        (root / "running").write_text(str(data))
        if stage == "start_wait":
            sys.exit(43)
    elif args[-1] == "stop":
        assert (root / "running").read_text() == str(data)
        if stage == "stop_failure":
            sys.exit(44)
        pid.unlink()
        (root / "running").unlink()
    else:
        raise AssertionError("unexpected pg_ctl operation")
elif name == "python":
    sys.stdin.read()
    if stage == "post_start":
        sys.exit(42)
    workspace = pathlib.Path(os.environ["RUNTIME"])
    (workspace / "runtime.json").write_text(json.dumps({"workspace": str(workspace)}))
else:
    raise AssertionError("unexpected tool " + name)
'''


def workflow_block(name):
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    lines = workflow.read_text().splitlines()
    start = lines.index("      - name: " + name)
    run = next(i for i in range(start + 1, len(lines)) if lines[i] == "        run: |")
    block = []
    for line in lines[run + 1:]:
        if line and not line.startswith("          "):
            break
        block.append(line[10:] if line else "")
    return "\n".join(block) + "\n"


@pytest.mark.parametrize("stage, provision_rc, cleanup_rc", [
    ("post_start", 42, 0),
    ("start_wait", 43, 0),
    ("before_start", 41, 0),
    ("success", 0, 0),
    ("stop_failure", 0, 44),
])
def test_ci_cleanup_survives_provision_failure(tmp_path, stage, provision_rc, cleanup_rc):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("sudo", "pg_config", "initdb", "pg_ctl", "python"):
        tool = fake_bin / name
        tool.write_text("#!" + sys.executable + "\n" + FAKE_TOOL)
        tool.chmod(0o700)
    github_env = tmp_path / "github.env"
    github_env.touch()
    env = {"PATH": str(fake_bin) + os.pathsep + os.defpath,
           "RUNNER_TEMP": str(tmp_path), "GITHUB_ENV": str(github_env),
           "FAKE_ROOT": str(tmp_path), "FAKE_STAGE": stage,
           "AURUM_POSTGRES_HOST": "127.0.0.1", "AURUM_POSTGRES_PORT": "57613",
           "AURUM_POSTGRES_USER": "postgres", "AURUM_POSTGRES_PASSWORD": ""}
    provision = workflow_block("Provision owned disposable loopback PostgreSQL")
    cleanup = workflow_block("Stop disposable PostgreSQL")
    for block in (provision, cleanup):
        assert subprocess.run(["/bin/bash", "-n"], input=block, text=True,
                              capture_output=True, env=env).returncode == 0
    result = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-e", "-o", "pipefail"],
                            input=provision, text=True, capture_output=True, env=env)
    assert result.returncode == provision_rc, result.stderr
    started = stage != "before_start"
    assert (tmp_path / "running").exists() is started
    for line in github_env.read_text().splitlines():
        key, value = line.split("=", 1)
        env[key] = value
    result = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-e", "-o", "pipefail"],
                            input=cleanup, text=True, capture_output=True, env=env)
    assert result.returncode == cleanup_rc, result.stderr
    assert (tmp_path / "running").exists() is (stage == "stop_failure")
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    stops = [args for name, args in calls if name == "pg_ctl" and args[-1] == "stop"]
    assert len(stops) == int(started)
    if started:
        assert stops[0][stops[0].index("-D") + 1].startswith(str(tmp_path) + "/aurum-test-postgres-")
    if stage in ("post_start", "start_wait"):
        assert not list(tmp_path.glob("aurum-test-postgres-*/runtime.json"))
