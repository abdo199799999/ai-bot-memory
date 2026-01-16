import os
import json
import requests
from flask import Flask, request

# إعدادات البيئة
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # مثال: "username/falcon_bot_rules"
GITHUB_FILE = "rules.json"

URL = f"https://api.telegram.org/bot{TOKEN}/"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"

app = Flask(__name__)

class PythonAI:
    def __init__(self):
        self.rules = {}
        self.load_rules()

    def load_rules(self):
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        response = requests.get(GITHUB_API, headers=headers)
        if response.status_code == 200:
            content = response.json()["content"]
            decoded = json.loads(requests.utils.unquote(content.encode()).decode("utf-8"))
            self.rules = json.loads(decoded)
        else:
            self.rules = {}

    def save_rules(self):
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        get_resp = requests.get(GITHUB_API, headers=headers)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None
        encoded = json.dumps(self.rules, ensure_ascii=False, indent=2)
        data = {
            "message": "update rules",
            "content": encoded.encode("utf-8").decode("utf-8"),
        }
        if sha:
            data["sha"] = sha
        requests.put(GITHUB_API, headers=headers, json=data)

    def generate(self, prompt):
        if "أضف" in prompt and "=" in prompt:
            try:
                key, code = prompt.split("=")
                key, code = key.replace("أضف", "").strip(), code.strip()
                self.rules[key] = code
                self.save_rules()
                return f"✅ تمت إضافة القاعدة: {key}"
            except:
                return "⚠️ صيغة غير صحيحة. استخدم: أضف المفتاح = الكود"

        if "اعرض القواعد" in prompt:
            if not self.rules:
                return "📂 لا توجد قواعد مخزنة بعد."
            return "📂 القواعد المخزنة:\n" + "\n".join([f"- {k}" for k in self.rules.keys()])

        for key in self.rules:
            if key in prompt:
                return self.rules[key]

        return "# لم أتعلم هذه القاعدة بعد"

ai = PythonAI()

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        reply = ai.generate(text)
        requests.post(URL + "sendMessage", json={"chat_id": chat_id, "text": reply})
    return "ok"

def set_webhook():
    requests.get(f"{URL}setWebhook?url={WEBHOOK_URL}")

if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=10000)
