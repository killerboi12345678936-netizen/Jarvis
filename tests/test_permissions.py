
import asyncio
import json

import pytest

from backend.tools.permissions import (
    claim_action,
    finish_action,
    get_action,
    list_actions,
    propose_action,
    update_action,
)


def test_propose_and_get_action(temp_db):
    action_id = asyncio.run(
        propose_action("create_event", {"title": "Study math"})
    )

    action = asyncio.run(get_action(action_id))

    assert action["tool_name"] == "create_event"
    assert action["status"] == "pending"
    assert action["result"] is None
    assert json.loads(action["arguments"]) == {"title": "Study math"}

    assert asyncio.run(get_action(9999)) is None


def test_claim_sets_executing_and_blocks_second_claim(temp_db):
    action_id = asyncio.run(propose_action("delete_event", {}))

    assert asyncio.run(claim_action(action_id)) is True

    action = asyncio.run(get_action(action_id))

    assert action["status"] == "executing"

    assert asyncio.run(claim_action(action_id)) is False


def test_finish_only_from_executing(temp_db):
    action_id = asyncio.run(propose_action("create_event", {}))

    assert asyncio.run(
        finish_action(action_id, "approved", json.dumps({"created": True}))
    ) is False

    asyncio.run(claim_action(action_id))

    assert asyncio.run(
        finish_action(action_id, "approved", json.dumps({"created": True}))
    ) is True

    action = asyncio.run(get_action(action_id))

    assert action["status"] == "approved"
    assert json.loads(action["result"]) == {"created": True}

    assert asyncio.run(finish_action(action_id, "failed")) is False


def test_update_pending_action_and_rejections(temp_db):
    action_id = asyncio.run(propose_action("create_event", {}))

    assert asyncio.run(
        update_action(action_id, "approved", json.dumps({"created": True}))
    ) is True

    assert asyncio.run(
        update_action(action_id, "rejected", "too late")
    ) is False

    rejected_id = asyncio.run(propose_action("delete_event", {}))

    assert asyncio.run(
        update_action(rejected_id, "rejected", "not now")
    ) is True

    action = asyncio.run(get_action(rejected_id))

    assert action["status"] == "rejected"
    assert action["result"] == "not now"


def test_list_actions_filters_by_status(temp_db):
    approved_id = asyncio.run(propose_action("create_event", {}))
    rejected_id = asyncio.run(propose_action("delete_event", {}))
    asyncio.run(propose_action("system_info", {}))

    asyncio.run(update_action(approved_id, "approved"))
    asyncio.run(update_action(rejected_id, "rejected"))

    everything = asyncio.run(list_actions())

    assert len(everything) == 3

    pending = asyncio.run(list_actions(status="pending"))

    assert len(pending) == 1
    assert pending[0]["tool_name"] == "system_info"

    approved = asyncio.run(list_actions(status="approved"))

    assert len(approved) == 1
    assert approved[0]["id"] == approved_id
