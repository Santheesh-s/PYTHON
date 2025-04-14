from flask import Flask, request, jsonify, send_file, session, render_template_string
import sqlite3
import os
import io
import hashlib
import hmac
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import time

app = Flask(__name__)
app.secret_key = "super_secret_key"  # Change in production!
SALT = "your_secret_salt"
app.config['PERMANENT_SESSION_LIFETIME'] = 60

@app.before_request
def before_request():
    session.permanent = True  # Set session to use permanent session lifetime
    if 'user' in session:
        # Update last activity timestamp
        session['last_activity'] = int(time.time())

def init_db():
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        # Create users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (username TEXT PRIMARY KEY, password TEXT)''')
        # Create expenses table
        c.execute('''CREATE TABLE IF NOT EXISTS expenses
                    (id INTEGER PRIMARY KEY, username TEXT,
                     category TEXT, amount REAL, description TEXT,
                     FOREIGN KEY (username) REFERENCES users(username))''')
        # Create budgets table
        c.execute('''CREATE TABLE IF NOT EXISTS budgets
                    (username TEXT PRIMARY KEY, amount REAL,
                     FOREIGN KEY (username) REFERENCES users(username))''')
        conn.commit()

# --- Helper Functions ---
def hash_password(password):
    return hashlib.sha256((password + SALT).encode()).hexdigest()

def get_user_budget(username):
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        c.execute('SELECT amount FROM budgets WHERE username = ?', (username,))
        result = c.fetchone()
        return result[0] if result else 0

def get_user_expenses(username):
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        c.execute('SELECT category, amount, description FROM expenses WHERE username = ?', (username,))
        return [{'category': row[0], 'amount': row[1], 'description': row[2]} for row in c.fetchall()]

def is_strong_password(password):
    """
    Validate password strength:
    - At least 8 characters long
    - Contains uppercase and lowercase letters
    - Contains at least one number
    - Contains at least one special character
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"

# --- Routes ---
@app.route("/")
def index():
    if "user" not in session:
        return render_template_string(open("login.html").read())
    return render_template_string(open("dashboard.html").read())

@app.route("/signup", methods=["POST"])
def signup():
    username = request.form["username"]
    password = request.form["password"]
    
    # Validate password
    is_valid, message = is_strong_password(password)
    if not is_valid:
        return jsonify({"success": False, "message": message})
    
    password_hash = hash_password(password)
    
    try:
        with sqlite3.connect('budget.db') as conn:
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                     (username, password_hash))
            conn.commit()
            return jsonify({"success": True, "message": "Signup successful!"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "User already exists!"})

@app.route("/check_password", methods=["POST"])
def check_password():
    password = request.form.get("password")
    is_valid, message = is_strong_password(password)
    return jsonify({"valid": is_valid, "message": message})

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]
    
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        c.execute('SELECT password FROM users WHERE username = ?', (username,))
        result = c.fetchone()
        
        if result and hmac.compare_digest(result[0], hash_password(password)):
            session["user"] = username
            return jsonify({"success": True, "message": "Login successful!"})
    
    return jsonify({"success": False, "message": "Invalid credentials!"})

@app.route("/logout")
def logout():
    session.pop("user", None)
    return jsonify({"message": "Logged out successfully!"})

@app.route("/set_budget", methods=["POST"])
def set_budget():
    if "user" not in session:
        return jsonify({"message": "Not logged in!"}), 401
        
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO budgets (username, amount) VALUES (?, ?)',
                 (session["user"], float(request.form["budget"])))
        conn.commit()
    return jsonify({"message": "Budget set successfully!"})

@app.route("/add_expense", methods=["POST"])
def add_expense():
    if "user" not in session:
        return jsonify({"message": "Not logged in!"}), 401
        
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        c.execute('INSERT INTO expenses (username, category, amount, description) VALUES (?, ?, ?, ?)',
                 (session["user"], request.form["category"], 
                  float(request.form["amount"]), request.form["description"]))
        conn.commit()
    return jsonify({"message": "Expense added!"})

@app.route("/remaining_budget")
def remaining_budget():
    if "user" not in session:
        return jsonify({"message": "Not logged in!"}), 401
        
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        budget = get_user_budget(session["user"])
        c.execute('SELECT SUM(amount) FROM expenses WHERE username = ?', (session["user"],))
        total_expenses = c.fetchone()[0] or 0
    return jsonify({"remaining": budget - total_expenses})

@app.route("/expenses_data")
def expenses_data():
    if "user" not in session:
        return jsonify({"message": "Not logged in!"}), 401
        
    with sqlite3.connect('budget.db') as conn:
        c = conn.cursor()
        c.execute('''SELECT category, SUM(amount) FROM expenses 
                    WHERE username = ? GROUP BY category''', (session["user"],))
        results = c.fetchall()
        categories = [row[0] for row in results]
        amounts = [row[1] for row in results]
    return jsonify({"categories": categories, "amounts": amounts})

@app.route("/download_pdf")
def download_pdf():
    if "user" not in session:
        return jsonify({"message": "Not logged in!"}), 401

    data = {"budget": get_user_budget(session["user"]), "expenses": get_user_expenses(session["user"])}
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
    init_db()
    app.run(debug=True)
