from flask import Flask, request, jsonify, send_file, session, render_template_string
import json
import os
import io
import hashlib
import hmac
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "super_secret_key"  # Change in production!

DATA_FILE = "expenses.json"
USER_FILE = "users.json"
SALT = "your_secret_salt"

# --- Helper Functions ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as file:
            return json.load(file)
    return {"budget": 0, "expenses": []}

def save_data(data):
    with open(DATA_FILE, "w") as file:
        json.dump(data, file)

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as file:
            return json.load(file)
    return {}

def save_users(users):
    with open(USER_FILE, "w") as file:
        json.dump(users, file)

def hash_password(password):
    """Hashes a password using SHA-256 with a salt."""
    return hashlib.sha256((password + SALT).encode()).hexdigest()

# --- Routes ---
@app.route("/")
def index():
    if "user" not in session:
        return render_template_string(open("templates/login.html").read())
    return render_template_string(open("templates/dashboard.html").read())

@app.route("/signup", methods=["POST"])
def signup():
    users = load_users()
    username = request.form["username"]
    password_hash = hash_password(request.form["password"])

    if username in users:
        return jsonify({"message": "User already exists!"})
    
    users[username] = password_hash
    save_users(users)
    return jsonify({"message": "Signup successful!"})

@app.route("/login", methods=["POST"])
def login():
    users = load_users()
    username = request.form["username"]
    password = request.form["password"]

    if username in users and hmac.compare_digest(users[username], hash_password(password)):
        session["user"] = username
        return jsonify({"success": True, "message": "Login successful!"})
    
    return jsonify({"success": False, "message": "Invalid credentials!"})

@app.route("/logout")
def logout():
    session.pop("user", None)
    return jsonify({"message": "Logged out successfully!"})

@app.route("/set_budget", methods=["POST"])
def set_budget():
    data = load_data()
    data["budget"] = float(request.form["budget"])
    save_data(data)
    return jsonify({"message": "Budget set successfully!"})

@app.route("/add_expense", methods=["POST"])
def add_expense():
    data = load_data()
    amount = float(request.form["amount"])
    expense = {"category": request.form["category"], "amount": amount, "description": request.form["description"]}
    data["expenses"].append(expense)
    save_data(data)
    return jsonify({"message": "Expense added!"})

@app.route("/remaining_budget")
def remaining_budget():
    data = load_data()
    total_expenses = sum(exp["amount"] for exp in data["expenses"])
    return jsonify({"remaining": data["budget"] - total_expenses})

@app.route("/expenses_data")
def expenses_data():
    data = load_data()
    category_totals = {}
    for expense in data["expenses"]:
        category_totals[expense["category"]] = category_totals.get(expense["category"], 0) + expense["amount"]
    
    return jsonify({"categories": list(category_totals.keys()), "amounts": list(category_totals.values())})

@app.route("/download_pdf")
def download_pdf():
    data = load_data()
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Budget Report")
    pdf.drawString(200, 750, "Budget Report")
    pdf.drawString(50, 720, f"Total Budget: ${data['budget']}")
    
    y = 700
    for expense in data["expenses"]:
        pdf.drawString(50, y, f"{expense['category']}: ${expense['amount']} ({expense['description']})")
        y -= 20

    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="Budget_Report.pdf")

if __name__ == "__main__":
    app.run(debug=True)