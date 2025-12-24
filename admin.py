# save as create_admin.py and run: python create_admin.py
import mysql.connector
from werkzeug.security import generate_password_hash

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Rajesh@2607",   # your mysql password
    "database": "banking_Project",
}

username = "Rajesh"
password = "admin123"   # choose a secure password
hashed = generate_password_hash(password)
con = mysql.connector.connect(**DB_CONFIG)
cur = con.cursor()
cur.execute("INSERT INTO users (username, password, role, full_name) VALUES (%s,%s,'admin',%s)",
            (username, hashed, "Administrator"))
con.commit()
print("Admin created.")
cur.close()
con.close()
