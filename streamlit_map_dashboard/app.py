
import os, json, requests, pandas as pd, streamlit as st
from datetime import datetime, date
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster

st.set_page_config(page_title="Orders Map (Monday.com)", layout="wide")

# === Secrets / env ===
API_TOKEN = st.secrets.get("MONDAY_API_TOKEN", os.getenv("MONDAY_API_TOKEN", ""))
BOARD_ID = st.secrets.get("MONDAY_BOARD_ID", os.getenv("MONDAY_BOARD_ID", ""))
SUBDOMAIN = st.secrets.get("MONDAY_SUBDOMAIN", os.getenv("MONDAY_SUBDOMAIN", ""))  # youraccount.monday.com (only the subdomain part)

if not API_TOKEN or not BOARD_ID:
    st.warning("Add MONDAY_API_TOKEN and MONDAY_BOARD_ID in Streamlit secrets (or as env vars) to load live data. Showing an empty app until secrets are set.")
    
# === Column mapping (edit these to match your board) ===
with st.sidebar:
    st.header("Settings")
    st.caption("Set your Monday column IDs. IDs are visible in the column settings or via the API. "
               "You can also use the column 'title' but IDs are more reliable.")
    location_col = st.text_input("Location column ID", value="location")
    value_col = st.text_input("Order value column ID", value="order_value")
    status_col = st.text_input("Status column ID (optional)", value="status")
    date_col = st.text_input("Date column ID (optional)", value="date")
    customer_col = st.text_input("Customer/Clinic column ID (optional)", value="customer")
    city_col = st.text_input("City column ID (optional)", value="city")
    state_col = st.text_input("State column ID (optional)", value="state")
    country_col = st.text_input("Country column ID (optional)", value="country")
    extra_cols_str = st.text_input("Other column IDs (comma-separated, optional)", value="")
    cluster_markers = st.toggle("Cluster markers", value=True)
    st.markdown("---")
    st.caption("Tip: The Monday 'Location' column can be used directly; this app will parse lat/lng from it.")

def _cv_to_dict(cv):
    # Monday returns {"id": "...", "text": "...", "value": "{...json...} or None"}
    if not isinstance(cv, dict): 
        return {"id": None, "text": None, "value": None}
    out = {"id": cv.get("id"), "text": cv.get("text"), "value": None}
    try:
        if cv.get("value"):
            out["value"] = json.loads(cv["value"])
    except Exception:
        out["value"] = cv.get("value")
    return out

def parse_location(value_obj, text_fallback):
    # Handles Monday Location column (lat/lng stored in JSON) or "lat, lng" text
    if isinstance(value_obj, dict) and "lat" in value_obj and "lng" in value_obj:
        return value_obj.get("lat"), value_obj.get("lng"), value_obj.get("address")
    if text_fallback and "," in text_fallback:
        try:
            lat, lng = [float(x.strip()) for x in text_fallback.split(",")[:2]]
            return lat, lng, None
        except Exception:
            return None, None, None
    return None, None, None

