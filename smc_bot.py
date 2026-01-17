# -----------------------------------------------------------------------------
# smc_bot_v5.0.py - (SMC Sniper v5.0: Instant FVG Entry)
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
    return "SMC Sniper Bot Service (v5.0 - Instant FVG Entry) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- (دالة جلب العملات تبقى كما هي) ---
def get_filtered_usdt_pairs(client, max_price=100.0, top_n_by_volume=150):
    try:
        all_tickers = client.get_ticker()
        usdt_pairs = [t for t in all_tickers if t['symbol'].endswith('USDT') and 'UP' not in t['symbol'] and 'DOWN' not in t['symbol']]
        cheap_pairs = [p for p in usdt_pairs if 'lastPrice' in p and float(p['lastPrice']) < max_price]
        sorted_pairs = sorted(cheap_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [p['symbol'] for p in sorted_pairs[:top_n_by_volume]]
    except Exception as e:
        logger.error(f"[Binance] فشل في جلب قائمة العملات المفلترة: {e}")
        return []

# --- دوال التحليل (SMC) - تم تعديلها ---
def find_fvg_in_discount(df):
    """
    يبحث عن فجوة سعرية (FVG) موجودة بالكامل داخل منطقة الخصم.
    """
    if len(df) < 52: return None
    
    # تحديد موجة آخر 50 شمعة
    wave_df = df.tail(50)
    wave_low, wave_high = wave_df['low'].min(), wave_df['high'].max()
    
    # تحديد منطقة الخصم (تحت 50% من الموجة)
    discount_zone_50_percent = wave_low + (wave_high - wave_low) * 0.5

    # البحث عن فجوة سعرية غير ممتلئة
    for i in range(len(df) - 3, 0, -1):
        prev_candle, current_candle, next_candle = df.iloc[i-1], df.iloc[i], df.iloc[i+1]
        
        # شرط وجود فجوة سعرية صاعدة
        if prev_candle['high'] < next_candle['low']:
            fvg_top = next_candle['low']
            fvg_bottom = prev_candle['high']

            # هل الفجوة موجودة في منطقة الخصم؟
            if fvg_top < discount_zone_50_percent:
                # هل تم ملء هذه الفجوة لاحقًا؟
                is_filled = any(df.iloc[j]['low'] <= fvg_bottom for j in range(i + 2, len(df)))
                if not is_filled:
                    return {"top": fvg_top, "bottom": fvg_bottom}
    return None

def check_bos(df):
    """
    يتحقق من وجود كسر للهيكل (BOS) في آخر شمعتين.
    """
    if len(df) < 52: return False
    relevant_df = df.iloc[:-2] # استبعاد آخر شمعتين للنظر في القمم السابقة
    last_50_high = relevant_df['high'].tail(50).max()
    
    # هل آخر شمعتين كسرتا أعلى قمة في الـ 50 شمعة السابقة؟
    if df.iloc[-1]['high'] > last_50_high or df.iloc[-2]['high'] > last_50_high:
        return True
    return False

def analyze_for_instant_entry(client, symbol):
    """
    يحلل العملة لإيجاد إشارة دخول فوري.
    """
    try:
        klines_1h = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=100)
        if len(klines_1h) < 100: return None
        
        df = pd.DataFrame(klines_1h, columns=['timestamp','open','high','low','close','volume','time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df[['high','low','close']] = df[['high','low','close']].apply(pd.to_numeric)
        
        current_price = df.iloc[-1]['close']

        # 1. هل هناك كسر للهيكل؟
        if not check_bos(df):
            return None
            
        # 2. هل هناك فجوة سعرية في منطقة الخصم؟
        fvg = find_fvg_in_discount(df)
        if not fvg:
            return None

        # 3. الشرط الأهم: هل السعر الحالي داخل هذه الفجوة؟
        if fvg['bottom'] <= current_price <= fvg['top']:
            # نعم! هذه إشارة دخول فوري.
            return {"entry_price": current_price, "fvg_bottom": fvg['bottom'], "fvg_top": fvg['top']}

    except Exception as e:
        logger.error(f"[SMC Instant] خطأ أثناء فحص {symbol}: {e}")
    
    return None

# --- مهمة الفحص الدوري (تم تبسيطها) ---
async def scan_for_instant_entry(context):
    client = context.job.data['binance_client']
    chat_id = context.job.data['chat_id']
    
    logger.info("--- [SMC Instant] بدء جولة الفحص (الدخول الفوري) ---")
    
    symbols_to_scan = get_filtered_usdt_pairs(client, max_price=100.0, top_n_by_volume=150)
    if not symbols_to_scan: return

    for symbol in symbols_to_scan:
        entry_signal = analyze_for_instant_entry(client, symbol)
        
        if entry_signal:
            price = entry_signal['entry_price']
            fvg_bottom = entry_signal['fvg_bottom']
            fvg_top = entry_signal['fvg_top']

            message = (
                f"🔥 *[SMC Instant] إشارة دخول فورية!* 🔥\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **سعر الدخول الحالي:** `{price}`\n\n"
                f"• **السبب:** السعر الآن داخل فجوة سعرية (`{fvg_bottom}` - `{fvg_top}`) تقع في منطقة الخصم بعد كسر الهيكل."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
            logger.info(f"--- [SMC Instant] تم إرسال إشارة دخول فوري لـ {symbol}. ---")
        
        await asyncio.sleep(2)

# --- أوامر البوت ودالة التشغيل الرئيسية ---
async def start(update, context):
    await update.message.reply_html("أهلاً بك! أنا **بوت SMC Sniper v5.0 (Instant Entry)**.\nأبحث عن لحظة دخول السعر إلى فجوة سعرية في منطقة الخصم وأرسل إشارة فورية.")

def run_bot():
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    BINANCE_API_KEY, BINANCE_SECRET_KEY = os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_SECRET_KEY")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    job_data = {'binance_client': client, 'chat_id': TELEGRAM_CHAT_ID}
    
    job_queue = application.job_queue
    # يمكننا جعل الفحص أسرع الآن، مثلاً كل 30 دقيقة، لأنه لا يعتمد على ذاكرة
    job_queue.run_repeating(scan_for_instant_entry, interval=30 * 60, first=10, data=job_data)
    
    logger.info("--- [SMC Instant Bot] البوت جاهز ويعمل. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [SMC Instant Bot] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [SMC Instant Bot] Web Server has been started. ---")
    run_bot()

