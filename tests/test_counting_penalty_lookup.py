"""Unit tests for core.counting._find_counting_penalty_job -- the lookup
that replaced the old counting_penalties table (see core.tasks.
apply_scheduled_role_job / commands.permissions.role_commands for the
other half of this: scheduled_roles is the single shared mechanism now).
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.counting as counting

GUILD_ID = 1
USER_ID = 2
PENALTY_ROLE_ID = 999
OTHER_ROLE_ID = 111


def test_finds_job_that_removes_the_penalty_role():
    jobs = [
        {"id": 1, "add_ids": [], "remove_ids": [OTHER_ROLE_ID], "run_at": "a"},
        {"id": 2, "add_ids": [], "remove_ids": [PENALTY_ROLE_ID], "run_at": "b"},
    ]
    with patch.object(counting.db, "get_pending_scheduled_role_changes_for_user", return_value=jobs):
        job = counting._find_counting_penalty_job(GUILD_ID, USER_ID, PENALTY_ROLE_ID)
    assert job is not None
    assert job["id"] == 2


def test_returns_none_when_no_pending_jobs():
    with patch.object(counting.db, "get_pending_scheduled_role_changes_for_user", return_value=[]):
        assert counting._find_counting_penalty_job(GUILD_ID, USER_ID, PENALTY_ROLE_ID) is None


def test_returns_none_when_pending_jobs_dont_remove_this_role():
    jobs = [{"id": 1, "add_ids": [], "remove_ids": [OTHER_ROLE_ID], "run_at": "a"}]
    with patch.object(counting.db, "get_pending_scheduled_role_changes_for_user", return_value=jobs):
        assert counting._find_counting_penalty_job(GUILD_ID, USER_ID, PENALTY_ROLE_ID) is None


def test_matches_role_in_multi_role_removal_list():
    jobs = [{"id": 1, "add_ids": [], "remove_ids": [OTHER_ROLE_ID, PENALTY_ROLE_ID], "run_at": "a"}]
    with patch.object(counting.db, "get_pending_scheduled_role_changes_for_user", return_value=jobs):
        job = counting._find_counting_penalty_job(GUILD_ID, USER_ID, PENALTY_ROLE_ID)
    assert job is not None and job["id"] == 1
