import re
import sqlite3
from flask import Flask, jsonify, request
import requests
from decouple import config
import pandas as pd
import logging

app = Flask(__name__)

API_KEY = config("API_KEY")
DATABASE_FILE_PATH = config("DATABASE_FILE_PATH")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


@app.route('/v1/ok')
def health_check():
    retr = {'message': 'ok'}
    return jsonify(retr), 200
    

@app.route("/v1/process", methods=["POST"])
def process():
    """This is a callback from KaveNegar. It will get sender and message, check if valid, and answer back."""
    data = request.form
    sender = data.get("from")
    message = normalize_string(data["message"])
    if not sender or not message:
        return jsonify({"error": "Missing 'from' or 'message' in request."}), 400

    logging.info(f"Received '{message}' from {sender}")
    send_sms(sender, f"Hi {message}")

    return jsonify({"message": "processed"}), 200


def send_sms(receptor, message):
    """This function will send an SMS using Kavenegar API."""
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


def normalize_string(input_str):
    from_char = "۱۲۳۴۵۶۷۸۹۰"
    to_char = "1234567890"

    for i in range(len(from_char)):
        input_str = input_str.replace(from_char[i], to_char[i])
    input_str = input_str.upper()
    input_str = re.sub(r'\W', '', input_str) #remove any non alphanumeric character
    return input_str


def insert_serials(cur, serials):
    """Inserts serial records into the database."""
    for index, row in serials.iterrows():
        try:
            cur.execute(
                "INSERT INTO serials (ref_number, description, start_serial, end_serial, date) VALUES (?, ?, ?, ?, ?)",
                (
                    row["Reference Number"],
                    row["Description"],
                    row["Start Serial"],
                    row["End Serial"],
                    row["Date"],
                ),
            )
            logging.info(
                f"Inserted Row {index}: Ref: {row['Reference Number']}, Desc: {row['Description']}, Start: {row['Start Serial']}, End: {row['End Serial']}, Date: {row['Date']}"
            )
        except Exception as e:
            logging.error(f"Failed to insert row {index}: {e}")


def import_database_from_excel(filepath):
    """Imports data from an Excel file."""
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
            logging.info("Finished importing lookup data.")
            df_failed = pd.read_excel(filepath, sheet_name=1, engine="openpyxl")
            logging.info("Importing failed serial numbers...")
            for index, row in df_failed.iterrows():
                start_serial = normalize_string(start_serial)
                end_serial = normalize_string(end_serial)
                failed_serial = row.get("Failed Serial")
                logging.info(f"Failed serial {index}: {failed_serial}")

    except FileNotFoundError:
        logging.error("Excel file not found.")
    except sqlite3.Error as e:
        logging.error(f"SQLite error: {e}")
    except Exception as e:
        logging.error(f"Error importing database from Excel: {e}")


def check_serial():
    pass


if __name__ == "__main__":
    import_database_from_excel("tmp/main.xlsx")
    app.run("0.0.0.0", 5000, debug=True)
