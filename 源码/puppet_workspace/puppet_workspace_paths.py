# -*- coding: utf-8 -*-
"""Puppet 工作区及用户路径定位；与具体业务操作分离。"""
import os
import sys
from pathlib import Path


from puppet_common.paths import workspace_root as workspace_root_from_script


def user_home() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))).absolute()


def default_ccswitch_home() -> Path:
    env = os.environ.get("CCSWITCH_SKILLS_HOME")
    return Path(env).absolute() if env else user_home() / ".cc-switch" / "skills"
