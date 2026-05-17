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