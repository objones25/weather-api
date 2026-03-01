import pytest
from datetime import datetime, timezone, timedelta
from app.history.models import RequestLog


@pytest.mark.anyio
async def test_history_empty(history_client):
    response = await history_client.get("/v1/history")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["offset"] == 0
    assert data["limit"] == 20


@pytest.mark.anyio
async def test_history_returns_entries(history_client, db_session):
    async with db_session() as session:
        session.add(RequestLog(location="London,UK"))
        session.add(RequestLog(location="Paris,FR"))
        await session.commit()

    response = await history_client.get("/v1/history")
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.anyio
async def test_history_ordered_newest_first(history_client, db_session):
    now = datetime.now(timezone.utc)
    async with db_session() as session:
        session.add(RequestLog(location="London,UK", requested_at=now - timedelta(hours=1)))
        session.add(RequestLog(location="Paris,FR", requested_at=now))
        await session.commit()

    items = (await history_client.get("/v1/history")).json()["items"]
    assert items[0]["location"] == "Paris,FR"
    assert items[1]["location"] == "London,UK"


@pytest.mark.anyio
async def test_history_location_filter(history_client, db_session):
    async with db_session() as session:
        session.add(RequestLog(location="London,UK"))
        session.add(RequestLog(location="Paris,FR"))
        session.add(RequestLog(location="London Bridge,UK"))
        await session.commit()

    data = (await history_client.get("/v1/history?location=london")).json()
    assert data["total"] == 2
    assert all("london" in item["location"].lower() for item in data["items"])


@pytest.mark.anyio
async def test_history_total_reflects_filter(history_client, db_session):
    async with db_session() as session:
        for _ in range(3):
            session.add(RequestLog(location="London,UK"))
        session.add(RequestLog(location="Paris,FR"))
        await session.commit()

    data = (await history_client.get("/v1/history?location=London")).json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.anyio
async def test_history_pagination(history_client, db_session):
    async with db_session() as session:
        for i in range(5):
            session.add(RequestLog(location=f"City{i},UK"))
        await session.commit()

    page1 = (await history_client.get("/v1/history?limit=2&offset=0")).json()
    assert page1["total"] == 5
    assert len(page1["items"]) == 2

    page2 = (await history_client.get("/v1/history?limit=2&offset=2")).json()
    assert page2["total"] == 5
    assert len(page2["items"]) == 2

    page3 = (await history_client.get("/v1/history?limit=2&offset=4")).json()
    assert page3["total"] == 5
    assert len(page3["items"]) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("params", ["limit=0", "limit=101", "offset=-1"])
async def test_history_invalid_params(history_client, params):
    response = await history_client.get(f"/v1/history?{params}")
    assert response.status_code == 422
