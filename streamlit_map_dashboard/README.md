
# Orders Map Dashboard (Monday.com → Streamlit)

A no-cost, executive-friendly map dashboard that pulls live data from a Monday.com board and shows clickable map markers with full order details + ad‑hoc filters.

## What you get
- 🗺️ Interactive map (Leaflet via Folium) with optional clustering
- 🔎 Filters: order value range, status, date range, search
- 🧾 Click any marker to see order details + link back to the Monday item
- 📥 Download filtered CSV
- ⚡ Fetches data directly from Monday GraphQL API (near real‑time)

## 1) Create a Monday API token
1. In Monday: click your avatar → **Developers** → **API tokens** → **Generate**.
2. Copy the token.

## 2) Find your Board ID + column IDs
- Board ID: open your board; URL looks like `https://YOURSUBDOMAIN.monday.com/boards/123456789/views/...` → **123456789** is the board ID.
- Column IDs: open column settings → "Developer" info; or call the API once and inspect the `column_values` array.

> If your location is a single *Location* column, keep it. This app parses `lat/lng` from that JSON automatically.

## 3) Deploy (free) on Streamlit Cloud
1. Push this folder to a **public GitHub repo**.
2. Go to https://share.streamlit.io → **New app** → point to your repo.
3. In the Streamlit app → **Settings → Secrets**, add:

```
MONDAY_API_TOKEN = "YOUR_LONG_TOKEN"
MONDAY_BOARD_ID = "123456789"
MONDAY_SUBDOMAIN = "your-subdomain"
```

4. Click **Deploy**. The app will build and open.
5. In the app sidebar, set your column IDs (defaults are `location`, `order_value`, `status`, `date`, `customer`).

## 4) Use it inside Monday (optional)
In a **Dashboard** → **Add Widget** → **Website** (or **Embed**) → paste your Streamlit app URL.  
If your org blocks iframes, you can keep it as a separate link or host on Vercel/Render with headers adjusted.

## FAQ
### Is the Monday Location column usable?
Yes. Monday’s Location column stores JSON like `{"lat": 43.65, "lng": -79.38, "address": "Toronto, ON, Canada"}`. This app parses that JSON and falls back to `lat, lng` in the text if needed.

### How “real‑time” is this?
Every page refresh calls Monday’s API (cache TTL is 60 seconds by default), so you always see fresh data without waiting for a 3rd‑party sync.

### Can I extend the popup with more fields?
Yes—add the column IDs in the sidebar or hard‑code more IDs in `wanted_ids`, then include them inside `popup_html(...)`.

### Private data?
The app fetches data *at view time* using your token stored as a secret in Streamlit Cloud. No data is stored in the repo.

---

Made for you 💙