@st.cache_data(ttl=60, show_spinner=False)
def fetch_items(board_id, api_token, wanted_ids):
    if not api_token or not board_id:
        return pd.DataFrame()

    headers = {
        "Authorization": api_token,
        "Content-Type": "application/json"
    }
    url = "https://api.monday.com/v2"
    cursor = None
    rows = []

    while True:
        query = """
        query($board_id: [Int], $cursor: String) {
          boards (ids: $board_id) {
            items_page (limit: 500, cursor: $cursor) {
              cursor
              items {
                id
                name
                created_at
                updated_at
                column_values {
                  id
                  text
                  value
                }
              }
            }
          }
        }
        """
        variables = {"board_id": int(board_id), "cursor": cursor}
        resp = requests.post(url, headers=headers, json={"query": query, "variables": variables})
        resp.raise_for_status()
        data = resp.json()
        items_page = data["data"]["boards"][0]["items_page"]
        items = items_page["items"]
        cursor = items_page["cursor"]

        for it in items:
            cv_map = {cv["id"]: _cv_to_dict(cv) for cv in it["column_values"]}
            # parse location
            loc_cv = cv_map.get(wanted_ids["location"], {"text": None, "value": None})
            lat, lng, address = parse_location(loc_cv.get("value"), loc_cv.get("text"))

            def get_text(cid):
                if cid in cv_map:
                    return cv_map[cid].get("text")
                return None

            def get_raw_value(cid):
                if cid in cv_map:
                    return cv_map[cid].get("value")
                return None

            row = {
                "item_id": it["id"],
                "name": it["name"],
                "created_at": it["created_at"],
                "updated_at": it["updated_at"],
                "lat": lat,
                "lng": lng,
                "address": address,
                "order_value": None,
                "status": None,
                "date": None,
                "customer": None,
                "city": None,
                "state": None,
                "country": None
            }
            # texts
            row["order_value"] = get_text(wanted_ids["value"])
            row["status"] = get_text(wanted_ids["status"]) if wanted_ids["status"] else None
            row["date"] = get_text(wanted_ids["date"]) if wanted_ids["date"] else None
            row["customer"] = get_text(wanted_ids["customer"]) if wanted_ids["customer"] else None
            row["city"] = get_text(wanted_ids["city"]) if wanted_ids["city"] else None
            row["state"] = get_text(wanted_ids["state"]) if wanted_ids["state"] else None
            row["country"] = get_text(wanted_ids["country"]) if wanted_ids["country"] else None

            # extras
            for ec in wanted_ids.get("extras", []):
                row[f"extra__{ec}"] = get_text(ec)

            rows.append(row)

        if not cursor:
            break

    df = pd.DataFrame(rows)
    # convert order value numeric if possible
    if "order_value" in df.columns:
        df["order_value_num"] = pd.to_numeric(df["order_value"].str.replace(",","").str.extract(r'([\d\.]+)')[0], errors="coerce")
    else:
        df["order_value_num"] = None

    # parse date if present
    if "date" in df.columns and df["date"].notna().any():
        df["date_parsed"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    else:
        df["date_parsed"] = None

    return df

wanted_ids = {
    "location": location_col.strip(),
    "value": value_col.strip(),
    "status": status_col.strip() or None,
    "date": date_col.strip() or None,
    "customer": customer_col.strip() or None,
    "city": city_col.strip() or None,
    "state": state_col.strip() or None,
    "country": country_col.strip() or None,
    "extras": [c.strip() for c in (extra_cols_str.split(",") if extra_cols_str else []) if c.strip()]
}

df = fetch_items(BOARD_ID, API_TOKEN, wanted_ids)

st.title("📍 Orders Map (from Monday.com)")
st.caption("Filter by order value, status, and date. Click any marker to see order details.")

# --- KPI row ---
k1, k2, k3, k4 = st.columns(4)
if not df.empty and df["order_value_num"].notna().any():
    k1.metric("Total Orders", int(len(df)))
    k2.metric("Total Value", f"${df['order_value_num'].sum():,.0f}")
    k3.metric("Avg Value", f"${df['order_value_num'].mean():,.0f}")
else:
    k1.metric("Total Orders", int(len(df)))
    k2.metric("Total Value", "-")
    k3.metric("Avg Value", "-")
k4.metric("Last Refreshed", datetime.now().strftime("%H:%M:%S"))

# --- Filters ---
with st.expander("Filters", expanded=True):
    c1, c2, c3, c4 = st.columns([2,2,2,2])
    # Order value slider
    if not df.empty and df["order_value_num"].notna().any():
        mn, mx = float(df["order_value_num"].min()), float(df["order_value_num"].max())
        val_range = c1.slider("Order value range", min_value=0.0, max_value=max(mx, 1.0), value=(0.0, max(mx, 1.0)))
    else:
        val_range = (0.0, 999999999.0)
        c1.write("Order value not set or non-numeric.")

    # Status multiselect
    status_options = sorted([s for s in df["status"].dropna().unique().tolist()]) if "status" in df.columns else []
    status_sel = c2.multiselect("Status", options=status_options, default=status_options)

    # Date range
    if "date_parsed" in df.columns and df["date_parsed"].notna().any():
        mind = df["date_parsed"].min()
        maxd = df["date_parsed"].max()
        date_range = c3.date_input("Date range", value=(mind, maxd))
    else:
        date_range = None
        c3.write("No valid date column.")

    # Search
    q = c4.text_input("Search (customer / name / city)", value="").strip().lower()

# Apply filters
def apply_filters(df):
    out = df.copy()
    if "order_value_num" in out.columns:
        out = out[(out["order_value_num"].fillna(0) >= val_range[0]) & (out["order_value_num"].fillna(0) <= val_range[1])]
    if "status" in out.columns and status_options:
        if status_sel:
            out = out[out["status"].isin(status_sel)]
    if date_range and isinstance(date_range, (list, tuple)) and len(date_range) == 2 and out["date_parsed"].notna().any():
        start, end = date_range
        out = out[(out["date_parsed"] >= start) & (out["date_parsed"] <= end)]
    if q:
        mask = (
            out.get("customer","").astype(str).str.lower().str.contains(q) |
            out.get("name","").astype(str).str.lower().str.contains(q) |
            out.get("city","").astype(str).str.lower().str.contains(q)
        )
        out = out[mask]
    return out

fdf = apply_filters(df)

# --- Map ---
if fdf.empty or fdf["lat"].isna().all():
    st.info("No items with valid latitude/longitude yet.")
else:
    lat0 = fdf["lat"].dropna().mean()
    lng0 = fdf["lng"].dropna().mean()
    m = folium.Map(location=[lat0, lng0], tiles="cartodbpositron", zoom_start=4)
    marker_group = MarkerCluster() if cluster_markers else folium.FeatureGroup(name="Orders")
    if cluster_markers:
        m.add_child(marker_group)
    else:
        m.add_child(marker_group)

    def popup_html(row):
        url = f"https://{SUBDOMAIN}.monday.com/boards/{BOARD_ID}/pulses/{row['item_id']}" if SUBDOMAIN else None
        parts = []
        parts.append(f"<b>{row.get('name','')}</b>")
        if row.get('customer'):
            parts.append(f"Customer: {row['customer']}")
        if row.get('order_value'):
            parts.append(f"Order Value: {row['order_value']}")
        if row.get('status'):
            parts.append(f"Status: {row['status']}")
        if row.get('date'):
            parts.append(f"Date: {row['date']}")
        if row.get('city') or row.get('state'):
            parts.append(f"Location: {row.get('city','')}, {row.get('state','')}")
        if row.get('address'):
            parts.append(f"Address: {row['address']}")
        if url:
            parts.append(f"<a target='_blank' href='{url}'>Open in Monday</a>")
        return "<br>".join(parts)

    for _, r in fdf.dropna(subset=["lat","lng"]).iterrows():
        folium.Marker(
            location=[r["lat"], r["lng"]],
            popup=folium.Popup(popup_html(r), max_width=350),
            tooltip=r.get("name","Order")
        ).add_to(marker_group)

    st_data = st_folium(m, use_container_width=True, returned_objects=[])

st.markdown("---")
st.subheader("Data")
st.dataframe(fdf, use_container_width=True)
st.download_button("Download filtered CSV", data=fdf.to_csv(index=False).encode("utf-8"), file_name="orders_filtered.csv", mime="text/csv")

st.caption("Tip: This app reads directly from Monday's GraphQL API (no intermediate spreadsheets). Refresh the page to fetch the latest data. Cache TTL is 60s by default.")
