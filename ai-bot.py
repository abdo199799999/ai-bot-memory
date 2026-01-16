import os
import json
import requests
from flask import Flask, request

# إعدادات البيئة
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_FILE = "rules.json"

URL = f"https://api.telegram.org/bot{TOKEN}/"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"

app = Flask(__name__)

class PythonAI:
    def __init__(self):
        self.rules = {}
        self.load_rules()

    def load_rules(self):
        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3.raw"}
            response = requests.get(GITHUB_API, headers=headers)
            if response.status_code == 200:
                self.rules = response.json()
            else:
                # إذا لم يكن الملف موجودًا، نبدأ بقاموس فارغ
                self.rules = {}
        except Exception as e:
            print(f"Error loading rules: {e}")
            self.rules = {}

    def save_rules(self):
        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
            
            # أولاً، نحصل على SHA الحالي للملف لتجنب التعارضات
            get_resp = requests.get(GITHUB_API, headers=headers)
            sha = None
            if get_resp.status_code == 200:
                sha = get_resp.json().get("sha")

            # تجهيز البيانات الجديدة
            content_str = json.dumps(self.rules, ensure_ascii=False, indent=2)
            
            data = {
                "message": "Update rules via bot",
                "content": content_str,
                "committer": {
                    "name": "AI Bot",
                    "email": "bot@example.com"
                }
            }
            if sha:
                data["sha"] = sha

            # إرسال طلب التحديث
            put_resp = requests.put(GITHUB_API, headers=headers, json=data)
            if put_resp.status_code not in [200, 201]:
                 print(f"Failed to save rules: {put_resp.status_code} - {put_resp.text}")

        except Exception as e:
            print(f"Error saving rules: {e}")


    def generate(self, prompt):
        # الشرط المصحح: يجب أن يحتوي على "أضف" وعلامة "="
        if "أضف" in prompt and "=" in prompt:
            try:
                key, code = prompt.split("=", 1) # نستخدم split مرة واحدة فقط
                key = key.replace("أضف", "").strip()
                code = code.strip()
                
                if not key: # التأكد من أن المفتاح ليس فارغًا
                    return "⚠️ المفتاح لا يمكن أن يكون فارغًا."

                self.rules[key] = code
                self.save_rules()
                return f"✅ تمت إضافة القاعدة: {key}"
            except ValueError:
                return "⚠️ صيغة غير صحيحة. استخدم: أضف المفتاح = الكود"

        if prompt.strip() == "اعرض القواعد":
            self.load_rules() # تحديث القواعد قبل العرض
            if not self.rules:
                return "📂 لا توجد قواعد مخزنة بعد."
            # تحويل القواعد إلى نص منسق
            rules_text = "\n".join([f"🔑 *{k}*:\n`{v}`" for k, v in self.rules.items()])
            return f"📂 *القواعد المخزنة حاليًا:*\n\n{rules_text}"

        # البحث عن قاعدة موجودة
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
        # إرسال الرد مع تفعيل Markdown
        requests.post(URL + "sendMessage", json={"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"})
    return "ok"

def set_webhook():
    response = requests.get(f"{URL}setWebhook?url={WEBHOOK_URL}")
    print(f"Webhook setup response: {response.json()}")

if __name__ == "__main__":
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

