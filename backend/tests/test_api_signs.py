from app import db
from app.models import ZodiacSign
from app.services import SIGNS


def test_signs_endpoint_returns_frontend_compatible_list(client):
    response = client.get("/api/signs")

    assert response.status_code == 200

    data = response.get_json()

    assert isinstance(data, list)
    assert data == SIGNS
    assert len(data) == 13
    assert len(set(data)) == 13
    assert "aries" in data
    assert "ophiuchus" in data
    assert all(isinstance(item, str) for item in data)


def test_signs_meta_endpoint_returns_active_ordered_metadata(client):
    response = client.get("/api/signs/meta")

    assert response.status_code == 200

    data = response.get_json()
    assert data["locale"] == "ru"

    items = data["items"]
    assert isinstance(items, list)
    assert len(items) == 13
    assert [item["key"] for item in items] == SIGNS

    assert items[0] == {
        "key": "aries",
        "name": "Овен",
        "sort_order": 1,
        "is_active": True,
    }

    assert all(
        set(item.keys()) == {"key", "name", "sort_order", "is_active"}
        for item in items
    )
    assert all(item["is_active"] is True for item in items)


def test_signs_meta_endpoint_excludes_inactive_signs(client):
    sign = db.session.get(ZodiacSign, "aries")
    assert sign is not None

    original_is_enabled = sign.is_enabled

    try:
        sign.is_enabled = False
        db.session.commit()

        response = client.get("/api/signs/meta")

        assert response.status_code == 200

        data = response.get_json()
        keys = [item["key"] for item in data["items"]]

        assert "aries" not in keys
        assert len(keys) == len(SIGNS) - 1
    finally:
        sign.is_enabled = original_is_enabled
        db.session.commit()