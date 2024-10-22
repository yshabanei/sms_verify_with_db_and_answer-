import logging
import sqlite3

import pandas as pd
import requests
from decouple import config
from flask import Flask, jsonify, request, Response, redirect, url_for, abort
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user

app = Flask(__name__)

# Configuration
API_KEY = config("API_KEY")
DATABASE_FILE_PATH = config("DATABASE_FILE_PATH")
SECRET_KEY = config("SECRET_KEY")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

app.config.update(SECRET_KEY=SECRET_KEY)


class User(UserMixin):
    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "%d" % self.id


# Example user database
users = {1: User(1)}  # Example user with id=1


@app.route("/")
@login_required
def home():
    return Response("Hello World!")


# login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if password == config("PASSWORD") and username == config("USERNAME"):
            user = users.get(1)  # Simulate a user lookup
            login_user(user)
            return redirect(
                request.args.get("next") or url_for("home")
            )  # Safe redirect
        else:
            return abort(401)
    else:
        return Response(
            """
        <form action="" method="post">
            <p><input type="text" name="username" required>
            <p><input type="password" name="password" required>
            <p><input type="submit" value="Login">
        </form>
        """
        )


# logout route
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return Response("<p>Logged out</p>")


# handle login failure
@app.errorhandler(401)
def page_not_found(error):
    return Response("<p>Login failed</p>")


# callback to reload user object
@login_manager.user_loader
def load_user(userid):
    return users.get(int(userid))


@app.route("/v1/ok")
def health_check():
    retr = {"message": "ok"}
    return jsonify(retr), 200


@app.route("/v1/process", methods=["POST"])
def process():
    """Callback from KaveNegar. It gets sender and message, checks if valid, and replies."""
    data = request.form
    sender = data.get("from")
    message = normalize_string(data.get("message", ""))

    if not sender or not message:
        return jsonify({"error": "Missing 'from' or 'message' in request."}), 400

    answer = check_serial(message)
    logging.info(f"Received '{message}' from {sender}")
    send_sms(sender, answer)

    return jsonify({"message": "processed"}), 200


def send_sms(receptor, message):
    """Send an SMS using Kavenegar API."""
    url = f"https://api.kavenegar.com/v1/{API_KEY}/sms/send.json"
    data = {"message": message, "receptor": receptor}

    try:
        res = requests.post(url, data=data)
        res.raise_for_status()
        logging.info(
            f"Message '{message}' sent to {receptor}. Status code: {res.status_code}"
        )
    except requests.RequestException as e:
        logging.error(f"Failed to send message: {e}")
        return False
    return True


import re


def normalize_string(input_str, fixed_size=30):
    """Normalize the input string by replacing Persian and Arabic numbers and removing non-alphanumeric characters."""

    persian_numerals = "۱۲۳۴۵۶۷۸۹۰"
    arabic_numerals = "١٢٣٤٥٦٧٨٩٠"
    english_numerals = "1234567890"

    # Replace Persian and Arabic numerals with English numerals
    for persian_num, arabic_num, eng_num in zip(
        persian_numerals, arabic_numerals, english_numerals
    ):
        input_str = input_str.replace(persian_num, eng_num)
        input_str = input_str.replace(arabic_num, eng_num)

    # Convert to uppercase and remove non-alphanumeric characters
    input_str = re.sub(r"\W+", "", input_str.upper())

    all_alpha = "".join([c for c in input_str if c.isalpha()])
    all_digit = "".join([c for c in input_str if c.isdigit()])

    # Pad with zeros to the fixed size
    missing_zeros = fixed_size - len(all_alpha) - len(all_digit)
    normalized_str = all_alpha + "0" * missing_zeros + all_digit

    return normalized_str


def insert_serials(cur, serials):
    """Insert serial records into the database using bulk insert."""
    try:
        rows = [
            (
                row["Reference Number"],
                row["Description"],
                normalize_string(row["Start Serial"]),
                normalize_string(row["End Serial"]),
                row["Date"],
            )
            for _, row in serials.iterrows()
        ]
        cur.executemany(
            "INSERT INTO serials (ref_number, description, start_serial, end_serial, date) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        logging.info(f"Inserted {len(rows)} serial records successfully.")
    except Exception as e:
        logging.error(f"Failed to insert serial records: {e}")


def import_database_from_excel(filepath):
    """Import data from an Excel file into the SQLite database."""
    try:
        with sqlite3.connect(DATABASE_FILE_PATH) as conn:
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS serials")
            cur.execute(
                """CREATE TABLE IF NOT EXISTS serials (
                    id INTEGER PRIMARY KEY,
                    ref_number TEXT,
                    description TEXT,
                    start_serial TEXT,
                    end_serial TEXT,
                    date DATE
                );"""
            )
            conn.commit()

            # Import the first sheet (serials)
            df = pd.read_excel(filepath, sheet_name=0, engine="openpyxl")
            logging.info("Importing lookup data...")

            required_columns = [
                "Reference Number",
                "Description",
                "Start Serial",
                "End Serial",
                "Date",
            ]
            if not all(col in df.columns for col in required_columns):
                logging.error(
                    f"Missing required columns in the Excel sheet: {required_columns}"
                )
                return

            insert_serials(cur, df)
            conn.commit()

            # Import the second sheet (failed serials)
            df_failed = pd.read_excel(filepath, sheet_name=1, engine="openpyxl")
            logging.info("Importing failed serial numbers...")

            for index, row in df_failed.iterrows():
                failed_serial = normalize_string(row.get("Failed Serial", ""))
                logging.info(f"Failed serial {index}: {failed_serial}")

            logging.info("Finished importing lookup data.")
    except FileNotFoundError:
        logging.error("Excel file not found.")
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {e}")
    except Exception as e:
        logging.error(f"Error importing database from Excel: {e}")


def check_serial(serial_number):
    """Check if the serial number exists in the database and return an appropriate response."""
    try:
        with sqlite3.connect(DATABASE_FILE_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM serials WHERE start_serial <= ? AND end_serial >= ?",
                (serial_number, serial_number),
            )
            result = cur.fetchone()
            cur.execute(
                "SELECT * FROM invalids WHERE invalid_serial = ?", (serial_number,)
            )
            invalid_result = cur.fetchone()

            if invalid_result:
                return "This serial is among the failed ones."
            elif result:
                return f"Serial number {serial_number} is valid and belongs to {result[1]}."
            else:
                return f"Serial number {serial_number} is not valid."
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {e}")
        return "Database error occurred."


if __name__ == "__main__":
    # Ensure the database file path and secret key are set properly
    if not API_KEY or not DATABASE_FILE_PATH or not SECRET_KEY:
        logging.error("Missing required configuration. Check .env file.")
        exit(1)
    import_database_from_excel("../tmp/main.xlsx")
    app.run("0.0.0.0", 5000, debug=True)