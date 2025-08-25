from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import sqlite3
import os
from datetime import datetime 
import json
from collections import defaultdict



app = Flask(__name__)
app.secret_key = "clave_super_secreta"

DB_NAME = "finanzas.db"
USERS_FILE = "usuarios.txt"

# Crear base de datos si no existe
def create_db():
    if not os.path.exists(DB_NAME):
        conn = sqlite3.connect(DB_NAME)
        conn.close()

create_db()

def create_tables():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            category TEXT,
            type TEXT NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

create_tables()

def check_credentials(username, password):
    if not os.path.exists(USERS_FILE):
        return False
    with open(USERS_FILE, "r") as f:
        for line in f.readlines():
            stored_user, stored_pass = line.strip().split(":")
            if stored_user == username and stored_pass == password:
                return True
    return False

@app.route("/home")
def home():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT amount, type, category FROM transactions WHERE username=?", (username,))
    rows = cursor.fetchall()
    conn.close()

    balance = 0
    ingresos = 0
    egresos_por_categoria = defaultdict(float)

    for amount, ttype, category in rows:
        if ttype == "Ingreso":
            balance += amount
            ingresos += amount
        else:
            balance -= amount
            egresos_por_categoria[category] += amount

    # Pasamos datos al template
    return render_template("home.html",
                           username=username,
                           balance=balance,
                           ingresos=ingresos,
                           egresos=json.dumps(egresos_por_categoria))

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if check_credentials(username, password):
            session["username"] = username
            return redirect(url_for("dashboard"))
        else:
            flash("Usuario o contraseña incorrectos", "error")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with open(USERS_FILE, "a") as f:
            f.write(f"{username}:{password}\n")

        flash("Usuario registrado correctamente", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]

    if request.method == "POST":
        amount = request.form["amount"]
        description = request.form["description"]
        category = request.form["category"]
        transaction_type = request.form["transaction_type"]  # <- nombre correcto
        date = request.form["date"]

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO transactions (username, amount, description, category, type, date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, amount, description, category, transaction_type, date))
        conn.commit()
        conn.close()
        flash("Transacción guardada!", "success")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions WHERE username=? ORDER BY date DESC", (username,))
    transactions = cursor.fetchall()
    conn.close()

    balance = 0.0
    for t in transactions:
        balance += t[2] if t[5] == "Ingreso" else -t[2]

    # 👇 pasamos la fecha de hoy al template
    default_date = datetime.now().strftime("%Y-%m-%d")
    return render_template("dashboard.html",
                           username=username,
                           transactions=transactions,
                           balance=balance,
                           default_date=default_date)


@app.route("/delete/<int:trans_id>")
def delete_transaction(trans_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id=?", (trans_id,))
    conn.commit()
    conn.close()
    flash("Transacción eliminada", "info")
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

from flask import send_file
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

@app.route("/exportar")
def exportar():
    if "username" not in session:
        flash("Debes iniciar sesión para exportar tus transacciones", "error")
        return redirect(url_for("login"))

    username = session["username"]

    # Obtener transacciones del usuario
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT date, type, category, description, amount
        FROM transactions
        WHERE username=?
        ORDER BY date DESC
    """, (username,))
    transactions = cursor.fetchall()
    conn.close()

    # Usar BytesIO para generar PDF en memoria
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica", 12)

    # Título
    c.drawString(50, 750, f"Reporte de transacciones - Usuario: {username}")
    c.drawString(50, 735, f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, 720, "-" * 80)

    y = 700
    balance = 0.0

    # Encabezado
    c.drawString(50, y, "Fecha")
    c.drawString(120, y, "Tipo")
    c.drawString(190, y, "Categoría")
    c.drawString(300, y, "Descripción")
    c.drawString(500, y, "Monto")
    y -= 20

    for date, ttype, category, description, amount in transactions:
        if y < 50:  # Salto de página
            c.showPage()
            c.setFont("Helvetica", 12)
            y = 750

        c.drawString(50, y, date)
        c.drawString(120, y, ttype)
        c.drawString(190, y, category)
        c.drawString(300, y, description[:30])  # Truncar descripción larga
        c.drawRightString(570, y, f"${amount:,.2f}")
        y -= 20

        if ttype == "Ingreso":
            balance += amount
        else:
            balance -= amount

    # Línea final
    y -= 10
    c.drawString(50, y, "-" * 80)
    y -= 20
    c.drawString(50, y, f"Balance total: ${balance:,.2f}")

    c.save()

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="transacciones.pdf", mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True)
