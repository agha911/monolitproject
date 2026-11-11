import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from test_auth import signed
from test_gameplay import game  # noqa: F401 -- shared fixture


def prepare(maker, *, referral=False):
    async def action():
        from app.models.user import User
        async with maker() as session:
            users = [User(telegram_id=tid, total_xp=100000, energy=1000, max_energy=1000,
                          pvp_best_result=5, lastEnergyUpdate=datetime.now(timezone.utc).replace(tzinfo=None))
                     for tid in (101, 202, 303)]
            session.add_all(users)
            await session.flush()
            if referral:
                users[1].invited_by = users[0].id
            await session.commit()
            return [user.id for user in users]
    return asyncio.run(action())


def call(client, path, tid=101, **body):
    return client.post(path, json={"telegram_id": tid, **body}, headers={"X-Telegram-Init-Data": signed(tid)})


def test_referral_first_credit_survives_first_balance_read_and_duplicate_flush(game):
    client, maker = game
    prepare(maker, referral=True)
    payload = {"init_data": signed(202), "delta_clicks": 100, "client_seq": 1, "session_id": "referral"}
    for _ in range(2):
        assert client.post("/api/game/clicks/flush", json=payload).status_code == 200
    for _ in range(2):
        response = client.get("/api/referral/balance", params={"init_data": signed()})
        assert response.status_code == 200, response.text
        assert response.json()["amount"] == 10
    claim = client.post("/api/referral/claim", json={"init_data": signed()})
    assert claim.status_code == 200, claim.text
    assert claim.json()["claimed_amount"] == 10
    assert client.post("/api/referral/claim", json={"init_data": signed()}).json()["claimed_amount"] == 0


def test_referral_concurrent_claim_pays_once(game):
    client, maker = game
    ids = prepare(maker, referral=True)

    async def accrual():
        from app.models.referral import ReferralCycle, ReferralShareEvent
        async with maker() as session:
            now = datetime.now(timezone.utc)
            session.add(ReferralCycle(referrer_id=ids[0], anchor_at=now-timedelta(hours=1), updated_at=now))
            session.add(ReferralShareEvent(referrer_id=ids[0], source_user_id=ids[1], day_date=now.date(), amount=25))
            await session.commit()
    asyncio.run(accrual())
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post("/api/referral/claim", json={"init_data": signed()}), range(4)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert sum(r.json()["claimed_amount"] for r in responses) == 25


def test_referral_expired_cycle_is_persisted(game):
    client, maker = game
    ids = prepare(maker, referral=True)

    async def accrual():
        from app.models.referral import ReferralCycle, ReferralShareEvent
        async with maker() as session:
            now = datetime.now(timezone.utc)
            session.add(ReferralCycle(referrer_id=ids[0], anchor_at=now-timedelta(hours=25), updated_at=now))
            session.add(ReferralShareEvent(referrer_id=ids[0], source_user_id=ids[1], day_date=now.date(), amount=25,
                                           created_at=now-timedelta(hours=24, minutes=30)))
            await session.commit()
    asyncio.run(accrual())
    first = client.post("/api/referral/claim", json={"init_data": signed()}).json()
    assert first["status"] == "expired"
    assert client.post("/api/referral/claim", json={"init_data": signed()}).json()["claimed_amount"] == 0


@pytest.mark.parametrize("draw", [False, True])
def test_live_match_settles_once_and_rejects_outsider(game, draw):
    client, maker = game
    prepare(maker)
    invitation = call(client, "/api/pvp/invite/create").json()
    accepted = call(client, "/api/pvp/invite/accept", 202, invite_code=invitation["invite_code"])
    assert accepted.status_code == 200, accepted.text
    token = accepted.json()["match_token"]
    assert call(client, "/api/pvp/live/submit", 303, match_token=token, my_clicks=1).status_code == 403
    first = call(client, "/api/pvp/live/submit", 101, match_token=token, my_clicks=10)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "waiting"
    assert call(client, "/api/pvp/live/submit", 101, match_token=token, my_clicks=10).status_code == 409
    second = call(client, "/api/pvp/live/submit", 202, match_token=token, my_clicks=10 if draw else 5)
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "finished"
    assert second.json()["is_draw"] is draw
    assert second.json()["player1_total_xp"] == (100000 if draw else 150000)
    assert second.json()["player2_total_xp"] == (100000 if draw else 50000)
    assert call(client, "/api/pvp/live/submit", 202, match_token=token, my_clicks=5).status_code == 409


def test_invite_can_only_be_accepted_once_concurrently(game):
    client, maker = game
    prepare(maker)
    code = call(client, "/api/pvp/invite/create").json()["invite_code"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda tid: call(client, "/api/pvp/invite/accept", tid, invite_code=code), (202, 303)))
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]


def test_challenge_completion_cannot_be_replayed_or_stolen(game):
    client, maker = game
    prepare(maker)
    start = call(client, "/api/pvp/challenge/start")
    assert start.status_code == 200, start.text
    attempt = start.json()["attempt_id"]
    assert call(client, "/api/pvp/challenge/finish", 202, attempt_id=attempt, my_clicks=10).status_code == 403
    finish = call(client, "/api/pvp/challenge/finish", attempt_id=attempt, my_clicks=10)
    assert finish.status_code == 200, finish.text
    assert finish.json()["is_win"] is True
    assert call(client, "/api/pvp/challenge/finish", attempt_id=attempt, my_clicks=10).status_code == 409


def test_expired_match_cannot_move_points(game):
    client, maker = game
    prepare(maker)
    code = call(client, "/api/pvp/invite/create").json()["invite_code"]
    token = call(client, "/api/pvp/invite/accept", 202, invite_code=code).json()["match_token"]

    async def expire():
        from app.models.pvp_models import PvpSession, PvpMatch
        async with maker() as session:
            row = (await session.execute(select(PvpSession).where(PvpSession.match_token == token))).scalar_one()
            row.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            await session.commit()
            assert (await session.execute(select(func.count()).select_from(PvpMatch))).scalar_one() == 0
    asyncio.run(expire())
    assert call(client, "/api/pvp/live/submit", match_token=token, my_clicks=10).status_code == 409
