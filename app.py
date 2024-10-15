import sqlite3
from flask import Flask, jsonify, request
import requests
from decouple import config
import pandas as pd
import logging

app = Flask(__name__)

API_KEY = config("API_KEY")

# Configure logging
logging.basicConfig(level=logging.INFO)

@app.route("/v1/process", methods=["POST"])
def process():
    """This is a callback from KaveNegar. It will get sender and message, check if valid, and answer back."""
    data = request.form
    sender = data.get("from")
    message = data.get("message")

    if not sender or not message:
        return jsonify({"error": "Missing 'from' or 'message' in request."}), 400

    logging.info(f"Received '{message}' from {sender}")
    send_sms(sender, f"Hi {message}")

    ret = {"message": "processed"}
    return jsonify(ret), 200

def send_sms(receptor, message):
    """This function will send an SMS using Kavenegar API."""
    url = f"https://api.kavenegar.com/v1/{API_KEY}/sms/send.json"
    data = {"message": message, "receptor": receptor}

    try:
        res = requests.post(url, data=data)
        res.raise_for_status()
        logging.info(f"Message '{message}' sent to {receptor}. Status code: {res.status_code}")
    except requests.RequestException as e:
        logging.error(f"Failed to send message: {e}")
        return False
    return True

def import_database_from_excel(filepath):
    """Imports data from an Excel file. The first sheet contains lookup data,
    and the second sheet contains a list of failed serial numbers."""
    database = config("DATABASE_FILE_PATH")
    
    required_columns = ["Reference Number", "Description", "Start Serial", "End Serial", "Date"]
    
    try:
        with sqlite3.connect(database) as conn:
            cur = conn.cursor()
            cur.execute('DROP TABLE IF EXISTS serials')
            cur.execute("""CREATE TABLE IF NOT EXISTS serials (
                id INTEGER PRIMARY KEY,
                ref_number TEXT,
                description TEXT,
                start_serial TEXT,
                end_serial TEXT,
                date DATE
            );""")

            # Import lookup data
            df = pd.read_excel(filepath, sheet_name=0, engine="openpyxl")
            logging.info("Importing lookup data...")
            
            if not all(col in df.columns for col in required_columns):
                logging.error(f"Missing required columns in the Excel sheet: {required_columns}")
                return
            
            serials_counter = 0
            for index, row in df.iterrows():
                try:
                    ref_number = row["Reference Number"]
                    description = row["Description"]
                    start_serial = row["Start Serial"]
                    end_serial = row["End Serial"]
                    date = row["Date"]
                    cur.execute("INSERT INTO serials (ref_number, description, start_serial, end_serial, date) VALUES (?, ?, ?, ?, ?)",
                                (ref_number, description, start_serial, end_serial, date))
                    serials_counter += 1
                    logging.info(f"Inserted Row {index}: Ref: {ref_number}, Desc: {description}, Start: {start_serial}, End: {end_serial}, Date: {date}")

                    if serials_counter % 10 == 0:
                        conn.commit()
                except Exception as e:
                    logging.error(f"Failed to insert row {index}: {e}")

            conn.commit()  # Final commit after all inserts
            logging.info("Finished importing lookup data.")

            # Handle the second sheet for failed serial numbers
            df_failed = pd.read_excel(filepath, sheet_name=1, engine="openpyxl")
            logging.info("Importing failed serial numbers...")
            for index, row in df_failed.iterrows():
                failed_serial = row.get("Failed Serial")
                logging.info(f"Failed serial {index}: {failed_serial}")

    except sqlite3.Error as e:
        logging.error(f"SQLite error: {e}")
    except Exception as e:
        logging.error(f"Error importing database from Excel: {e}")

if __name__ == "__main__":
    import_database_from_excel("tmp/main.xlsx")
    app.run("0.0.0.0", 5000, debug=True)
