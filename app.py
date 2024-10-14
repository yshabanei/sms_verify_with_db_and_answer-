from flask import Flask, jsonify, request
import 
from decouple import config

app = Flask(__name__)

API_KEY = config("API_KEY")

@app.route('/v1/process', methods=['POST'])
def process():
    """This is a callback from KaveNegar. It will get sender and message, check if valid, and answer back."""
    data = request.form
    sender = data.get("from")
    message = data.get("message")
    
    if not sender or not message:
        return jsonify({"error": "Missing 'from' or 'message' in request."}), 400
    
    print(f"Received '{message}' from {sender}")
    send_sms(sender, 'Hi'+message)

    ret = {"message": "processed"}
    return jsonify(ret), 200

def send_sms(receptor, message):
    """This function will send an SMS using Kavenegar API."""
    url = f'https://api.kavenegar.com/v1/{API_KEY}/sms/send.json'
    data = {
        "message": message,
        "receptor": receptor
    }
    
    try:
        res = requests.post(url, data=data)
        res.raise_for_status()
        print(f"Message '{message}' sent to {receptor}. Status code: {res.status_code}")
    except requests.RequestException as e:
        print(f"Failed to send message: {e}")
        return False
    return True

def check_serial():
    # Your serial checking logic will go here
    pass

if __name__ == "__main__":
        app.run("0.0.0.0", 5000, debug=True)
