import asyncio
import schedule
import time
import json
import os 

from datetime import datetime,timedelta
from typing import Optional
from telegram.ext import Application, ContextTypes
from config import api, PRICE_SYMBOLS, PRICE_ALERTS, ALERT_COUNTER, TELEGRAM_CHAT_ID

# 功能


HISTORY_FILE = "net_worth_history.json"

def load_history():
    """加载历史净资产记录"""
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_history(history):
    """保存历史记录"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def add_today_net_worth(net_usd: float):
    """添加今天的净资产记录（只记录一次/天）"""
    history = load_history()
    today = datetime.now().strftime('%Y-%m-%d')
    
    if history.get(today) is None:  # 今天还没记录
        history[today] = round(net_usd, 2)
        save_history(history)

def get_recent_history(days=7):
    """获取最近days天的历史记录，用于显示趋势"""
    history = load_history()
    dates = sorted(history.keys(), reverse=True)[:days]
    dates.reverse()  # 从旧到新
    
    data = []
    for date in dates:
        data.append({"date": date, "value": history[date]})
    
    return data
# price alert
async def check_price_alerts(app: Application):
    global PRICE_ALERTS
    if not PRICE_ALERTS:
        return

    triggered = []
    for alert_id, alert in list(PRICE_ALERTS.items()):
        if alert.get('triggered'):
            continue

        inst_id = PRICE_SYMBOLS.get(alert['coin'].upper())
        if not inst_id:
            continue

        try:
            resp = api.marketdata.get_ticker(instId=inst_id)
            if resp.get('code') == '0' and resp.get('data'):
                current_price = float(resp['data'][0]['last'])

                should_trigger = False
                if alert['direction'] == 'above' and current_price >= alert['price']:
                    should_trigger = True
                elif alert['direction'] == 'below' and current_price <= alert['price']:
                    should_trigger = True

                if should_trigger:
                    coin = inst_id.split('-')[0].upper()
                    msg = f"🚨 价格警报触发！\n{coin} 已{ '上涨突破' if alert['direction']=='above' else '下跌跌破' } {alert['price']}\n当前价格：${current_price:.2f}"
                    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
                    PRICE_ALERTS[alert_id]['triggered'] = True
                    triggered.append(alert_id)
        except:
            pass

    # 可选：清除已触发的警报（或保留历史）
    for aid in triggered:
        del PRICE_ALERTS[aid]

# 获取加密货币价格
async def get_crypto_price(inst_id: str) -> str:
    try:
        resp = api.marketdata.get_ticker(instId=inst_id)

        if resp.get('code') != '0' or not resp.get('data'):
            return f"获取 {inst_id} 价格失败：{resp.get('msg', '未知错误')}"

        data = resp['data'][0]

        last = float(data['last'])                    # 最新价
        open24h = float(data['open24h'])              # 24小时开盘价
        high24h = float(data['high24h'])               # 24小时最高
        low24h = float(data['low24h'])                # 24小时最低

        # 计算24小时涨跌幅
        change_24h = (last - open24h) / open24h * 100

        coin = inst_id.split('-')[0].upper()

        message = f"**{coin} 实时行情**\n\n"
        message += f"当前价格：**${last:.2f}**\n"
        message += f"24h 涨跌：**{change_24h:+.2f}%**\n"
        message += f"24h 最高：${high24h:.2f}\n"
        message += f"24h 最低：${low24h:.2f}\n"
        message += f"24h 开盘：${open24h:.2f}"

        return message

    except Exception as e:
        return f"查询价格异常: {str(e)}"

# 处理 /price 命令
async def price_command(update, context: ContextTypes.DEFAULT_TYPE):
    # 获取用户输入
    if context.args:
        user_input = ' '.join(context.args).lower()
    else:
        user_input = update.message.text.strip().lower()

    # 提取币种关键词
    coin = None
    for key in PRICE_SYMBOLS.keys():
        if key in user_input:
            coin = key
            break

    if not coin:
        await update.message.reply_text(
            "请指定币种：btc、eth、sol（支持大小写）\n"
            "用法：\n"
            "/price btc\n"
            "或直接发送：btc"
        )
        return

    inst_id = PRICE_SYMBOLS[coin]

    # 发送"查询中..."提示
    waiting_msg = await update.message.reply_text("🕐 正在获取最新价格...")

    price_text = await get_crypto_price(inst_id)

    # 编辑为最终结果（支持 Markdown）
    await waiting_msg.edit_text(price_text, parse_mode='Markdown')

# 处理直接发送币种消息
async def handle_coin_message(update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if text in [k.lower() for k in PRICE_SYMBOLS.keys()]:
        context.args = [text]
        await price_command(update, context)

def safe_float(value, default=0.0):
    if value is None or value == '' or value == 'null':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def fmt_amt(x: float, precision: int = 2) -> str:
    """Format amounts: show <0.01 for tiny values, thousands sep for large."""
    if x is None:
        x = 0.0
    if abs(x) < 0.01 and x != 0:
        return "<0.01"
    return f"{x:,.{precision}f}"

async def get_balance_info() -> str:
    try:
        # 1. 资金账户（充提）
        funding_resp = api.funding.get_balances()

        # 2. 交易账户（现货/杠杆）
        trading_resp = api.account.get_balance()

        # 3. 灵活借贷完整信息
        loan_resp = api.flexible_loan.get_loan_info()

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message_lines = []
        message_lines.append(f"=== 每日余额报告  {now} ===\n")

        # 用于计算总净资产的变量
        funding_usd = 0.0
        trading_eq_usd = 0.0
        flexible_net_usd = 0.0

        # ========= 资金账户 =========
        message_lines.append("资金账户（充提账户）:")
        found = False
        for bal in funding_resp.get('data', []):
            ccy = bal.get('ccy', '?')
            total = safe_float(bal.get('bal'))
            avail = safe_float(bal.get('availBal'))
            amt = max(total, avail)  # 取较大值作为持仓参考

            if amt > 0.01:
                found = True
                message_lines.append(f"  • {ccy}: 总 {fmt_amt(total)}  / 可用 {fmt_amt(avail)}")

                # 计算美元价值
                if ccy in ['USDT', 'USDC']:
                    funding_usd += amt
                else:
                    inst_id = f"{ccy}-USDT"
                    try:
                        ticker = api.marketdata.get_ticker(instId=inst_id)
                        if ticker.get('code') == '0' and ticker.get('data'):
                            price = safe_float(ticker['data'][0]['last'])
                            funding_usd += amt * price
                    except:
                        pass  # 无交易对或查询失败，跳过

        if not found:
            message_lines.append("  • 无显著余额")

        # ========= 交易账户 =========
        message_lines.append("\n交易账户（现货/杠杆）:")
        found = False
        for item in trading_resp.get('data', []):
            for bal in item.get('details', []):
                ccy = bal.get('ccy', '?')
                cash = safe_float(bal.get('cashBal'))
                avail = safe_float(bal.get('availBal'))
                eq = safe_float(bal.get('eq'))
                liab = safe_float(bal.get('liab'))
                interest = safe_float(bal.get('interest'))

                if abs(cash) > 0.01 or avail > 0.01 or eq > 0.01 or liab > 0.01 or interest > 0.01:
                    found = True
                    borrow = ""
                    if liab > 0.01 or interest > 0.01:
                        borrow = f"  | 借币 {fmt_amt(liab)} 利息 {fmt_amt(interest)}"
                    message_lines.append(
                        f"  • {ccy}: 现金 {fmt_amt(cash)}  / 可用 {fmt_amt(avail)}  / 权益 {fmt_amt(eq)}{borrow}"
                    )

                    # 交易账户权益直接是USD计价
                    if eq > 0.01:
                        trading_eq_usd += eq

        if not found:
            message_lines.append("  • 无显著余额或负债")

        # ========= 灵活借贷 =========
        message_lines.append("\n灵活借贷（Flexible Loan）:")
        if loan_resp.get('code') != '0' or not loan_resp.get('data'):
            message_lines.append("  • 获取失败或无借贷记录")
        else:
            data = loan_resp['data'][0]

            # 已借币种
            loan_lines = []
            for loan in data.get('loanData', []):
                amt = safe_float(loan.get('amt'))
                if amt > 0.01:
                    loan_lines.append(f"{loan.get('ccy','?')}: {fmt_amt(amt)}")
            if loan_lines:
                message_lines.append("  • 已借:")
                for l in loan_lines:
                    message_lines.append(f"    - {l}")
            else:
                message_lines.append("  • 已借: 无")

            # 抵押物
            col_lines = []
            for col in data.get('collateralData', []):
                amt = safe_float(col.get('amt'))
                if amt > 0.01:
                    col_lines.append(f"{col.get('ccy','?')}: {fmt_amt(amt)}")
            message_lines.append("  • 抵押物:")
            if col_lines:
                for c in col_lines:
                    message_lines.append(f"    - {c}")
            else:
                message_lines.append("    - 无抵押物")

            # 总体指标
            collateral_usd = safe_float(data.get('collateralNotionalUsd'))
            loan_usd = safe_float(data.get('loanNotionalUsd'))
            cur_ltv = safe_float(data.get('curLTV')) * 100
            mcall = safe_float(data.get('marginCallLTV')) * 100
            liq = safe_float(data.get('liqLTV')) * 100

            message_lines.append("")
            message_lines.append(f"  抵押物总价值: ${fmt_amt(collateral_usd, 2)}  | 已借总额: ${fmt_amt(loan_usd, 2)}")
            message_lines.append(f"  当前 LTV: {fmt_amt(cur_ltv, 2)}%  (预警 {fmt_amt(mcall, 2)}% | 清算 {fmt_amt(liq, 2)}%)")

            # 灵活借贷净价值
            flexible_net_usd = collateral_usd - loan_usd

        # ========= 总净资产汇总 =========
        total_net_usd = funding_usd + trading_eq_usd + flexible_net_usd
        add_today_net_worth(total_net_usd)

        # ========= 最近7天净资产趋势 =========
        recent = get_recent_history(7)
        if len(recent) >= 2:
            message_lines.append("\n📈 最近7天净资产变化:")
            values = [item['value'] for item in recent]
            dates_short = [item['date'][5:] for item in recent]  # 显示 mm-dd

            # 简单文本折线图
            max_val = max(values)
            min_val = min(values)
            range_val = max_val - min_val if max_val > min_val else 1
            bars = []
            for v in values:
                ratio = (v - min_val) / range_val
                bar_len = int(ratio * 20)  # 20格宽度
                bars.append("█" * bar_len)

            for i, item in enumerate(recent):
                change = ""
                if i > 0:
                    diff = item['value'] - recent[i-1]['value']
                    change = f" ({diff:+.2f})"
                message_lines.append(f"  {dates_short[i]}: ${fmt_amt(item['value'], 2)} {bars[i]} {change}")

            # 总变化
            total_change = recent[-1]['value'] - recent[0]['value']
            pct_change = (total_change / recent[0]['value']) * 100 if recent[0]['value'] > 0 else 0
            message_lines.append(f"\n  7天总变化: {total_change:+.2f} USD ({pct_change:+.2f}%)")
        elif len(recent) == 1:
            message_lines.append(f"\n📈 今日净资产: ${fmt_amt(recent[0]['value'], 2)} (暂无历史对比)")
            
        message_lines.append("\n" + "=" * 40)
        message_lines.append(f"💰 账户总净资产（USD）：**${fmt_amt(total_net_usd, 2)}**")
        message_lines.append(f"   ├─ 资金账户贡献：${fmt_amt(funding_usd, 2)}")
        message_lines.append(f"   ├─ 交易账户权益：${fmt_amt(trading_eq_usd, 2)}")
        message_lines.append(f"   └─ 灵活借贷净值：${fmt_amt(flexible_net_usd, 2)}")
        message_lines.append("=" * 40)

        return "\n".join(message_lines)

    except Exception as e:
        return f"获取余额失败: {str(e)}\n类型: {type(e).__name__}"

# 检测借贷额度问题
async def check_lending_limit() -> Optional[str]:
    """
    使用 flexible_loan.get_loan_info() 的数据判断借贷风险：
    - 每15分钟检查一次（由调度器控制）
    - 仅当 curLTV >= 50% 时才发送警报
    """
    try:
        loan_resp = api.flexible_loan.get_loan_info()
        if loan_resp.get("code") != "0" or not loan_resp.get("data"):
            return None

        data = loan_resp["data"][0]
        cur_ltv = safe_float(data.get("curLTV")) * 100
        # 不到 50% 不发送任何信息
        if cur_ltv < 50.0:
            return None

        mcall = safe_float(data.get("marginCallLTV")) * 100
        liq = safe_float(data.get("liqLTV")) * 100

        # 列出已借详情
        loan_lines = []
        for loan in data.get("loanData", []):
            amt = safe_float(loan.get("amt"))
            if amt > 0.01:
                loan_lines.append(f"{loan.get('ccy','?')}: {fmt_amt(amt)}")

        alerts = []
        if cur_ltv >= mcall:
            alerts.append(f"❗ 当前 LTV {fmt_amt(cur_ltv,2)}% 已达到或超过预警 LTV {fmt_amt(mcall,2)}%（可能触发追加保证金/清算）")
        else:
            alerts.append(f"⚠️ 当前 LTV {fmt_amt(cur_ltv,2)}% 已超过阈值 50%，请关注（预警 LTV {fmt_amt(mcall,2)}% | 清算 LTV {fmt_amt(liq,2)}%）")

        if loan_lines:
            alerts.append("已借明细:")
            for l in loan_lines:
                alerts.append(f"  • {l}")

        collateral_usd = safe_float(data.get("collateralNotionalUsd"))
        loan_usd = safe_float(data.get("loanNotionalUsd"))
        alerts.append(f"抵押总值: ${fmt_amt(collateral_usd,2)} | 已借总额: ${fmt_amt(loan_usd,2)} | 清算 LTV: {fmt_amt(liq,2)}%")

        header = "⚠️ 灵活借贷警报\n"
        return header + "\n".join(alerts)

    except Exception as e:
        return f"检测借贷失败: {str(e)}"

async def send_daily_balance(app: Application):
    message = await get_balance_info()
    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

async def check_and_send_lending_alert(app: Application):
    alert = await check_lending_limit()
    if alert:
        await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=alert)

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("机器人已启动！/balance 查看余额，/lending 检查借贷 /price 查看价格。")

async def balance(update, context: ContextTypes.DEFAULT_TYPE):
    message = await get_balance_info()
    await update.message.reply_text(message)

async def lending(update, context: ContextTypes.DEFAULT_TYPE):
    alert = await check_lending_limit()
    if alert:
        await update.message.reply_text(alert)

def run_scheduler(app: Application, loop: asyncio.AbstractEventLoop):
    """
    Scheduler runs in a separate thread; use asyncio.run_coroutine_threadsafe
    to submit coroutines to the main event loop (avoids "no running event loop").
    """
    schedule.every().day.at("09:00").do(lambda: asyncio.run_coroutine_threadsafe(send_daily_balance(app), loop))
    schedule.every(15).minutes.do(lambda: asyncio.run_coroutine_threadsafe(check_and_send_lending_alert(app), loop))
    schedule.every(15).minutes.do(lambda: asyncio.run_coroutine_threadsafe(check_price_alerts(app), loop))
    while True:
        schedule.run_pending()
        time.sleep(1)

async def alert_command(update, context: ContextTypes.DEFAULT_TYPE):
    global PRICE_ALERTS, ALERT_COUNTER
    args = context.args

    if not args:
        await update.message.reply_text("用法：\n/alert btc above 90000\n/alert eth below 4000\n/alert list\n/alert clear")
        return

    cmd = args[0].lower()

    if cmd == 'list':
        if not PRICE_ALERTS:
            await update.message.reply_text("当前无价格警报")
            return
        msg = "当前价格警报：\n"
        for aid, a in PRICE_ALERTS.items():
            status = "（已触发）" if a.get('triggered') else ""
            msg += f"{aid}: {a['coin'].upper()} {a['direction']} ${a['price']:.2f}{status}\n"
        await update.message.reply_text(msg)
        return

    if cmd == 'clear':
        PRICE_ALERTS.clear()
        await update.message.reply_text("所有价格警报已清除")
        return

    # 设置新警报：/alert btc above 90000
    if len(args) != 3 or args[1].lower() not in ['above', 'below']:
        await update.message.reply_text("格式错误！示例：/alert btc above 90000")
        return

    coin = args[0].lower()
    direction = args[1].lower()
    try:
        price = float(args[2])
    except:
        await update.message.reply_text("价格必须是数字")
        return

    if coin not in [k.lower() for k in PRICE_SYMBOLS.keys()]:
        await update.message.reply_text(f"不支持的币种，目前支持：{', '.join(PRICE_SYMBOLS.keys())}")
        return

    ALERT_COUNTER += 1
    PRICE_ALERTS[ALERT_COUNTER] = {
        'coin': coin,
        'price': price,
        'direction': direction,
        'triggered': False
    }

    await update.message.reply_text(f"价格警报设置成功！\n当 {coin.upper()} {direction} ${price:.2f} 时将提醒你")