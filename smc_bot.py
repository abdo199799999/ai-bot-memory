# -----------------------------------------------------------------------------
# smc_bot_v4.1.py - (SMC Sniper v4.1: Transparent Status)
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

# --- ذاكرة البوت للفرص المراقبة ---
watched_opportunities = []

# --- خادم الويب ---
@app.route('/')
def health_check():
    return "SMC Sniper Bot Service (v4.1 - Transparent Status) is Running!", 200
def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- (دوال التحليل وجلب العملات تبقى كما هي تمامًا) ---
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

def find_fvg(df):
    for i in range(len(df) - 3, 0, -1):
        prev_candle, next_candle = df.iloc[i-1], df.iloc[i+1]
        if prev_candle['high'] < next_candle['low']:
            is_filled = any(df.iloc[j]['low'] <= prev_candle['high'] for j in range(i + 2, len(df)))
            if not is_filled:
                return {"type": "Bullish", "top": next_candle['low'], "bottom": prev_candle['high'], "time": next_candle['time']}
    return None

def find_bos(df):
    if len(df) < 52: return None
    relevant_df = df.iloc[:-2]
    last_50_high = relevant_df['high'].tail(50).max()
    last_candle, prev_candle = df.iloc[-1], df.iloc[-2]
    if last_candle['high'] > last_50_high or prev_candle['high'] > last_50_high:
        return {"type": "Bullish", "price": last_50_high, "time": last_candle['time']}
    return None

def analyze_symbol_smc(client, symbol):
    try:
        klines_1h = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1HOUR, limit=100)
        if len(klines_1h) < 100: return None
        df = pd.DataFrame(klines_1h, columns=['timestamp','open','high','low','close','volume','time','quote_av','trades','tb_base_av','tb_quote_av','ignore'])
        df[['high','low','close']] = df[['high','low','close']].apply(pd.to_numeric)
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        
        bos = find_bos(df)
        if not bos: return None
        
        fvg = find_fvg(df)
        if not fvg: return None
        
        wave_low, wave_high = df['low'].tail(50).min(), df['high'].tail(50).max()
        discount_zone_50_percent = wave_low + (wave_high - wave_low) * 0.5
        
        if fvg['bottom'] < discount_zone_50_percent:
            return {"bos": bos, "fvg": fvg, "current_price": df.iloc[-1]['close']}
    except Exception as e:
        logger.error(f"[SMC] خطأ أثناء فحص {symbol}: {e}")
    return None

# --- (مهمة الفحص الرئيسية ومهمة المراقبة السريعة تبقى كما هي) ---
async def scan_for_smc_setup(context):
    global watched_opportunities
    client = context.job.data['binance_client']
    chat_id = context.job.data['chat_id']
    logger.info("--- [SMC Sniper] بدء جولة الفحص الرئيسية (كل ساعة) ---")
    symbols_to_scan = get_filtered_usdt_pairs(client, max_price=100.0, top_n_by_volume=150)
    if not symbols_to_scan: return
    for symbol in symbols_to_scan:
        if any(opp['symbol'] == symbol for opp in watched_opportunities): continue
        opportunity = analyze_symbol_smc(client, symbol)
        if opportunity:
            bos, fvg, price = opportunity['bos'], opportunity['fvg'], opportunity['current_price']
            message = (f"🎯 *[SMC Sniper]* فرصة شراء احترافية محتملة!\n\n"
                       f"• **العملة:** `{symbol}`\n"
                       f"• **السعر الحالي:** `{price}`\n\n"
                       f"• **التحليل:**\n"
                       f"  1- تم كسر الهيكل عند سعر `{bos['price']}`.\n"
                       f"  2- توجد فجوة سعرية (FVG) في منطقة الخصم.\n"
                       f"  3- منطقة الدخول المحتملة: بين `{fvg['bottom']}` و `{fvg['top']}`.\n\n"
                       f"سأقوم بمراقبة هذه المنطقة وسأرسل تنبيهًا عند دخول السعر إليها.")
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
            watched_opportunities.append({"symbol": symbol, "fvg_top": fvg['top'], "fvg_bottom": fvg['bottom']})
            logger.info(f"--- [SMC Sniper] تم العثور على فرصة في {symbol} وإضافتها للمراقبة. ---")
        await asyncio.sleep(2)

async def quick_check_watched(context):
    global watched_opportunities
    client = context.job.data['binance_client']
    chat_id = context.job.data['chat_id']
    if not watched_opportunities: return
    logger.info(f"--- [Watcher] بدء جولة المراقبة السريعة لـ {len(watched_opportunities)} فرصة. ---")
    for opp in list(watched_opportunities):
        try:
            ticker = client.get_symbol_ticker(symbol=opp['symbol'])
            current_price = float(ticker['price'])
            if opp['fvg_bottom'] <= current_price <= opp['fvg_top']:
                message = (f"🔥 *[Watcher] تنبيه دخول!* 🔥\n\n"
                           f"• **العملة:** `{opp['symbol']}`\n"
                           f"• **السعر الآن (`{current_price}`) داخل منطقة الدخول التي حددناها!**\n"
                           f"• **المنطقة:** بين `{opp['fvg_bottom']}` و `{opp['fvg_top']}`.\n\n"
                           f"هذه قد تكون لحظة الدخول المناسبة.")
                await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                watched_opportunities.remove(opp)
                logger.info(f"--- [Watcher] تم إرسال تنبيه دخول لـ {opp['symbol']} وإزالتها من المراقبة. ---")
        except Exception as e:
            logger.error(f"[Watcher] خطأ أثناء مراقبة {opp['symbol']}: {e}")
        await asyncio.sleep(1)

# --- أوامر البوت (تمت إضافة أمر /status هنا) ---
async def start(update, context):
    await update.message.reply_html("أهلاً بك! أنا **بوت SMC Sniper v4.1 (Transparent Status)**.\nأبحث عن فرص ثم أراقبها وأرسل تنبيهًا عند لحظة الدخول.\n\nاستخدم /status لمعرفة العملات التي أراقبها حاليًا.")

async def status(update, context):
    """يرسل قائمة بالعملات المراقبة حاليًا."""
    global watched_opportunities
    if not watched_opportunities:
        await update.message.reply_text("✅ لا توجد عملات تحت المراقبة حاليًا.")
        return

    message = "--- *العملات تحت المراقبة* ---\n\n"
    for opp in watched_opportunities:
        message += (f"• **العملة:** `{opp['symbol']}`\n"
                    f"  - **منطقة الدخول:** بين `{opp['fvg_bottom']}` و `{opp['fvg_top']}`\n\n")
    
    await update.message.reply_text(message, parse_mode='Markdown')

# --- دالة تشغيل البوت (تم تعديلها لتسجيل الأمر الجديد) ---
def run_bot():
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    BINANCE_API_KEY, BINANCE_SECRET_KEY = os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_SECRET_KEY")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # تسجيل الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status)) # <-- السطر الجديد
    
    client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)
    job_data = {'binance_client': client, 'chat_id': TELEGRAM_CHAT_ID}
    
    job_queue = application.job_queue
    job_queue.run_repeating(scan_for_smc_setup, interval=60 * 60, first=10, data=job_data)
    job_queue.run_repeating(quick_check_watched, interval=5 * 60, first=20, data=job_data)
    
    logger.info("--- [SMC Bot] البوت جاهز ويعمل بكلتا المهمتين والأوامر. ---")
    application.run_polling()

if __name__ == "__main__":
    logger.info("--- [SMC Bot] Starting Main Application ---")
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    logger.info("--- [SMC Bot] Web Server has been started. ---")
    run_bot()

