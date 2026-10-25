import io, os, random, secrets, sqlite3, smtplib, string
from datetime import datetime, timedelta
from email.message import EmailMessage
import numpy as np, pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score, davies_bouldin_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

DB = "segmentiq.db"
ADMIN_EMAIL = "admin@segmentiq.com"
app = FastAPI(title="SegmentIQ")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginBody(BaseModel):
    email: str

NAMES = {3: ["Champions", "At-Risk", "Lost"],
         4: ["Champions", "Loyal", "At-Risk", "Lost"],
         5: ["Champions", "Loyal", "Promising", "At-Risk", "Lost"]}
# segment -> (title, message, discount %)
ACTIONS = {
    "Champions": ("You're a VIP!", "Thanks for being our best customer. Early access to new arrivals is yours.", 5),
    "Loyal": ("Loyalty reward", "Here are bonus loyalty points and a discount on your next order.", 10),
    "Promising": ("A little something for you", "Enjoy a welcome offer on your next purchase.", 10),
    "At-Risk": ("We miss you!", "It's been a while. Come back with a bigger discount.", 20),
    "Lost": ("Win-back offer", "We'd love to see you again. Use this exclusive coupon.", 25),
}

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT, email TEXT,
            recency REAL, frequency REAL, monetary REAL, segment TEXT, x REAL, y REAL);
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INT,
            title TEXT, message TEXT, created TEXT, read_flag INT DEFAULT 0);
        CREATE TABLE IF NOT EXISTS coupons(id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INT,
            code TEXT, discount INT, created TEXT);
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, email TEXT, role TEXT,
            customer_id INT, created TEXT);
        CREATE TABLE IF NOT EXISTS campaign_log(id INTEGER PRIMARY KEY AUTOINCREMENT, segment TEXT,
            sent_at TEXT, num_customers INT, discount INT);""")
        try:
            c.execute("ALTER TABLE notifications ADD COLUMN read_flag INT DEFAULT 0")
        except sqlite3.OperationalError:
            pass
init()

def auth_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    with db() as c:
        row = c.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    return dict(row) if row else None

def rfm_matrix():
    """Scaled log-RFM features for clustering; None if no customers loaded."""
    with db() as c:
        df = pd.DataFrame([dict(r) for r in c.execute("SELECT id,recency,frequency,monetary FROM customers")])
    if df.empty:
        return None
    return StandardScaler().fit_transform(np.log1p(df[["recency", "frequency", "monetary"]]))

def cluster_metrics(X, labels):
    """Silhouette and Davies-Bouldin; nulls if labels are not usable."""
    labels = np.asarray(labels)
    mask = labels >= 0
    if mask.sum() < 2 or len(set(labels[mask])) < 2:
        return None, None
    Xm, lm = X[mask], labels[mask]
    return round(float(silhouette_score(Xm, lm)), 3), round(float(davies_bouldin_score(Xm, lm)), 3)

def compute_rfm(transactions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Online Retail transactions to one RFM row per customer."""
    df = transactions.dropna(subset=["CustomerID"]).copy()
    df = df[(df["Quantity"] > 0) & (df["UnitPrice"] > 0)]
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    df["total"] = df["Quantity"] * df["UnitPrice"]
    now = df["InvoiceDate"].max() + pd.Timedelta(days=1)
    g = df.groupby("CustomerID").agg(
        recency=("InvoiceDate", lambda s: (now - s.max()).days),
        frequency=("InvoiceNo", "nunique"),
        monetary=("total", "sum"),
    ).reset_index()
    return g.rename(columns={"CustomerID": "id"})

