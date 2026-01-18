# -----------------------------------------------------------------------------
# smc_bot_v6.0.py - (SMC Sniper v6.0: Crossover Hunter)
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
import pandas_ta as ta # <-- استيراد المكتبة الجديدة

# --- الإعدادات الأساسية ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

# --- خادم الويب ---
@app.route('/')
def health_check():
    return "SMC Sniper Bot Service (v6.0 - Crossover Hunter) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- دوال جلب العملات والتحليل ---
def get_filtered_usdt_pairs(client, max_price=100.0, top_n_by_volume=150):
    try:
        all_tickers = client.get_ticker()
        usdt_pairs = [t for t in all_tickers if t['symbol'].endswith('USDT') and 'UP' not in t['symbol'] and 'DOWN' not in t['symbol']]
        cheap_pairs = [p for p in usdt_pairs if 'lastPrice' in p and float(p['lastPrice']) < max_price]
        sorted_pairs = sorted(cheap_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        return [p['symbol'] for p in sorted_pairs[:top_n_by_volume]]
    except Exception as e:
        logger.error(f"[Binance] فشل في جلب قائمة العملات: {e}")
        return []

def analyze_crossover_strategy(client, symbol):
    """
    يحلل العملة بناءً على استراتيجية تقاطع الماكد مع تأكيد RSI.
    """
    try:
        # جلب بيانات كافية لحساب المؤشرات بشكل صحيح (200 شمعة)
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=200)
        if len(klines) < 200: return None
        
        df = pd.DataFrame(klines, columns=['timestamp','open','high','low','close','volume','time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df['close'] = pd.to_numeric(df['close'])

        # --- حساب المؤشرات باستخدام pandas-ta ---
        # إعدادات الماكد القياسية (12, 26, 9)
        df.ta.macd(close='close', fast=12, slow=26, signal=9, append=True)
        # إعدادات RSI القياسية (14)
        df.ta.rsi(close='close', length=14, append=True)

        # --- تطبيق شروط الاستراتيجية على آخر شمعتين ---
        # نحن ننظر إلى آخر شمعتين ([-2] للشمعة قبل الأخيرة, [-1] للشمعة الأخيرة)
        # هذا يسمح لنا باكتشاف التقاطع لحظة حدوثه
        
        # الشمعة قبل الأخيرة
        prev_macd = df['MACD_12_26_9'].iloc[-2]
        prev_signal = df['MACDs_12_26_9'].iloc[-2]
        
        # الشمعة الأخيرة (الحالية)
        curr_macd = df['MACD_12_26_9'].iloc[-1]
        curr_signal = df['MACDs_12_26_9'].iloc[-1]
        curr_rsi = df['RSI_14'].iloc[-1]
        
        # الشرط 1: هل حدث تقاطع إيجابي في الشمعة الأخيرة؟
        # (كان الماكد تحت خط الإشارة، والآن أصبح فوقه)
        crossover_happened = (prev_macd < prev_signal) and (curr_macd > curr_signal)
        
        # الشرط 2: هل التقاطع حدث تحت خط الصفر؟
        # (كلا خطي الماكد والإشارة تحت الصفر)
        below_zero = (curr_macd < 0) and (curr_signal < 0)
        
        # الشرط 3: هل مؤشر القوة النسبية يؤكد الزخم؟
        # (اخترق مستوى 50 أو فوقه)
        rsi_confirms = curr_rsi > 50

        # --- اتخاذ القرار ---
        if crossover_happened and below_zero and rsi_confirms:
            current_price = df['close'].iloc[-1]
            logger.info(f"!!! إشارة محتملة في {symbol} !!! تقاطع ماكد تحت الصفر مع RSI > 50.")
            return {"price": current_price, "rsi": curr_rsi, "macd": curr_macd}

    except Exception as e:
        logger.error(f"[Crossover] خطأ أثناء فحص {symbol}: {e}")
    
    return None

# --- مهمة الفحص الدوري ---
async def scan_for_crossovers(context):
    client = context.job.data['binance_client']
    chat_id = context.job.data['chat_id']
    
    logger.info("--- [Crossover Hunter] بدء جولة الفحص (كل ساعة) ---")
    symbols_to_scan = get_filtered_usdt_pairs(client)
    if not symbols_to_scan: return

    for symbol in symbols_to_scan:
        signal = analyze_crossover_strategy(client, symbol)
        
        if signal:
            price = signal['price']
            rsi = signal['rsi']
            
            message = (
                f"🎯 *[Crossover Hunter]* إشارة دخول مبكرة محتملة!\n\n"
                f"• **العملة:** `{symbol}`\n"
                f"• **السعر الحالي:** `{price}`\n\n"
                f"• **السبب (تأكيد الفرضية):**\n"
                f"  1- حدث تقاطع إيجابي للماكد **تحت خط الصفر**.\n"
                f"  2- مؤشر RSI يؤكد الزخم (حالياً: `{rsi:.2f}`).\n\n"
                f"هذه قد تكون بداية حركة صاعدة قوية."
            )
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
            logger.info(f"--- [Crossover Hunter] تم إرسال إشارة لـ {symbol}. ---")
        
        await asyncio.sleep(2) # لإعطاء وقت لواجهة Binance API

# --- أوامر البوت ودالة التشغيل ---
async def start(update, context):
    await update.message.reply_html("أهلاً بك! أنا **بوت Crossover Hunter v6.0**.\nأبحث عن تقاطعات الماكد الإيجابية تحت خط الصفر مع تأكيد من مؤشر RSI على إطار الساعة.")

def run_bot():
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    BINANCE_API_KEY, BINANCE_SECRET_KEY = os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_SECRET_KEY")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    job_data = {'binance_client': client, 'chat_id': TELEGRAM_CHAT_ID}
    
    job_queue = application.job_queue
    # الفحص كل ساعة مناسب جدًا لهذه الاستراتيجية
    job_queue.run_repeating(scan_for_crossovers, interval=60 * 60, first=10, data=job_data)
    
    logger.info("--- [Crossover Hunter v6.0] البوت جاهز ويعمل. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [Crossover Hunter v6.0] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [Crossover Hunter v6.0] Web Server has been started. ---")
    run_bot()

