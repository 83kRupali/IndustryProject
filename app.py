import os
import io
import csv
import requests
from flask import Flask, request, jsonify, render_template, send_file
from dotenv import load_dotenv

load_dotenv()  # load .env file

app = Flask(__name__)

# ---------------- Supabase configuration ----------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
API_KEY = os.environ.get("SUPABASE_API_KEY")

if not SUPABASE_URL or not API_KEY:
    raise RuntimeError(
        "Environment variables SUPABASE_URL or SUPABASE_API_KEY are missing. "
        "Set them in Render dashboard."
    )

HEADERS = {
    "apikey": API_KEY,
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ---------------- Helper functions ----------------
def fetch_distinct(column):
    """Fetch distinct values for a column"""
    url = f"{SUPABASE_URL}/rest/v1/forecasts"
    params = {"select": column}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    data = r.json()
    return sorted({row[column] for row in data if row[column] is not None})

def fetch_forecasts(store_id, product_id, start_date=None, end_date=None):
    url = f"{SUPABASE_URL}/rest/v1/forecasts"
    params = {
        "select": "*",
        "store_id": f"eq.{store_id}",
        "product_id": f"eq.{product_id}",
        "order": "forecast_date.asc"
    }
    if start_date and end_date:
        params["forecast_date"] = f"gte.{start_date},lte.{end_date}"
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()

def fetch_top_skus(limit=10):
    """Fetch top SKUs by total forecast"""
    url = f"{SUPABASE_URL}/rest/v1/forecasts"
    params = {"select": "product_id,forecast_qty"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    data = r.json()
    totals = {}
    for row in data:
        pid = row["product_id"]
        totals[pid] = totals.get(pid, 0) + row["forecast_qty"]
    # Sort by total descending
    top = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"product_id": pid, "total_forecast": total} for pid, total in top]

def fetch_critical_skus():
    """SKUs with min forecast < 5"""
    url = f"{SUPABASE_URL}/rest/v1/forecasts"
    params = {"select": "product_id,forecast_qty"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    data = r.json()
    min_qtys = {}
    for row in data:
        pid = row["product_id"]
        min_qtys[pid] = min(min_qtys.get(pid, row["forecast_qty"]), row["forecast_qty"])
    critical = [{"product_id": pid, "min_qty": q} for pid, q in min_qtys.items() if q < 5]
    return critical

# ---------------- Routes ----------------
@app.route("/")
def dashboard():
    try:
        stores = fetch_distinct("store_id")
        skus = fetch_distinct("product_id")
        return render_template("dashboard.html", stores=stores, skus=skus)
    except Exception as e:
        return f"Error fetching dashboard data: {e}", 500

@app.route("/forecast", methods=["POST"])
def forecast():
    store_id = request.form.get("store_id")
    product_id = request.form.get("product_id")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")

    if not store_id or not product_id:
        return jsonify({"error": "store_id and product_id are required"}), 400

    try:
        rows = fetch_forecasts(store_id, product_id, start_date, end_date)
        if not rows:
            return jsonify({"error": "No forecast found"}), 404

        latest = rows[-1]
        history = [{"date": r["forecast_date"], "qty": r["forecast_qty"], "model": r["model"]} for r in rows]
        quantities = [r["forecast_qty"] for r in rows]
        stats = {"avg": round(sum(quantities)/len(quantities), 2), "max": max(quantities), "min": min(quantities)}

        return jsonify({
            "latest": {"forecast_qty": latest["forecast_qty"], "forecast_date": latest["forecast_date"], "model": latest["model"]},
            "history": history,
            "stats": stats,
            "top_skus": fetch_top_skus(),
            "critical_skus": fetch_critical_skus()
        })
    except Exception as e:
        return jsonify({"error": f"Query failed: {e}"}), 500

@app.route("/export", methods=["POST"])
def export_csv():
    store_id = request.form.get("store_id")
    product_id = request.form.get("product_id")

    if not store_id or not product_id:
        return jsonify({"error": "store_id and product_id are required"}), 400

    try:
        rows = fetch_forecasts(store_id, product_id)
        if not rows:
            return jsonify({"error": "No data to export"}), 404

        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(["forecast_date", "store_id", "product_id", "forecast_qty", "model"])
        for r in rows:
            cw.writerow([r["forecast_date"], r["store_id"], r["product_id"], r["forecast_qty"], r["model"]])

        output = io.BytesIO()
        output.write(si.getvalue().encode("utf-8"))
        output.seek(0)

        filename = f"forecast_{store_id}_{product_id}.csv"
        return send_file(output, as_attachment=True, download_name=filename, mimetype="text/csv")
    except Exception as e:
        return jsonify({"error": f"Export failed: {e}"}), 500


@app.route("/profile")
def profile():
    user = {
        "name": "John Doe",
        "email": "john.doe@example.com",
        "role": "Inventory Manager",
        "joined": "2023-01-15"
    }
    return render_template("profile.html", user=user)


# ---------------- Run App ----------------
if __name__ == "__main__":
    app.run(debug=True)
