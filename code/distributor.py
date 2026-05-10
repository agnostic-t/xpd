from flask import Flask
import argparse

app = Flask(__file__)

BIND_IP   = "127.0.0.1"
BIND_PORT = 9005
SERVER_PORT = 9000

script = """
set -e
git clone https://github.com/agnostic-t/xpd.git
cd xpy-msg
python -m venv venv
source ./venv/bin/activate
pip install -r ./requirements
cd code

echo 'Now you can run:'
echo 'python ./client.py -i $IP -p $PORT ./runtime/database'
"""[1:-1]

@app.route("/")
async def index():
    return script.replace("$IP", BIND_IP).replace("$PORT", f"{SERVER_PORT}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distribution helper")
    parser.add_argument("-i", "--ip", help="IP to bind", required=True)
    parser.add_argument("-p", "--port", help="Port to bind", required=True)
    parser.add_argument("-s", "--sport", help="Port where server is", required=True)

    args = parser.parse_args()

    BIND_IP = args.ip
    BIND_PORT = args.port
    SERVER_PORT = args.sport

    app.run(BIND_IP, port=BIND_PORT, debug=False)
