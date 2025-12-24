import os
import random
import hashlib
import time
import string
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from email.mime.text import MIMEText
import smtplib

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change_this_secret_for_prod")

# --- Email Setup ---
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_ADDRESS = "rajeshsv.182006@gmail.com"
EMAIL_PASSWORD = "favr jrox qxjh kkhu"

def send_email(to_email, subject, message):
    msg = MIMEText(message)
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)

# --- Database Config ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Rajesh@2607",
    "database": "banking_project",
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# --- Login Required Decorator ---
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Access denied.", "danger")
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapped
    return decorator

# --- Helper Functions ---
def generate_account_no():
    return ''.join(random.choices(string.digits, k=12))

# ---------------- Routes ---------------- #

@app.route("/")
def index():
    if session.get("user_id"):
        if session.get("role") == "admin":
            return redirect(url_for("admin_dashboard"))
        else:
            return redirect(url_for("user_dashboard"))
    return redirect(url_for("login"))

# ---------- Register ----------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        full_name = request.form.get("full_name","")
        email = request.form.get("email","")

        if not username or not password or not email or not full_name:
            flash("All fields are required.", "warning")
            return render_template("register.html")

        hashed = generate_password_hash(password)

        try:
            db = get_db()
            with db.cursor(buffered=True) as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password, role, full_name, email) VALUES (%s,%s,'user',%s,%s)",
                    (username, hashed, full_name, email)
                )
                db.commit()
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for("login"))
        except mysql.connector.Error as e:
            flash("Error: " + str(e), "danger")
        finally:
            db.close()

    return render_template("register.html")

