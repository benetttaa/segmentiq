# SegmentIQ: Customer Segmentation + Automated Actions

RFM features + K-Means clustering, with optional GMM/DBSCAN comparison, campaign notifications, and discount coupons.

## Setup

```bash
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open **http://127.0.0.1:8000** (original vanilla dashboard in `static/index.html`).

### React dashboard (optional)

```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173** (API defaults to `http://127.0.0.1:8000`; override with `VITE_API_URL`).

### Tests

```bash
pytest
```

## Demo flow

1. **Load data** — Upload `retail_transactions.csv` or use **Load sample data**.
2. **Run segmentation** — K-Means picks k ∈ {3,4,5} by silhouette score.
3. **Log in as admin** — Email: `admin@segmentiq.com` (no password).
4. **Campaigns** — Send offers per segment; history appears in the Campaigns tab.
5. **Customer view** — Log in as `c{CustomerID}@example.com` (e.g. `c12001@example.com` after CSV upload) to see **My account**.

Optional real email: set `SMTP_USER` and `SMTP_PASS` (Gmail app password); up to 5 emails per campaign are sent.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Legacy HTML dashboard |
| POST | `/api/load-sample` | Generate synthetic RFM customers (`n` query param) |
| POST | `/api/upload` | CSV upload (Online Retail columns) |
| POST | `/api/segment` | Run K-Means segmentation |
| GET | `/api/model-comparison` | Silhouette / Davies-Bouldin for K-Means, GMM, DBSCAN + elbow data |
| GET | `/api/summary` | Dashboard stats, segments, PCA points |
| GET | `/api/customers` | List customers (`segment`, `q`, `limit`) |
| GET | `/api/customers/{id}/inbox` | Notifications and coupons for one customer |
| POST | `/api/login` | Body: `{"email": "..."}` → bearer token |
| GET | `/api/me` | Current session (Authorization header) |
| GET | `/api/account` | Logged-in customer's inbox |
| POST | `/api/notifications/{id}/read` | Mark notification read (customer) |
| GET | `/api/campaigns` | Campaign send history |
| POST | `/api/campaign/{segment}` | Send campaign (admin); `?override=true` bypasses 24h rule |

Campaign requests require header: `Authorization: Bearer <token>` from admin login.
