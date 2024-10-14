from flask import Flask
from flask.globals import app_ctx

app = Flask(__name__)


@app.route("/")
def main_page():
    return "Hello"


@app.route("/v1/process")
def process():
    pass


def send_sms():
    pass


def check_serial():
    pass


if __name__ == "__main__":
    app.run("0.0.0.0", 5000)