def name_clusters(cluster_centers: np.ndarray) -> dict[int, str]:
    """Turn K-Means centers (scaled log-RFM) into business segment names."""
    cs = cluster_centers
    best = len(cs)
    val = -cs[:, 0] + cs[:, 1] + cs[:, 2]
    ids = list(range(best))
    name_of = {}
    lost = max(ids, key=lambda i: cs[i, 0])
    name_of[lost] = "Lost"
    ids.remove(lost)
    champ = max(ids, key=lambda i: val[i])
    name_of[champ] = "Champions"
    ids.remove(champ)
    if ids:
        risk = max(ids, key=lambda i: cs[i, 0])
        name_of[risk] = "At-Risk"
        ids.remove(risk)
    ids.sort(key=lambda i: -val[i])
    for j, i in enumerate(ids):
        name_of[i] = "Loyal" if (j == 0 and (len(ids) > 1 or cs[i, 1] > 0)) else "Promising"
    return {int(k): v for k, v in name_of.items()}

def save_customers(df):
    with db() as c:
        for t in ("customers", "notifications", "coupons", "meta"):
            c.execute(f"DELETE FROM {t}")
        c.executemany("INSERT INTO customers(id,name,email,recency,frequency,monetary) VALUES(?,?,?,?,?,?)",
                      [(int(r.id), f"Customer {int(r.id)}", f"c{int(r.id)}@example.com",
                        float(r.recency), float(r.frequency), float(r.monetary)) for r in df.itertuples()])

@app.post("/api/load-sample")
def load_sample(n: int = 600):
    rng = np.random.default_rng(42)
    # (share, recency mean, frequency mean, spend mean) archetypes
    groups = [(.15, 10, 25, 5000), (.25, 40, 10, 1800), (.2, 25, 3, 400), (.2, 150, 4, 700), (.2, 300, 1, 120)]
    rows, cid = [], 1000
    for share, r, f, m in groups:
        for _ in range(int(n * share)):
            cid += 1
            rows.append((cid, max(1, rng.lognormal(np.log(r), .4)), max(1, rng.lognormal(np.log(f), .35)),
                         max(10, rng.lognormal(np.log(m), .4))))
    save_customers(pd.DataFrame(rows, columns=["id", "recency", "frequency", "monetary"]))
    return {"customers": len(rows)}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """Online Retail format: CustomerID, InvoiceNo, InvoiceDate, Quantity, UnitPrice"""
    raw = await file.read()
    try: df = pd.read_csv(io.BytesIO(raw), encoding="latin-1")
    except Exception: raise HTTPException(400, "Could not read CSV")
    need = {"CustomerID", "InvoiceNo", "InvoiceDate", "Quantity", "UnitPrice"}
    if not need <= set(df.columns): raise HTTPException(400, f"CSV needs columns: {sorted(need)}")
    g = compute_rfm(df)
    save_customers(g)
    return {"customers": len(g)}

@app.post("/api/segment")
def run_segmentation(k: int = 0):
    with db() as c:
        df = pd.DataFrame([dict(r) for r in c.execute("SELECT id,recency,frequency,monetary FROM customers")])
    if df.empty: raise HTTPException(400, "Load data first")
    X = StandardScaler().fit_transform(np.log1p(df[["recency", "frequency", "monetary"]]))
    scores = {}
    for kk in (3, 4, 5):
        lab = KMeans(kk, n_init=10, random_state=42).fit_predict(X)
        scores[kk] = round(float(silhouette_score(X, lab)), 3)
    best = k if k in scores else max(scores, key=scores.get)
    km = KMeans(best, n_init=10, random_state=42).fit(X)
    name_of = name_clusters(km.cluster_centers_)
    xy = PCA(2, random_state=42).fit_transform(X)
    with db() as c:
        c.executemany("UPDATE customers SET segment=?, x=?, y=? WHERE id=?",
                      [(name_of[int(l)], float(p[0]), float(p[1]), int(i)) for l, p, i in zip(km.labels_, xy, df.id)])
        c.execute("INSERT OR REPLACE INTO meta VALUES('silhouette',?)", (str(scores),))
        c.execute("INSERT OR REPLACE INTO meta VALUES('k',?)", (str(best),))
    return {"k": best, "silhouette_by_k": scores}

