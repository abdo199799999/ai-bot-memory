# -----------------------------------------------------------------------------
# smc_bot_v3.py - (SMC Sniper v3.0: Professional Grade)
# -----------------------------------------------------------------------------

import os
import logging
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from binance.client import Client
import pandas as pd

# --- الإعدادات الأساسية ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- خادم الويب ---
@app.route('/')
def health_check():
    return "SMC Sniper Bot Service (v3.0) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- دوال التحليل (SMC) ---

def find_fvg(df):
    """البحث عن آخر فجوة سعرية صاعدة (Bullish FVG) غير مملوءة."""
    for i in range(len(df) - 3, 0, -1): # البحث من النهاية للبداية
        prev_candle = df.iloc[i-1]
        next_candle = df.iloc[i+1]
        
        # هل هناك فجوة صاعدة؟
        if prev_candle['high'] < next_candle['low']:
            # هل تم ملء هذه الفجوة؟ (هل هبط السعر تحتها؟)
            # نتحقق من كل الشموع التي تلت تكون الفجوة
            is_filled = False
            for j in range(i + 2, len(df)):
                if df.iloc[j]['low'] <= prev_candle['high']:
                    is_filled = True
                    break
            
            if not is_filled:
                return {
                    "type": "Bullish",
                    "top": next_candle['low'],
                    "bottom": prev_candle['high'],
                    "time": next_candle['time']
                }
    return None

def find_bos(df):
    """البحث عن آخر كسر هيكل صاعد (Bullish BOS)."""
    # نحدد أعلى قمة في آخر 50 شمعة (باستثناء آخر شمعتين)
    relevant_df = df.iloc[:-2]
    if len(relevant_df) < 50: return None
    
    last_50_high = relevant_df['high'].tail(50).max()
    
    # هل الشمعة الأخيرة أو قبل الأخيرة كسرت هذه القمة؟
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    
    if last_candle['high'] > last_50_high or prev_candle['high'] > last_50_high:
        return {
            "type": "Bullish",
            "price": last_50_high,
            "time": last_candle['time']
        }
    return None

def analyze_symbol_smc(client, symbol):
    """العقل الرئيسي: يدمج كل المفاهيم لاتخاذ القرار."""
    try:
        klines_1h = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=100)
        if len(klines_1h) < 100: return None

        df = pd.DataFrame(klines_1h, columns=['timestamp','open','high','low','close','volume','time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df[['high','low','close']] = df[['high','low','close']].apply(pd.to_numeric)
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        # --- تطبيق منطق التحليل ---
        
        # 1. هل حدث كسر هيكل (BOS) مؤخرًا؟
        bos = find_bos(df)
        if not bos:
            return None # إذا لم يحدث كسر، لا توجد فرصة

        # 2. إذا حدث كسر، ابحث عن أقرب فجوة سعرية (FVG) تحته
        fvg = find_fvg(df)
        if not fvg:
            return None # إذا لم توجد فجوة، لا توجد فرصة

        # 3. هل الفجوة في منطقة الخصم (Discount)؟
        # نحدد الموجة الصاعدة الأخيرة (من أدنى قاع إلى أعلى قمة في آخر 50 شمعة)
        wave_low = df['low'].tail(50).min()
        wave_high = df['high'].tail(50).max()
        discount_zone_50_percent = wave_low + (wave_high - wave_low) * 0.5

        # يجب أن يكون قاع الفجوة تحت مستوى 50%
        if fvg['bottom'] < discount_zone_50_percent:
            # --- وجدنا فرصة محتملة! ---
            return {
                "bos": bos,
                "fvg": fvg,
                "current_price": df.iloc[-1]['close']
            }

    except Exception as e:
        logger.error(f"[SMC] خطأ أثناء فحص {symbol}: {e}")
    return None

# --- مهمة الفحص الدوري ---
async def scan_for_smc_setup(context):
    logger.info("--- [SMC Sniper] بدء جولة البحث عن فرص احترافية ---")
    client = context.job.data['binance_client']
    chat_id = context.job.data['chat_id']
    
    # سنقوم بفحص عملة واحدة فقط كمثال (BTCUSDT)
    symbol_to_check = "BTCUSDT" 
    
    opportunity = analyze_symbol_smc(client, symbol_to_check)
    
    if opportunity:
        bos = opportunity['bos']
        fvg = opportunity['fvg']
        price = opportunity['current_price']
        
        message = (
            f"🎯 *[SMC Sniper]* فرصة شراء احترافية محتملة!\n\n"
            f"• **العملة:** `{symbol_to_check}`\n"
            f"• **السعر الحالي:** `{price}`\n\n"
            f"• **التحليل:**\n"
            f"  1- تم كسر الهيكل عند سعر `{bos['price']}`.\n"
            f"  2- توجد فجوة سعرية (FVG) في منطقة الخصم.\n"
            f"  3- منطقة الدخول المحتملة: بين `{fvg['bottom']}` و `{fvg['top']}`.\n\n"
            f"راقب السعر عند وصوله لمنطقة الفجوة للدخول."
        )
        await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
    else:
        logger.info(f"--- [SMC Sniper] لا توجد فرص واضحة في {symbol_to_check} حاليًا ---")

# --- أوامر البوت ---
async def start(update, context):
    await update.message.reply_html("أهلاً بك! أنا **بوت SMC Sniper v3.0**.\nأبحث عن فرص الشراء الاحترافية بناءً على كسر الهيكل والفجوات السعرية.")

# --- دالة التشغيل الرئيسية ---
def run_bot():
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
    BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    job_data = {'binance_client': client, 'chat_id': TELEGRAM_CHAT_ID}
    
    job_queue = application.job_queue
    job_queue.run_repeating(scan_for_smc_setup, interval=60 * 60, first=10, data=job_data) # يفحص كل ساعة
    
    logger.info("--- [SMC Bot] البوت جاهز ويعمل. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [SMC Bot] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [SMC Bot] Web Server has been started. ---")
    run_bot()

