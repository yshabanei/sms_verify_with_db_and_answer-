SMS Verification System with Flask and Database
This project implements an SMS verification system using Flask as the web framework and a database to store verification details. Users can register with their phone numbers, receive a verification code via SMS, and verify their account.

Features
User Registration: Users register with their phone numbers.
SMS Verification: A code is sent to the user's phone for verification.
Database Integration: Stores user details and verification status.
Flask Framework: Python-based web application framework for handling requests.
SMS Gateway API: Integrates with a third-party service (like Twilio) to send SMS.
Verification Check: Verifies the user's code and updates the database upon success.
Requirements
Python 3.x
Flask
SQLAlchemy (or any preferred ORM)
Twilio (or any SMS API service)
SQLite (or any other database of choice)
Python Packages
Install required dependencies with pip:

bash
Copy code
pip install Flask SQLAlchemy Twilio
Project Structure
bash
Copy code
.
├── app.py                # Main Flask application
├── models.py             # Database models
├── services.py           # SMS verification logic
├── config.py             # Configuration (Twilio, database credentials, etc.)
├── README.md             # This file
├── requirements.txt      # List of dependencies
└── templates/
    └── verification.html # Verification page template
Setup and Installation
Clone the repository:
bash
Copy code
git clone  https://github.com/yshabanei/sms_verify_with_db_and_answer.git
cd sms-verification-flask
Install dependencies:
bash
Copy code
pip install -r requirements.txt
Set up environment variables for your SMS API (Twilio, for example):
bash
Copy code
export TWILIO_ACCOUNT_SID='your_account_sid'
export TWILIO_AUTH_TOKEN='your_auth_token'
export TWILIO_PHONE_NUMBER='+1234567890'
Set up the database:
bash
Copy code
python
>>> from app import db
>>> db.create_all()
Run the application:
bash
Copy code
python app.py
Open the app in your browser at http://localhost:5000.
How it Works
User Registration: The user enters their phone number in a registration form.
Send SMS: Upon submission, a verification code is generated and sent to the user's phone number using the Twilio API.
Code Verification: The user enters the code in a verification form, and the system checks if the code matches the one stored in the database.
Success: If the code matches, the user is marked as verified.
Database Model
In the models.py, we define a User model for storing the phone number and verification status.

python
Copy code
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(15), unique=True, nullable=False)
    verification_code = db.Column(db.String(6), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
SMS Logic
In services.py, we define a function to send the verification code using Twilio's API.

python
Copy code
from twilio.rest import Client
import random

def send_verification_code(phone_number):
    client = Client(account_sid, auth_token)
    verification_code = str(random.randint(100000, 999999))
    
    message = client.messages.create(
        body=f"Your verification code is {verification_code}",
        from_=twilio_phone_number,
        to=phone_number
    )

    return verification_code
Routes
/register: User submits phone number for registration.
/verify: User submits verification code for account verification.
Example from app.py:

python
Copy code
from flask import Flask, request, render_template, redirect
from models import db, User
from services import send_verification_code

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sms_verification.db'
db.init_app(app)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        phone_number = request.form['phone']
        verification_code = send_verification_code(phone_number)
        user = User(phone_number=phone_number, verification_code=verification_code)
        db.session.add(user)
        db.session.commit()
        return redirect('/verify')
    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        phone_number = request.form['phone']
        code = request.form['code']
        user = User.query.filter_by(phone_number=phone_number).first()
        if user and user.verification_code == code:
            user.is_verified = True
            db.session.commit()
            return "Verified Successfully!"
        return "Verification Failed."
    return render_template('verification.html')
License
This project is licensed under the MIT License.
