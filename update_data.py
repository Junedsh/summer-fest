import os
import pandas as pd
import toml
import subprocess
from sqlalchemy import create_engine

# ─── Load Secrets ─────────────────────────────────────────────────────────────
# We load from local .streamlit/secrets.toml
try:
    secrets = toml.load(".streamlit/secrets.toml")
    rs = secrets.get("redshift", {})
except Exception as e:
    print("Error loading secrets:", e)
    exit(1)

DB_USER     = rs.get("user")
DB_PASSWORD = rs.get("password")
DB_HOST     = rs.get("host")
DB_PORT     = rs.get("port")
DB_NAME     = "prod2-generico"
SCHEMA      = "prod2-generico"

def get_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)

# ─── Drug IDs ──────────────────────────────────────────────────────────────────
DRUG_IDS = (
    56119,57077,759105,499772,499771,
    758696,758707,522142,658028,412912,410448,513711,514824,487154,495969,502937,510083,
    759024,513715,759152,759153,759154,490446,617966,514194,514146,519888,519887,519274,522971,519275,630789,758887,
    500093,500094,755165,519304,513380,632714,755205,500343,758512,755166,758853,617692,755163,488841,758855,758880,
    758882,758883,395023,523051,499171,500441,632188,632209,632210,758885,758886,632208,514786,758901,758951,
    758903,512589,514407,758957,758907,514790,758900,522144
)

print("Connecting to Redshift...")
engine = get_engine()
drug_list = ",".join(str(d) for d in DRUG_IDS)

query = f"""
    SELECT
        s."created-date"                AS transaction_date,
        s.abo,
        s."line-manager"                AS line_manager,
        s."store-name"                  AS store_name,
        s."bill-flag"                   AS bill_flag,
        s."promo-code"                  AS promo_code,
        s."promo-discount"              AS promo_discount,
        s."drug-name"                   AS drug_name,
        s."net-quantity"                AS net_quantity,

        ( (s."revenue-value"
            - CASE WHEN s."promo-code" LIKE 'ZRF%' THEN s."promo-discount" ELSE 0 END)
            / NULLIF(1.0 + ((s."sgst-rate" + s."cgst-rate" + s."igst-rate") / 100.0), 0)
        ) AS revenue_excl_tax,
        (s."revenue-value" - CASE WHEN s."promo-code" LIKE 'ZRF%' THEN s."promo-discount" else 0 end ) as rev_with_tax,

        ( CASE WHEN s."promo-code" LIKE 'ZRF%' AND s."promo-discount" > 0
                THEN (s."purchase-rate" * s."net-quantity")
                    / NULLIF(1.0 + ((ii."sgst-rate" + ii."cgst-rate" + ii."igst-rate") / 100.0), 0)
                ELSE 0 END
        ) AS zrf_purchase_excl_tax,

        ( (s."purchase-rate" * s."net-quantity")
            / NULLIF(1.0 + ((ii."sgst-rate" + ii."cgst-rate" + ii."igst-rate") / 100.0), 0)
        ) AS purchase_excl_tax

    FROM "{SCHEMA}".sales s
    LEFT JOIN "{SCHEMA}"."inventory-1" i
        ON s."inventory-id" = i.id
    LEFT JOIN "{SCHEMA}"."invoice-items-1" ii
        ON i."invoice-item-id" = ii.id
    WHERE s."created-date" >= '2026-04-01'
        AND s."created-date" <= '2026-05-31'
        AND s."created-date" <  CURRENT_DATE
        AND s."franchisee-id" = 1
        AND s."drug-id" IN ({drug_list})
"""

print("Executing query and fetching data...")
with engine.connect() as conn:
    df = pd.read_sql(query, conn)
engine.dispose()

print(f"Data fetched! Shape: {df.shape}")
df.to_csv("data.csv", index=False)
print("Saved to data.csv")

# ─── Push to GitHub ───────────────────────────────────────────────────────────
print("Pushing data to GitHub...")
try:
    subprocess.run(["git", "add", "data.csv"], check=True)
    subprocess.run(["git", "commit", "-m", "Automated data refresh"], check=True)
    subprocess.run(["git", "push", "origin", "main"], check=True)
    print("Successfully pushed data to GitHub!")
except subprocess.CalledProcessError as e:
    print("Error during git push. (Did the data change?)", e)
