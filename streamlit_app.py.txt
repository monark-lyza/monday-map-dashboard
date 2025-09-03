import os, json, time, requests, pandas as pd
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster

# --------- SETTINGS via Secrets ----------
MONDAY_TOKEN = os.getenv("MONDAY_TOKEN")
BOARD_ID = os.getenv("MONDAY_BOARD_ID")
ORDER_VALUE_COLUMN_TITLE = os.getenv("ORDER_VALUE_TITLE", "Order Value")
LOCATION_COLUMN_TITLE = os.getenv("LOCATION_TITLE", "Location")
EXTRA_DETAIL_COLUMNS = [c.strip() for c in os.getenv("DETAIL_TITLES","Customer,Status,Order Date").split(",") if c.strip()]
AUTO_REFRESH_SECONDS = int(os.getenv("AUTO_REFRESH_SECONDS","60"))
# -----------------------------------------

st.set_page_config(page_title="Orders Map", layout="wide")
st.title("Orders Map (live from monday.com)")
st.caption(f"Auto-refresh every {AUTO_REFRESH_SECONDS}s")

def monday(query, variables=None):
    headers = {"Authorization": MONDAY_TOKEN, "Content-Type": "application/json"}
    r = requests.post("https://api.monday.com/v2", headers=headers,
                      json={"query": query, "variables": variables or {}}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data: raise RuntimeError(data["errors"])
    return data["data"]

# Map column titles -> ids so this works with your names
cols_resp = monday("""
query($board_id:[Int]) {
  boards(ids:$board_id) {
    columns { id title type }
  }
}
""", {"board_id": int(BOARD_ID)})

title_to_id = {c["title"]: c["id"] for c in cols_resp["boards"][0]["columns"]}
loc_col_id   = title_to_id.get(LOCATION_COLUMN_TITLE)
value_col_id = title_to_id.get(ORDER_VALUE_COLUMN_TITLE)

# Pull all items (pagination)
items = []
cursor = None
while True:
    resp = monday("""
    query($board_id:[Int], $cursor:String) {
      boards(ids:$board_id) {
        items_page(limit:250, cursor:$cursor) {
          cursor
          items {
            id name updated_at
            column_values { id title text value }
          }
        }
      }
    }""", {"board_id": int(BOARD_ID), "cursor": cursor})
    page = resp["boards"][0]["items_page"]
    items.extend(page["items"])
    cursor = page["cursor"]
    if not cursor: break

def parse_location(raw_value, raw_text):
    # Works for monday JSON and "lat,lng" text
    if raw_value:
        try:
            j = json.loads(raw_value)
            if isinstance(j, dict) and "lat" in j and "lng" in j:
                return float(j["lat"]), float(j["lng"]), j.get("address","")
        except Exception:
            pass
    if raw_text and "," in raw_text:
        try:
            lat_s, lng_s = raw_text.split(",", 1)
            return float(lat_s.strip()), float(lng_s.strip()), ""
        except Exception:
            pass
    return None, None, ""

rows = []
for it in items:
    vals = {cv["title"]: cv for cv in it["column_values"]}
    # order value → number
    val_txt = (vals.get(ORDER_VALUE_COLUMN_TITLE, {}).get("text") or "").replace("$","").replace(",","").strip()
    try: order_val = float(val_txt) if val_txt else None
    except: order_val = None
    # location
    lat, lng, addr = parse_location(
        vals.get(LOCATION_COLUMN_TITLE, {}).get("value"),
        vals.get(LOCATION_COLUMN_TITLE, {}).get("text")
    )
    if lat is None or lng is None or order_val is None: continue

    row = {
        "id": it["id"], "name": it["name"], "updated_at": it["updated_at"],
        "order_value": order_val, "lat": lat, "lng": lng, "address": addr
    }
    for t in EXTRA_DETAIL_COLUMNS:
        row[t] = vals.get(t, {}).get("text")
    rows.append(row)

df = pd.DataFrame(rows)
if df.empty:
    st.warning("No mappable rows found (check column titles or data)."); st.stop()

# Filters
left, mid, right = st.columns([2,1,2])
with left:
    lo, hi = int(df["order_value"].min()), int(df["order_value"].max())
    vmin, vmax = st.slider("Order value range", lo, hi, (lo, hi), step=1)
with mid:
    st.write("")
    if st.button("Refresh now"): st.rerun()
with right:
    q = st.text_input("Search name/customer (optional)", "")

mask = (df["order_value"]>=vmin) & (df["order_value"]<=vmax)
if q:
    ql = q.lower()
    mask &= df.apply(lambda r: ql in str(r["name"]).lower() or any(ql in str(r.get(t,"")).lower() for t in EXTRA_DETAIL_COLUMNS), axis=1)
filtered = df[mask].copy()

# Map
m = folium.Map(location=[filtered["lat"].mean(), filtered["lng"].mean()], zoom_start=4, tiles="OpenStreetMap")
cluster = MarkerCluster().add_to(m)
fmt = lambda x: "${:,.0f}".format(float(x)) if x not in (None,"") else "—"

for _, r in filtered.iterrows():
    html = f"<b>{r['name']}</b><br>Value: {fmt(r['order_value'])}<br>Address: {r.get('address') or '—'}"
    for t in EXTRA_DETAIL_COLUMNS:
        v = r.get(t);  html += f"<br>{t}: {v}" if v else ""
    html += f"<br><a href='https://view.monday.com/boards/{BOARD_ID}/pulses/{r['id']}' target='_blank'>Open in monday</a>"
    folium.CircleMarker(
        location=[r["lat"], r["lng"]], radius=6, weight=1, fill=True, fill_opacity=0.85,
        popup=folium.Popup(html, max_width=320),
        tooltip=f"{r['name']} • {fmt(r['order_value'])}"
    ).add_to(cluster)

out = st_folium(m, width=1100, height=600)

# Details panel
st.markdown("### Selected order")
selected = None
if out and out.get("last_object_clicked"):
    latc = round(out["last_object_clicked"]["lat"], 5)
    lngc = round(out["last_object_clicked"]["lng"], 5)
    filtered["dist"] = (filtered["lat"].round(5).sub(latc).abs() + filtered["lng"].round(5).sub(lngc).abs())
    selected = filtered.nsmallest(1, "dist").drop(columns=["dist"]).to_dict("records")[0]
if selected:
    details = {
        "Name": selected["name"],
        "Order Value": fmt(selected["order_value"]),
        "Address": selected.get("address"),
        **{t: selected.get(t) for t in EXTRA_DETAIL_COLUMNS},
        "monday link": f"https://view.monday.com/boards/{BOARD_ID}/pulses/{selected['id']}"
    }
    st.write(details)
else:
    st.info("Click a marker to see full details here.")

# Light auto-refresh (keeps UX simple on Streamlit Cloud)
st.caption("Tip: use the Refresh button above if needed.")
