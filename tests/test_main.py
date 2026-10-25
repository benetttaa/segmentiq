import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", str(tmp_path / "test_segmentiq.db"))
    main.init()
    return TestClient(main.app)


def test_compute_rfm():
    tx = pd.DataFrame([
        {"CustomerID": 1, "InvoiceNo": "A", "InvoiceDate": "2025-01-01", "Quantity": 2, "UnitPrice": 10},
        {"CustomerID": 1, "InvoiceNo": "B", "InvoiceDate": "2025-01-10", "Quantity": 1, "UnitPrice": 5},
        {"CustomerID": 2, "InvoiceNo": "C", "InvoiceDate": "2025-01-05", "Quantity": 3, "UnitPrice": 4},
    ])
    rfm = main.compute_rfm(tx)
    assert set(rfm.columns) == {"id", "recency", "frequency", "monetary"}
    c1 = rfm[rfm.id == 1].iloc[0]
    assert c1.frequency == 2
    assert c1.monetary == 25
    assert c1.recency == 1  # day after last purchase 2025-01-10


def test_name_clusters_labels_five_segments():
    # Fake centers: cluster 0 = best value, cluster 2 = highest recency (lost)
    cs = np.array([
        [0.0, 1.0, 1.0],
        [0.5, 0.2, 0.2],
        [2.0, 0.1, 0.1],
    ])
    names = main.name_clusters(cs)
    assert names[2] == "Lost"
    assert names[0] == "Champions"
    assert set(names.values()) <= {"Champions", "Loyal", "Promising", "At-Risk", "Lost"}


def test_campaign_requires_admin_and_logs(client):
    client.post("/api/load-sample", params={"n": 50})
    client.post("/api/segment")
    denied = client.post("/api/campaign/Champions")
    assert denied.status_code == 403
    login = client.post("/api/login", json={"email": main.ADMIN_EMAIL}).json()
    h = {"Authorization": f"Bearer {login['token']}"}
    ok = client.post("/api/campaign/Champions", headers=h)
    assert ok.status_code == 200
    assert ok.json()["customers_notified"] > 0
    hist = client.get("/api/campaigns").json()
    assert any(row["segment"] == "Champions" for row in hist)
    again = client.post("/api/campaign/Champions", headers=h)
    assert again.status_code == 409