# ---------- Login ----------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")

        try:
            db = get_db()
            with db.cursor(dictionary=True, buffered=True) as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
        finally:
            db.close()

        if user and check_password_hash(user.get("password",""), password):
            session["user_id"] = user.get("user_id")
            session["username"] = user.get("username")
            session["role"] = user.get("role")
            flash("Logged in successfully.", "success")
            return redirect(url_for("admin_dashboard") if user.get("role")=="admin" else url_for("user_dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")

# ---------- Logout ----------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

# ---------- User Dashboard ----------
@app.route("/dashboard")
@login_required()
def user_dashboard():
    account = None
    request_status = None  # For approved request needing initial deposit
    try:
        db = get_db()
        with db.cursor(dictionary=True, buffered=True) as cursor:
            # Fetch user's account
            cursor.execute("SELECT account_no, balance FROM accounts WHERE user_id=%s", (session["user_id"],))
            account = cursor.fetchone()

            # Check if there is an approved account request without an account yet
            if not account:
                cursor.execute("""
                    SELECT r.request_id, r.status, t.token
                    FROM account_requests r
                    LEFT JOIN initial_deposit_tokens t
                    ON r.request_id = t.request_id
                    WHERE r.user_id=%s AND r.status='approved'
                    LIMIT 1
                """, (session["user_id"],))
                request_status = cursor.fetchone()
    finally:
        db.close()

    return render_template("user_dashboard.html", account=account, request_status=request_status)

# ---------- Admin Dashboard ----------
@app.route("/admin")
@login_required(role="admin")
def admin_dashboard():
    users = []
    try:
        db = get_db()
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute("""
                SELECT u.user_id, u.username, u.full_name, a.account_no, COALESCE(a.balance,0) AS balance
                FROM users u
                LEFT JOIN accounts a ON u.user_id = a.user_id
                WHERE u.role='user'
                ORDER BY u.user_id
            """)
            users = cursor.fetchall()
    finally:
        db.close()
    return render_template("admin_dashboard.html", users=users)

# ---------- Admin Account Requests ----------
@app.route("/admin/account_requests")
@login_required(role="admin")
def admin_account_requests():
    requests = []
    try:
        db = get_db()
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute("""
                SELECT r.*, u.username, u.full_name, u.email
                FROM account_requests r
                JOIN users u ON r.user_id = u.user_id
                WHERE r.status='pending'
                ORDER BY r.request_date DESC
            """)
            requests = cursor.fetchall()
    finally:
        db.close()
    return render_template("admin_account_requests.html", requests=requests)

@app.route("/admin/account_requests/<int:request_id>/<action>")
@login_required(role="admin")
def handle_account_request(request_id, action):
    try:
        db = get_db()
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute("SELECT r.*, u.username, u.email, u.full_name FROM account_requests r JOIN users u ON r.user_id = u.user_id WHERE r.request_id = %s", (request_id,))
            req = cursor.fetchone()
            if not req:
                flash("Request not found.", "danger")
                return redirect(url_for("admin_account_requests"))

            if action == "approve":
                cursor.execute("UPDATE account_requests SET status='approved' WHERE request_id=%s", (request_id,))
                db.commit()
                flash(f"Account request approved for {req.get('username','User')}.", "success")

                # Generate token link for initial deposit
                token = hashlib.sha256(f"{req['user_id']}-{request_id}-{time.time()}".encode()).hexdigest()
                deposit_link = f"http://127.0.0.1:8383/initiate_account/{request_id}/{token}"

                cursor.execute("INSERT INTO initial_deposit_tokens (token, user_id, request_id) VALUES (%s,%s,%s)",
                               (token, req['user_id'], request_id))
                db.commit()

                subject = "Activate Your Account with Initial Deposit"
                message = f"""
Dear {req.get('full_name','User')},

Your account request has been approved. Click the link below to deposit ₹1000 and activate your account:

{deposit_link}

- YourBank Team
"""
                send_email(req['email'], subject, message)
            elif action == "reject":
                cursor.execute("UPDATE account_requests SET status='rejected' WHERE request_id=%s", (request_id,))
                db.commit()
                flash(f"Account request rejected for {req.get('username','User')}.", "info")
            else:
                flash("Invalid action.", "danger")
    finally:
        db.close()
    return redirect(url_for("admin_account_requests"))

# ---------- Initial Deposit for New Account ----------
@app.route("/initiate_account/<int:request_id>/<token>", methods=["GET","POST"])
@login_required()
def initiate_account(request_id, token):
    if request.method == "POST":
        try:
            db = get_db()
            with db.cursor(dictionary=True, buffered=True) as cursor:
                # Validate token
                cursor.execute(
                    "SELECT * FROM initial_deposit_tokens WHERE token=%s AND request_id=%s",
                    (token, request_id)
                )
                record = cursor.fetchone()
                if not record:
                    flash("Invalid or expired link.", "danger")
                    return redirect(url_for("user_dashboard"))

                # Check if account already exists
                cursor.execute("SELECT * FROM accounts WHERE user_id=%s", (record['user_id'],))
                if cursor.fetchone():
                    flash("Account already created.", "info")
                    return redirect(url_for("user_dashboard"))

                # Deposit amount from user input
                amount = float(request.form.get("amount", 0))
                if amount < 1000:
                    flash("You must deposit at least ₹1000 to activate your account.", "warning")
                    return redirect(request.url)

                # Create account with balance = amount
                account_no = generate_account_no()
                cursor.execute(
                    "INSERT INTO accounts (account_no, user_id, balance) VALUES (%s,%s,%s)",
                    (account_no, record['user_id'], amount)
                )

                # Record transaction
                cursor.execute(
                    "INSERT INTO transactions (account_no, amount, trans_type, remarks) VALUES (%s,%s,'deposit','Initial deposit')",
                    (account_no, amount)
                )

                # Delete token
                cursor.execute("DELETE FROM initial_deposit_tokens WHERE token=%s", (token,))

                db.commit()
                flash(f"Account created successfully with ₹{amount:.2f} balance.", "success")
        finally:
            db.close()

        return redirect(url_for("user_dashboard"))

    # GET request → show deposit page
    return render_template("initial_deposit.html", request_id=request_id, token=token)

# ---------- Request New Account ----------
@app.route("/request_account", methods=["GET","POST"])
@login_required()
def request_account():
    try:
        db = get_db()
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute("SELECT * FROM accounts WHERE user_id=%s", (session["user_id"],))
            if cursor.fetchone():
                flash("You already have an account.", "info")
                return redirect(url_for("user_dashboard"))

            cursor.execute("SELECT * FROM account_requests WHERE user_id=%s AND status='pending'", (session["user_id"],))
            if cursor.fetchone():
                flash("Your account request is already pending.", "info")
                return redirect(url_for("user_dashboard"))

            if request.method=="POST":
                full_name = request.form.get("full_name","")
                email = request.form.get("email","")
                cursor.execute("INSERT INTO account_requests (user_id, full_name, email) VALUES (%s,%s,%s)",
                               (session["user_id"], full_name, email))
                db.commit()
                flash("Your account request has been sent to the admin.", "success")
                return redirect(url_for("user_dashboard"))
    finally:
        db.close()
    return render_template("request_account.html")

# ---------- Deposit ----------
@app.route("/deposit", methods=["POST"])
@login_required()
def deposit():
    amount = float(request.form.get("amount",0))
    remarks = request.form.get("remarks","deposit")
    if amount <= 0:
        flash("Amount must be positive", "warning")
        return redirect(url_for("user_dashboard"))

    try:
        db = get_db()
        with db.cursor(buffered=True) as cursor:
            cursor.execute("SELECT account_no FROM accounts WHERE user_id=%s", (session["user_id"],))
            acct = cursor.fetchone()
            if not acct:
                flash("Account not found", "danger")
                return redirect(url_for("user_dashboard"))
            account_no = acct[0]
            cursor.execute("UPDATE accounts SET balance=balance+%s WHERE account_no=%s", (amount, account_no))
            cursor.execute("INSERT INTO transactions (account_no, amount, trans_type, remarks) VALUES (%s,%s,'deposit',%s)",
                           (account_no, amount, remarks))
            db.commit()
            flash(f"Deposited ₹{amount:.2f}", "success")
    finally:
        db.close()
    return redirect(url_for("user_dashboard"))

# ---------- Withdraw ----------
@app.route("/withdraw", methods=["POST"])
@login_required()
def withdraw():
    amount = float(request.form.get("amount",0))
    remarks = request.form.get("remarks","withdraw")
    if amount <= 0:
        flash("Amount must be positive", "warning")
        return redirect(url_for("user_dashboard"))
    try:
        db = get_db()
        with db.cursor(buffered=True) as cursor:
            cursor.execute("SELECT account_no, balance FROM accounts WHERE user_id=%s", (session["user_id"],))
            acct = cursor.fetchone()
            if not acct:
                flash("Account not found", "danger")
                return redirect(url_for("user_dashboard"))
            account_no, balance = acct
            if float(balance) - amount < 500:
                flash("Cannot withdraw. Minimum balance ₹500 required.", "warning")
                return redirect(url_for("user_dashboard"))
            cursor.execute("UPDATE accounts SET balance=balance-%s WHERE account_no=%s", (amount, account_no))
            cursor.execute("INSERT INTO transactions (account_no, amount, trans_type, remarks) VALUES (%s,%s,'withdraw',%s)",
                           (account_no, amount, remarks))
            db.commit()
            flash(f"Withdrew ₹{amount:.2f}", "success")
    finally:
        db.close()
    return redirect(url_for("user_dashboard"))

# ---------- Transfer ----------
@app.route("/transfer", methods=["GET","POST"])
@login_required()
def transfer():
    if request.method=="POST":
        to_account = request.form.get("to_account","").strip()
        amount = float(request.form.get("amount",0))
        remarks = request.form.get("remarks","transfer")
        if amount <= 0:
            flash("Amount must be positive", "warning")
            return redirect(url_for("transfer"))
        try:
            db = get_db()
            with db.cursor(buffered=True) as cursor:
                cursor.execute("SELECT account_no, balance FROM accounts WHERE user_id=%s", (session["user_id"],))
                from_acct = cursor.fetchone()
                if not from_acct:
                    flash("Your account not found", "danger")
                    return redirect(url_for("transfer"))
                from_account_no, from_balance = from_acct
                cursor.execute("SELECT account_no FROM accounts WHERE account_no=%s", (to_account,))
                if not cursor.fetchone():
                    flash("Destination account not found", "warning")
                    return redirect(url_for("transfer"))
                if float(from_balance) - amount < 500:
                    flash("Cannot transfer. Minimum balance ₹500 required.", "warning")
                    return redirect(url_for("transfer"))
                cursor.execute("UPDATE accounts SET balance=balance-%s WHERE account_no=%s", (amount, from_account_no))
                cursor.execute("UPDATE accounts SET balance=balance+%s WHERE account_no=%s", (amount, to_account))
                cursor.execute("INSERT INTO transactions (account_no, amount, trans_type, remarks) VALUES (%s,%s,'transfer',%s)",
                               (from_account_no, amount, f"to {to_account} | {remarks}"))
                cursor.execute("INSERT INTO transactions (account_no, amount, trans_type, remarks) VALUES (%s,%s,'transfer',%s)",
                               (to_account, amount, f"from {from_account_no} | {remarks}"))
                db.commit()
                flash(f"Transferred ₹{amount:.2f} to {to_account}", "success")
        finally:
            db.close()
        return redirect(url_for("user_dashboard"))
    return render_template("transfer.html")

# ---------- View Transactions ----------
@app.route("/transactions")
@login_required()
def transactions():
    txs = []
    try:
        db = get_db()
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute("""
                SELECT t.*
                FROM transactions t
                JOIN accounts a ON t.account_no = a.account_no
                WHERE a.user_id = %s
                ORDER BY t.trans_date DESC
            """, (session["user_id"],))
            txs = cursor.fetchall()
    finally:
        db.close()
    return render_template("transactions.html", transactions=txs)

# ---------- Run ----------
if __name__=="__main__":
    app.run(debug=True, port=8383)
