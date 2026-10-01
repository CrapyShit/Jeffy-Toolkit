"""Runs tools/check_maya_api.py when maya-stubs is installed."""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_maya_api  # noqa: E402


def test_cmds_and_openmaya_usage():
    stubs = check_maya_api.find_stubs()
    if not stubs:
        pytest.skip("maya-stubs not installed")
    assert check_maya_api.main([os.path.join(ROOT, "scripts"), os.path.join(ROOT, "install")]) == 0


def test_checker_detects_errors(tmp_path):
    stubs = check_maya_api.find_stubs()
    if not stubs:
        pytest.skip("maya-stubs not installed")
    bad = tmp_path / "bad.py"
    bad.write_text("from maya import cmds\ncmds.joint(notAFlag=True)\ncmds.notACommand()\n")
    assert check_maya_api.main([str(bad)]) == 1
