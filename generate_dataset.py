"""Generates a synthetic Online-Retail-style transactions CSV (same columns as the UCI dataset)."""
import numpy as np, pandas as pd
rng = np.random.default_rng(7)
END = pd.Timestamp("2025-12-31")
PRODUCTS = [("P1001","Ceramic Mug",6.5),("P1002","Scented Candle",12),("P1003","Notebook A5",4.5),("P1004","Desk Lamp",28),
 ("P1005","Wireless Mouse",19),("P1006","Yoga Mat",24),("P1007","Water Bottle",11),("P1008","Backpack",45),
 ("P1009","Bluetooth Speaker",39),("P1010","Throw Pillow",15),("P1011","Plant Pot",9),("P1012","Wall Clock",22),
 ("P1013","Phone Case",8),("P1014","Coffee Grinder",34),("P1015","Tote Bag",7.5),("P1016","Photo Frame",13)]
COUNTRIES = ["India"]*6 + ["United Arab Emirates"]*2 + ["United Kingdom", "Singapore"]
# (share, orders mean, days since last order mean, basket size mean)
ARCH = [(.12, 22, 12, 6), (.25, 9, 45, 4), (.2, 3, 30, 3), (.23, 5, 160, 3), (.2, 1.4, 300, 2)]
rows, inv, cid = [], 20000, 12000
for share, orders, rec, basket in ARCH:
    for _ in range(int(800 * share)):
        cid += 1; country = str(rng.choice(COUNTRIES))
        n = max(1, int(rng.poisson(orders))); last = max(1, int(rng.lognormal(np.log(rec), .4)))
        span = int(min(364, last + rng.integers(30, 330)))
        days = np.sort(rng.integers(last, max(last + 1, span), n))
        days[0] = last
        for d in days:
            inv += 1; date = END - pd.Timedelta(days=int(d), hours=int(rng.integers(8, 21)), minutes=int(rng.integers(0, 60)))
            for pi in rng.choice(len(PRODUCTS), size=max(1, int(rng.poisson(basket))), replace=False):
                code, desc, price = PRODUCTS[pi]
                rows.append((f"INV{inv}", code, desc, int(rng.integers(1, 5)), date.strftime("%Y-%m-%d %H:%M"),
                             round(price * rng.uniform(.95, 1.05), 2), cid, country))
df = pd.DataFrame(rows, columns=["InvoiceNo","StockCode","Description","Quantity","InvoiceDate","UnitPrice","CustomerID","Country"])
df.to_csv("retail_transactions.csv", index=False); print(len(df), "rows,", df.CustomerID.nunique(), "customers")
