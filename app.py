import psycopg2
from flask import Flask, request, jsonify, render_template, send_file
import io
import csv
import os

from datetime import datetime

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST"),
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        port=os.environ.get("DB_PORT"),
        sslmode="require"
    )

# Dashboard route
@app.route('/')
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT store_id FROM forecasts ORDER BY store_id")
    stores = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT product_id FROM forecasts ORDER BY product_id")
    skus = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return render_template("dashboard.html", stores=stores, skus=skus)

# Profile route
@app.route('/profile')
def profile():
    user = {
        "name": "John Doe",
        "email": "john.doe@example.com",
        "role": "Inventory Manager",
        "joined": "2023-01-15"
    }
    return render_template("profile.html", user=user)

# Forecast API
@app.route('/forecast', methods=['POST'])
def forecast():
    store_id = request.form.get('store_id')
    product_id = request.form.get('product_id')
    start_date = request.form.get('start_date')  # optional
    end_date = request.form.get('end_date')      # optional

    query = "SELECT forecast_date, forecast_qty, model FROM forecasts WHERE store_id=%s AND product_id=%s"
    params = [store_id, product_id]

    if start_date and end_date:
        query += " AND forecast_date BETWEEN %s AND %s"
        params += [start_date, end_date]

    query += " ORDER BY forecast_date ASC"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()

    # Top 10 SKUs (all stores)
    cur.execute("SELECT product_id, SUM(forecast_qty) as total_forecast FROM forecasts GROUP BY product_id ORDER BY total_forecast DESC LIMIT 10")
    top_skus = [{"product_id": r[0], "total_forecast": r[1]} for r in cur.fetchall()]

    # Critical SKUs (example: min forecast < 5)
    cur.execute("SELECT product_id, MIN(forecast_qty) FROM forecasts GROUP BY product_id HAVING MIN(forecast_qty)<5")
    critical_skus = [{"product_id": r[0], "min_qty": r[1]} for r in cur.fetchall()]

    cur.close()
    conn.close()

    if rows:
        latest = rows[-1]
        history = [{"date": r[0].isoformat(), "qty": r[1], "model": r[2]} for r in rows]
        quantities = [r[1] for r in rows]
        stats = {"avg": round(sum(quantities)/len(quantities),2), "max": max(quantities), "min": min(quantities)}
        return jsonify({
            "latest": {"forecast_qty": latest[1], "forecast_date": latest[0].isoformat(), "model": latest[2]},
            "history": history,
            "stats": stats,
            "top_skus": top_skus,
            "critical_skus": critical_skus
        })
    else:
        return jsonify({"error":"No forecast found"})

# CSV Export
@app.route('/export', methods=['POST'])
def export_csv():
    store_id = request.form.get('store_id')
    product_id = request.form.get('product_id')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT forecast_date, store_id, product_id, forecast_qty, model FROM forecasts WHERE store_id=%s AND product_id=%s ORDER BY forecast_date",
        (store_id, product_id)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['forecast_date','store_id','product_id','forecast_qty','model'])
    cw.writerows(rows)
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)

    filename = f"forecast_{store_id}_{product_id}.csv"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='text/csv')

if __name__ == "__main__":
    app.run(debug=True)