@app.get("/api/model-comparison")
def model_comparison():
    """Compare K-Means, GMM, and DBSCAN on RFM features (segments still use K-Means)."""
    X = rfm_matrix()
    if X is None:
        raise HTTPException(400, "Load data first")
    with db() as c:
        row = c.execute("SELECT v FROM meta WHERE k='k'").fetchone()
    k = int(row["v"]) if row else 4
    elbow = []
    for kk in range(2, 9):
        km = KMeans(kk, n_init=10, random_state=42).fit(X)
        elbow.append({"k": kk, "inertia": round(float(km.inertia_), 2)})
    out = {}
    for name, labels in [
        ("kmeans", KMeans(k, n_init=10, random_state=42).fit_predict(X)),
        ("gmm", GaussianMixture(k, random_state=42, n_init=10).fit(X).predict(X)),
        ("dbscan", DBSCAN(eps=0.8, min_samples=8).fit_predict(X)),
    ]:
        sil, dbi = cluster_metrics(X, labels)
        n_clusters = len(set(labels[labels >= 0])) if (labels >= 0).any() else 0
        out[name] = {"silhouette": sil, "davies_bouldin": dbi, "n_clusters": n_clusters}
    return {"k_used": k, "elbow": elbow, "models": out}

@app.get("/api/summary")
def summary():
    with db() as c:
        seg = [dict(r) for r in c.execute("""SELECT segment, COUNT(*) n, ROUND(AVG(recency),1) recency,
            ROUND(AVG(frequency),1) frequency, ROUND(AVG(monetary),0) monetary FROM customers
            WHERE segment IS NOT NULL GROUP BY segment""")]
        pts = [dict(r) for r in c.execute("SELECT x,y,segment FROM customers WHERE segment IS NOT NULL")]
        meta = {r["k"]: r["v"] for r in c.execute("SELECT * FROM meta")}
        total = c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        sent = c.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
    rank = {n: i for i, n in enumerate(["Champions", "Loyal", "Promising", "At-Risk", "Lost"])}
    seg.sort(key=lambda s: rank.get(s["segment"], 9))
    for s in seg: s["action"] = ACTIONS[s["segment"]]
    return {"total": total, "segments": seg, "points": pts, "meta": meta, "sent": sent}

@app.get("/api/customers")
def customers(segment: str = "", q: str = "", limit: int = 200):
    sql, args = "SELECT id,name,email,recency,frequency,monetary,segment FROM customers WHERE 1=1", []
    if segment: sql += " AND segment=?"; args.append(segment)
    if q: sql += " AND (name LIKE ? OR email LIKE ?)"; args += [f"%{q}%"] * 2
    with db() as c: return [dict(r) for r in c.execute(sql + " LIMIT ?", args + [limit])]

def send_email(to, subject, body):
    """Optional real email: set SMTP_USER and SMTP_PASS (Gmail app password). Otherwise skipped."""
    u, p = os.getenv("SMTP_USER"), os.getenv("SMTP_PASS")
    if not u: return False
    m = EmailMessage(); m["From"], m["To"], m["Subject"] = u, to, subject; m.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s: s.login(u, p); s.send_message(m)
    return True

