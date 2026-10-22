"""Opt-in smoke harness for coordinator-run, live Sprint 1 acceptance.

This intentionally performs real API calls only when explicitly enabled. It
never prints or persists the bearer token returned when opening a session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE_URL = os.environ.get("STAYLEAD_LIVE_API_URL", "http://127.0.0.1:8000").rstrip("/")

SCENARIOS = (
    {
        "name": "city_vi_breakfast_parking_followup",
        "hotel_slug": "harbor-city-demo",
        "turns": [
            ("Bữa sáng ở đâu và mấy giờ? Có chỗ đỗ xe không, phí bao nhiêu?", [
                "F-HTL-CITY01-040", "F-HTL-CITY01-046",
            ]),
            ("Nhà hàng bữa sáng đó nằm ở tầng mấy?", ["F-HTL-CITY01-040"]),
        ],
    },
    {
        "name": "beach_fr_breakfast_pool",
        "hotel_slug": "lagoon-family-demo",
        "turns": [(
            "À quelle heure sert-on le petit-déjeuner et quand la piscine est-elle ouverte ?",
            ["F-HTL-BEACH02-040", "F-HTL-BEACH02-043"],
        )],
    },
    {
        "name": "retreat_ja_breakfast_parking",
        "hotel_slug": "pine-ridge-demo",
        "turns": [(
            "朝食の時間と月曜日の営業状況を教えてください。駐車場は何台分ありますか？16人乗りを超えるバスでも入れますか？",
            ["F-HTL-RETREAT03-040", "F-HTL-RETREAT03-046"],
        )],
    },
    {
        "name": "city_en_partial_supported_and_unknown",
        "hotel_slug": "harbor-city-demo",
        "turns": [(
            "What time is breakfast, and does the hotel have a helipad?",
            ["F-HTL-CITY01-040"],
        )],
    },
)


def request(path: str, payload: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {error.code}: {body}") from None
    if not isinstance(result, dict):
        raise TypeError("API returned a non-object JSON response")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=[scenario["name"] for scenario in SCENARIOS],
        help="run only this scenario (default: run all scenarios)",
    )
    parser.add_argument(
        "--turn-limit",
        type=int,
        help="run at most this many initial turns per selected scenario",
    )
    args = parser.parse_args()
    if args.turn_limit is not None and args.turn_limit < 1:
        parser.error("--turn-limit must be at least 1")

    if os.environ.get("STAYLEAD_LIVE_EVAL") != "1":
        print("Set STAYLEAD_LIVE_EVAL=1 to enable real API/model calls.", file=sys.stderr)
        return 2

    scenarios = [scenario for scenario in SCENARIOS if args.scenario is None or scenario["name"] == args.scenario]
    for scenario in scenarios:
        session = request("/v1/guest/sessions", {"hotel_slug": scenario["hotel_slug"]})
        session_id = session["session_id"]
        token = session["access_token"]
        turns = scenario["turns"]
        if args.turn_limit is not None:
            turns = turns[:args.turn_limit]
        for index, (question, expected_fact_ids) in enumerate(turns, start=1):
            result = request(
                f"/v1/guest/sessions/{session_id}/messages",
                {"request_id": str(uuid.uuid4()), "question": question},
                token,
            )
            # Emit only response/evaluation data; session credentials stay in memory.
            print(json.dumps({
                "scenario": scenario["name"],
                "turn": index,
                "question": question,
                "expected_fact_ids": expected_fact_ids,
                "response": result,
            }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
