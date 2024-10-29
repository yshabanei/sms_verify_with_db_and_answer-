import logging
import os
import re
import time

import pandas as pd
import requests
from decouple import config
import MySQLdb
from flask import (
    Flask,
    jsonify,
    request,
    redirect,
    url_for,
    flash,
    session,
    render_template,
)
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

UPLOAD_FOLDER = config("UPLOAD_FOLDER")
ALLOWED_EXTENSIONS = config("ALLOWED_EXTENSIONS").split(",")
API_KEY = config("API_KEY")
SECRET_KEY = config("SECRET_KEY")
CALL_BACK_TOKEN = config("CALL_BACK_TOKEN")

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app)
csrf = CSRFProtect()
csrf.init_app(app)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config.update(SECRET_KEY=SECRET_KEY)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ایجاد تابع برای اتصال به دیتابیس
def get_db_connection():
    try:
        connection = MySQLdb.connect(
            host=config("MySQL_HOST"),
            user=config("MYSQL_USERNAME"),
            passwd=config("MYSQL_PASSWORD"),
            db=config("MYSQL_DB_NAME"),
        )
        return connection
    except MySQLdb.Error as e:
        logging.error(f"Database connection failed: {e}")
        return None


def close_db_connection(connection):
    if connection:
        connection.close()


class User(UserMixin):
    def __init__(self, id):
        self.id = id

    def __repr__(self):
        return "%d" % self.id


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    """صفحه اصلی برای آپلود فایل"""
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)

        file = request.files["file"]

        if file.filename == "":
            flash("No selected file")
            session["message"] = "No selected file"
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)
            rows, failures = import_database_from_excel(file_path)
            session["message"] = f"Imported {rows} rows and {failures} failures"
            os.remove(file_path)
            return redirect("/")

    message = session.get("message", "")
    session["message"] = ""

    return render_template("index.html", message=message)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
@csrf.exempt
def login():
    """صفحه ورود کاربر"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        expected_username = config("USERNAME")
        expected_password_hash = config("PASSWORD")

        if username == expected_username and check_password_hash(
            expected_password_hash, password
        ):
            user = User(id=1)
            login_user(user)
            flash("Login successful!")
            return redirect(request.args.get("next") or url_for("home"))
        else:
            flash("Invalid username or password.")
            return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/check_one_serial", methods=["POST"])
@login_required
def check_one_serial():
    serial_to_check = request.form["serial"]
    answer = check_serial(normalize_string(serial_to_check))
    flash(answer, "info")
    return redirect("/")


@app.route("/logout")
@login_required
def logout():
    """خروج از حساب کاربری و بازگشت به صفحه ورود"""
    logout_user()
    flash("Logged out")
    return redirect("/login")


@app.errorhandler(401)
def page_not_found(e):
    flash("Login problem", "error")
    return redirect("/login")


@login_manager.user_loader
def load_user(userid):
    return User(userid)


@app.route("/v1/ok")
def health_check():
    """بررسی سلامت سرور"""
    return jsonify({"message": "ok"}), 200


@app.route(f"/v1/{CALL_BACK_TOKEN}/process", methods=["POST"])
def process():
    """واسط بازخورد KaveNegar برای پردازش پیام‌ها"""
    data = request.form
    sender = data.get("from")
    message = normalize_string(data.get("message", ""))
    if not sender or not message:
        return jsonify({"error": "Missing 'from' or 'message' in request."}), 400
    answer = check_serial(message)
    db = get_db_connection()
    cur = db.cursor()
    date = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO PROCESSED_SMS(sender, message, answer, date) VALUES (%s, %s, %s,'%s')",
        (sender, message, answer, date),
    )
    db.commit()
    db.close()
    logging.info(f"Received '{message}' from {sender}")
    send_sms(sender, answer)
    return jsonify({"message": "processed"}), 200


def send_sms(receptor, message):
    """ارسال پیامک با API Kavenegar"""
    url = config("URL")
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


def normalize_string(input_str, fixed_size=30):
    """استانداردسازی رشته ورودی برای حذف کاراکترهای غیرالفبایی"""
    persian_numerals = "۱۲۳۴۵۶۷۸۹۰"
    arabic_numerals = "١٢٣٤٥٦٧٨٩٠"
    english_numerals = "1234567890"

    for persian_num, arabic_num, eng_num in zip(
        persian_numerals, arabic_numerals, english_numerals
    ):
        input_str = input_str.replace(persian_num, eng_num)
        input_str = input_str.replace(arabic_num, eng_num)

    input_str = re.sub(r"\W+", "", input_str.upper())

    all_alpha = "".join([c for c in input_str if c.isalpha()])
    all_digit = "".join([c for c in input_str if c.isdigit()])

    missing_zeros = fixed_size - len(all_alpha) - len(all_digit)
    normalized_str = all_alpha + "0" * missing_zeros + all_digit

    return normalized_str


def insert_serials(cur, serials):
    """ورود رکوردهای سریال به دیتابیس به‌صورت دسته‌ای"""
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
            "INSERT INTO serials (ref_number, description, start_serial, end_serial, date) VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
        logging.info(f"Inserted {len(rows)} serial records successfully.")
    except Exception as e:
        logging.error(f"Failed to insert serial records: {e}")


def import_database_from_excel(filepath):
    """وارد کردن داده‌ها از فایل اکسل به دیتابیس"""
    connection = get_db_connection()
    if not connection:
        return 0, 0

    try:
        cur = connection.cursor()
        cur.execute("DROP TABLE IF EXISTS serials")
        cur.execute(
            """CREATE TABLE IF NOT EXISTS serials (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    ref_number VARCHAR(100),
                    description VARCHAR(256),
                    start_serial CHAR(30),
                    end_serial CHAR(30),
                    date DATETIME
                );"""
        )
        connection.commit()
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
            return 0, 0

        insert_serials(cur, df)
        connection.commit()

        df_failed = pd.read_excel(filepath, sheet_name=1, engine="openpyxl")
        logging.info("Importing failed serial numbers...")

        failures = 0
        for index, row in df_failed.iterrows():
            failed_serial = normalize_string(row.get("Failed Serial", ""))
            logging.info(f"Failed serial {index}: {failed_serial}")
            failures += 1

        logging.info("Finished importing lookup data.")
        return len(df), failures
    except FileNotFoundError:
        logging.error("Excel file not found.")
        return 0, 0
    except MySQLdb.Error as e:
        logging.error(f"MySQL error: {e}")
        return 0, 0
    except Exception as e:
        logging.error(f"Error importing database from Excel: {e}")
        return 0, 0
    finally:
        close_db_connection(connection)


def check_serial(serial_number):
    """بررسی وجود شماره سریال در دیتابیس"""
    connection = get_db_connection()
    if not connection:
        return "Database connection issue. Please try again."

    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT description FROM serials WHERE start_serial <= %s AND end_serial >= %s",
                (serial_number, serial_number),
            )
            result = cur.fetchone()
        return (
            f"Serial number {serial_number} is valid: {result[0]}"
            if result
            else f"Serial number {serial_number} is invalid."
        )
    except MySQLdb.Error as e:
        logging.error(f"Database query failed: {e}")
        return "Database error. Please try again."
    finally:
        close_db_connection(connection)


if __name__ == "__main__":
    app.run()
