from __future__ import annotations

import pytest
from pydantic import ValidationError

from staylead_platform.entrypoints.app import MessageRequest


def test_message_request_requires_exactly_one_question_or_answer_receipt() -> None:
    assert MessageRequest(request_id="normal-1", question="When is breakfast?")
    assert MessageRequest(request_id="resume-1", answer_only_receipt_id="original-1")
    with pytest.raises(ValidationError):
        MessageRequest(request_id="bad-1", question="Edit these dates", answer_only_receipt_id="original-1")
    with pytest.raises(ValidationError):
        MessageRequest(request_id="bad-2")