@app.post("/api/login")
def login(body: LoginBody):
    email = body.email.strip().lower()
    if not email:
        raise HTTPException(400, "Email required")
    if email == ADMIN_EMAIL:
        role, cid = "admin", None
    else:
        with db() as c:
            row = c.execute("SELECT id FROM customers WHERE lower(email)=?", (email,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown email. Admin: admin@segmentiq.com or a customer c{id}@example.com")
        role, cid = "customer", int(row["id"])
    token = secrets.token_urlsafe(24)
    now = datetime.now().isoformat(timespec="seconds")
    with db() as c:
        c.execute("INSERT INTO sessions(token,email,role,customer_id,created) VALUES(?,?,?,?,?)",
                  (token, email, role, cid, now))
    return {"token": token, "role": role, "email": email, "customer_id": cid}

@app.get("/api/me")
def me(authorization: str = Header(default="")):
    user = auth_user(authorization)
    if not user:
        raise HTTPException(401, "Not logged in")
    return {"email": user["email"], "role": user["role"], "customer_id": user["customer_id"]}

@app.get("/api/account")
def account(authorization: str = Header(default="")):
    user = auth_user(authorization)
    if not user or user["role"] != "customer" or not user["customer_id"]:
        raise HTTPException(403, "Customer login required")
    cid = user["customer_id"]
    with db() as c:
        n = [dict(r) for r in c.execute(
            "SELECT id,title,message,created,read_flag FROM notifications WHERE customer_id=? ORDER BY id DESC", (cid,))]
        k = [dict(r) for r in c.execute(
            "SELECT code,discount,created FROM coupons WHERE customer_id=? ORDER BY id DESC", (cid,))]
    return {"notifications": n, "coupons": k}

@app.post("/api/notifications/{nid}/read")
def mark_read(nid: int, authorization: str = Header(default="")):
    user = auth_user(authorization)
    if not user or user["role"] != "customer":
        raise HTTPException(403, "Customer login required")
    with db() as c:
        row = c.execute("SELECT customer_id FROM notifications WHERE id=?", (nid,)).fetchone()
        if not row or row["customer_id"] != user["customer_id"]:
            raise HTTPException(404, "Notification not found")
        c.execute("UPDATE notifications SET read_flag=1 WHERE id=?", (nid,))
    return {"ok": True}

@app.get("/api/campaigns")
def campaign_history():
    with db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT id,segment,sent_at,num_customers,discount FROM campaign_log ORDER BY id DESC LIMIT 100")]
    return rows

@app.post("/api/campaign/{segment}")
def campaign(segment: str, override: bool = False, authorization: str = Header(default="")):
    user = auth_user(authorization)
    if not user or user["role"] != "admin":
        raise HTTPException(403, "Admin login required to send campaigns")
    if segment not in ACTIONS:
        raise HTTPException(404, "Unknown segment")
    title, msg, pct = ACTIONS[segment]
    now = datetime.now()
    with db() as c:
        last = c.execute(
            "SELECT sent_at FROM campaign_log WHERE segment=? ORDER BY id DESC LIMIT 1", (segment,)).fetchone()
        if last and not override:
            sent = datetime.fromisoformat(last["sent_at"])
            if now - sent < timedelta(hours=24):
                raise HTTPException(409, "Same segment was emailed within 24h; retry with ?override=true")
        rows = c.execute("SELECT id,email FROM customers WHERE segment=?", (segment,)).fetchall()
        emailed = 0
        ts = now.isoformat(timespec="seconds")
        for r in rows:
            code = segment[:3].upper() + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            c.execute("INSERT INTO notifications(customer_id,title,message,created) VALUES(?,?,?,?)",
                      (r["id"], title, f"{msg} Use code {code} for {pct}% off.", ts))
            c.execute("INSERT INTO coupons(customer_id,code,discount,created) VALUES(?,?,?,?)", (r["id"], code, pct, ts))
            if emailed < 5 and send_email(r["email"], title, f"{msg} Code: {code} ({pct}% off)"):
                emailed += 1
        c.execute("INSERT INTO campaign_log(segment,sent_at,num_customers,discount) VALUES(?,?,?,?)",
                  (segment, ts, len(rows), pct))
    return {"segment": segment, "customers_notified": len(rows), "discount": pct, "emails_sent": emailed}

@app.get("/api/customers/{cid}/inbox")
def inbox(cid: int):
    with db() as c:
        n = [dict(r) for r in c.execute(
            "SELECT id,title,message,created,read_flag FROM notifications WHERE customer_id=? ORDER BY id DESC", (cid,))]
        k = [dict(r) for r in c.execute("SELECT code,discount,created FROM coupons WHERE customer_id=? ORDER BY id DESC", (cid,))]
    return {"notifications": n, "coupons": k}

@app.get("/")
def index(): return FileResponse("static/index.html")
