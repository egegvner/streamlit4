# Copyright Ege Güvener, 20/12/2024
# License: MIT

import numerize.numerize
import streamlit as st
import sqlite3
import random
import time
import pandas as pd
import datetime
import re
import argon2
from streamlit_autorefresh import st_autorefresh
from numerize.numerize import numerize
import streamlit as st

if "current_menu" not in st.session_state:
    st.session_state.current_menu = "Dashboard"

previous_layout = st.session_state.get("previous_layout", "centered")
current_layout = "wide" if st.session_state.current_menu == "Stocks" or st.session_state.current_menu == "Marketplace" or st.session_state.current_menu == "Investments" or st.session_state.current_menu == "Marketplace" or st.session_state.current_menu == "Main Account" or st.session_state.current_menu == "Marketplace" or st.session_state.current_menu == "Inventory" or st.session_state.current_menu == "Marketplace" or st.session_state.current_menu == "View Savings" else "centered"

if previous_layout != current_layout:
    st.session_state.previous_layout = current_layout
    st.rerun()

st.set_page_config(
    page_title="Bank Genova",
    page_icon="🏦",
    layout=current_layout,
    initial_sidebar_state="expanded"
)

ph = argon2.PasswordHasher(
    memory_cost=65536,  # 64MB RAM usage (default: 10240)
    time_cost=5,        # More iterations = stronger (default: 2)
    parallelism=4       # Number of parallel threads (default: 1)
)

def write_stream(s, delay = 0, random_delay = False):
    if random_delay:
        for i in s:
            yield i
            time.sleep(random.uniform(0.001, 0.05))
    else:
        for i in s:
            yield i
            time.sleep(delay)

@st.cache_resource
def get_db_connection():
    return sqlite3.connect("genova.db", check_same_thread = False)

item_colors = {
        "Common":":gray",
        "Uncommon":":green",
        "Rare":":blue",
        "Epic":":violet",
        "Ultimate":":orange"
    }

def format_currency(amount):
    if isinstance(amount, str):  # Convert if input is a string
        amount = amount.replace(",", "")  # Remove commas for conversion
        amount = float(amount)  # Convert to float
    return "{:,.2f}".format(amount)

# def format_currency(amount):
#     return "{:,.2f}".format(amount).replace(",", "X").replace(".", ",").replace("X", ".")

def hashPass(password):
    return ph.hash(password)

def verifyPass(hashed_password, entered_password):
    try:
        return ph.verify(hashed_password, entered_password)
    except:
        return False

admins = [
    "egegvner",
    "JohnyJohnJohn"
]

def apply_interest_if_due(conn, user_id, check = True):
    c = conn.cursor()
    current_time = time.time()
    if check:
        if current_time - st.session_state.last_refresh >= 5:
            st.session_state.last_refresh = current_time

            has_savings_account = c.execute("SELECT has_savings_account FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
            if not has_savings_account:
                return

            savings_data = c.execute("SELECT balance, last_interest_applied FROM savings WHERE user_id = ?", (user_id,)).fetchone()
            balance, last_applied = savings_data if savings_data else (0, None)

            last_applied_time = datetime.datetime.strptime(last_applied, "%Y-%m-%d %H:%M:%S") if last_applied else now

            now = datetime.datetime.now()

            hours_passed = (now - last_applied_time).total_seconds() / 3600

            hourly_interest_rate = c.execute("SELECT interest_rate FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]

            total_interest = balance * hourly_interest_rate * hours_passed
            new_balance = balance + total_interest

            c.execute("""
                INSERT INTO interest_history (user_id, interest_amount, new_balance)
                VALUES (?, ?, ?)
            """, (user_id, total_interest, new_balance))

            c.execute("""
                UPDATE savings
                SET balance = ?, last_interest_applied = ?
                WHERE user_id = ?
            """, (new_balance, now.strftime("%Y-%m-%d %H:%M:%S"), user_id))

            conn.commit()
            st.rerun()
        else:
            st.toast(f"Wait {int(5 - (current_time - st.session_state.last_refresh))} seconds before refreshing again.")
    
def change_password(conn, username, current_password, new_password):
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    real_password = result[0]
    if verifyPass(real_password, current_password):
        if new_password != "":
            if len(new_password) >= 8:
                hashed_new_password = hashPass(new_password)
                c.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_new_password, username))
                conn.commit()
                st.success("Password has been updated successfully.")
            else:
                st.error("New password must contain **at least 8 chars**.")
        else:
            st.error("Empty password is illegal.")
    else:
        st.error("Current password is incorrect.")

def add_email(c, conn, username, email):
    c.execute("UPDATE users SET email = ? WHERE username = ?", (email, username))
    conn.commit()
    st.success("Success!")
    time.sleep(2)
    st.rerun()

def change_visible_name(c, conn, username, new_name):
    c.execute("UPDATE users SET visible_name = ? WHERE username = ?", (new_name, username))
    conn.commit()
    st.success("Success!")
    time.sleep(2)
    st.rerun()

def check_cooldown(conn, user_id):
    c = conn.cursor()
    last_transaction = c.execute("SELECT last_transaction_time FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    if last_transaction:
        last_time = pd.to_datetime(last_transaction)
        current_time = pd.Timestamp.now()
        time_diff = (current_time - last_time).total_seconds()
        if time_diff < 15:
            st.warning(f"Cooldown in effect. Please wait {15 - int(time_diff)} seconds before your next transaction.")
            return False
    return True

def update_last_transaction_time(conn, user_id):
    c = conn.cursor()
    c.execute("UPDATE users SET last_transaction_time = ? WHERE user_id = ?", (datetime.datetime.now().isoformat(), user_id))
    conn.commit()

def recent_transactions_metrics(c, user_id):
    current_time = pd.Timestamp.now()
    last_24_hours = current_time - pd.Timedelta(days=1)
    last_24_hours_str = last_24_hours.strftime('%Y-%m-%d %H:%M:%S')

    transactions = c.execute("""
        SELECT type, COUNT(*), IFNULL(SUM(amount), 0) 
        FROM transactions 
        WHERE user_id = ? AND timestamp >= ? 
        GROUP BY type
    """, (user_id, last_24_hours_str)).fetchall()

    metrics = {
        "Top Ups": {"count": 0, "total": 0},
        "Withdrawals": {"count": 0, "total": 0},
        "Incoming Transfers": {"count": 0, "total": 0},
        "Outgoing Transfers": {"count": 0, "total": 0},
    }

    for trans_type, count, total in transactions:
        if "top up" in trans_type.lower():
            metrics["Top Ups"] = {"count": count, "total": total}
        elif "withdrawal" in trans_type.lower():
            metrics["Withdrawals"] = {"count": count, "total": total}
        elif trans_type.lower().startswith("transfer to"):
            metrics["Outgoing Transfers"] = {"count": count, "total": total}
        elif trans_type.lower().startswith("transfer from"):
            metrics["Incoming Transfers"] = {"count": count, "total": total}

    return metrics
    
def leaderboard_logic(c):
    result = c.execute("SELECT username, visible_name, balance FROM users ORDER BY balance DESC").fetchall()

    leaderboard = []
    rank = 1
    for row in result:
        username, visible_name, balance = row
        name_to_display = visible_name if visible_name else username
        leaderboard.append({
            "rank": rank,
            "name": name_to_display,
            "balance": balance
        })
        rank += 1

    return leaderboard

def get_transaction_history(conn, user_id):
    c = conn.cursor()
    username = c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    sender_query = """
        SELECT 'sent' AS role, type, amount, timestamp, status, receiver_username
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
    """
    sent_transactions = c.execute(sender_query, (user_id,)).fetchall()

    receiver_query = """
        SELECT 'received' AS role, type, amount, timestamp, status, user_id AS from_user_id
        FROM transactions
        WHERE  receiver_username = ?
        ORDER BY timestamp DESC
    """
    received_transactions = c.execute(receiver_query, (username,)).fetchall()

    return sent_transactions, received_transactions

def claim_daily_reward(conn, user_id):
    c = conn.cursor()
    last_claimed = c.execute("SELECT last_daily_reward_claimed FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    if last_claimed:
        last_claimed_date = datetime.datetime.strptime(last_claimed, "%Y-%m-%d")
        if last_claimed_date.date() == datetime.datetime.today().date():
            st.toast("You've already claimed your daily reward today!")
        else:
            streak = c.execute("SELECT login_streak FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
            new_streak = streak + 1 if last_claimed else 1
            reward = 100 + (new_streak * 2)

            c.execute("UPDATE users SET balance = balance + ?, last_daily_reward_claimed = ?, login_streak = ? WHERE user_id = ?", 
                    (reward, datetime.datetime.today().strftime("%Y-%m-%d"), new_streak, user_id))
            conn.commit()
            
            st.toast(f"🎉 You received ${reward} for logging in! (Streak: {new_streak})")
    else:
        last_claimed = datetime.datetime(1970, 1, 1)
        c.execute("UPDATE users SET last_daily_reward_claimed = ? WHERE user_id = ?", (last_claimed, user_id))
        conn.commit()

def update_stock_prices(conn):
    c = conn.cursor()
    now = datetime.datetime.now()

    stocks = c.execute("SELECT stock_id, price, last_updated, change_rate FROM stocks").fetchall()

    for stock_id, current_price, last_updated, change_rate in stocks:
        try:
            if last_updated:
                last_updated = datetime.datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
            else:
                last_updated = now - datetime.timedelta(seconds=300)

            elapsed_time = (now - last_updated).total_seconds()
            num_updates = int(elapsed_time // 300)

            if num_updates > 0:
                for i in range(num_updates):
                    change_percent = round(random.uniform(-change_rate, change_rate), 2)
                    new_price = max(1, round(current_price * (1 + change_percent / 100), 2))

                    missed_update_time = last_updated + datetime.timedelta(seconds=(i + 1) * 300)
                    if missed_update_time <= now:
                        c.execute(
                            "INSERT INTO stock_history (stock_id, price, timestamp) VALUES (?, ?, ?)",
                            (stock_id, new_price, missed_update_time.strftime("%Y-%m-%d %H:%M:%S"))
                        )
                    current_price = new_price

            c.execute(
                "UPDATE stocks SET price = ?, last_updated = ? WHERE stock_id = ?",
                (current_price, now.strftime("%Y-%m-%d %H:%M:%S"), stock_id)
            )
        except Exception as e:
            continue

    conn.commit()

def get_stock_metrics(conn, stock_id):
    c = conn.cursor()
    
    last_24_hours = datetime.datetime.now() - datetime.timedelta(days=1)
    
    result = c.execute("""
        SELECT MIN(price), MAX(price), price 
        FROM stock_history 
        WHERE stock_id = ? AND timestamp >= ?
    """, (stock_id, last_24_hours.strftime("%Y-%m-%d %H:%M:%S"))).fetchone()
    
    low_24h, high_24h, last_price = result if result else (None, None, None)

    c.execute("""
        SELECT MIN(price), MAX(price) 
        FROM stock_history 
        WHERE stock_id = ?
    """, (stock_id,))
    
    result = c.fetchone()
    all_time_low, all_time_high = result if result else (None, None)

    c.execute("""
        SELECT price 
        FROM stock_history 
        WHERE stock_id = ? AND timestamp >= ?
        ORDER BY timestamp ASC
        LIMIT 1
    """, (stock_id, last_24_hours.strftime("%Y-%m-%d %H:%M:%S")))
    
    price_24h_ago = c.fetchone()
    price_24h_ago = price_24h_ago[0] if price_24h_ago else last_price

    delta_24h_high = last_price - high_24h if high_24h else None
    delta_24h_low = last_price - low_24h if low_24h else None
    delta_all_time_high = last_price - all_time_high if all_time_high else None
    delta_all_time_low = last_price - all_time_low if all_time_low else None
    price_change_percent = ((last_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago else 0

    return {
        "low_24h": low_24h,
        "high_24h": high_24h,
        "all_time_low": all_time_low,
        "all_time_high": all_time_high,
        "price_change": price_change_percent,
        "delta_24h_high": delta_24h_high,
        "delta_24h_low": delta_24h_low,
        "delta_all_time_high": delta_all_time_high,
        "delta_all_time_low": delta_all_time_low
    }

def update_inflation(conn):
    c = conn.cursor()
    
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    last_entry = c.execute("SELECT date FROM inflation_history ORDER BY date DESC LIMIT 1").fetchone()
    if last_entry and last_entry[0] == today:
        return  # Already updated today
    
    new_inflation = round(random.uniform(-0.05, 0.05), 4)
    
    c.execute("INSERT INTO inflation_history (date, inflation_rate) VALUES (?, ?)", (today, new_inflation))
    conn.commit()


def get_latest_message_time(conn):
    c = conn.cursor()
    latest = c.execute("SELECT MAX(timestamp) FROM chats").fetchone()[0]
    return latest if latest else "1970-01-01 00:00:00"

def get_inflation_history(c):
    history = c.execute("SELECT date, inflation_rate FROM inflation_history ORDER BY date ASC").fetchall()
    return pd.DataFrame(history, columns=["Date", "Inflation Rate"])

def check_and_apply_loan_penalty(conn, user_id):
    c = conn.cursor()
    
    user_data = c.execute("SELECT loan, loan_due_date, loan_penalty FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if not user_data or user_data[0] == 0:
        return  # No loan, no penalty

    loan, due_date, penalty = user_data

    if not due_date:
        return

    today = datetime.date.today()
    due_date_obj = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()

    if today > due_date_obj:
        days_overdue = (today - due_date_obj).days
        penalty_amount = round(loan * 0.01 * days_overdue, 2)  # 1% penalty per day

        new_loan = loan + penalty_amount
        new_penalty = penalty + penalty_amount

        c.execute("UPDATE users SET loan = ?, loan_penalty = ? WHERE user_id = ?", (new_loan, new_penalty, user_id))
        conn.commit()

        print(f"⚠ User {user_id} has an overdue loan! Added ${penalty_amount:.2f} penalty.")

def calculate_investment_return(risk_rate, amount):
    success_rate = max(0.1, min(1, 1 - risk_rate))  # Higher risk means lower success chance
    success = random.random() <= success_rate

    if success:
        return round(amount * random.uniform(risk_rate, risk_rate * 2), 2)  # High risk => high return
    else:
        return -amount

def check_and_update_investments(conn, user_id):
    c = conn.cursor()
    now = datetime.datetime.now()

    pending_investments = c.execute("""
        SELECT investment_id, company_name, amount, risk_level, return_rate, end_date 
        FROM investments 
        WHERE user_id = ? AND status = 'pending'
    """, (user_id,)).fetchall()

    for investment_id, company_name, amount, risk_level, return_rate, end_date in pending_investments:
        end_date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")

        if now >= end_date_obj:
            risk_level = float(risk_level)  # Ensure that risk_level is treated as a float

            success = random.random() <= max(0.1, min(1, 1 - risk_level))  # Higher risk = lower success chance

            if success:
                profit = round(amount * random.uniform(1 + risk_level, 1 + (risk_level * 2)), 2)  # Calculate profit
                outcome = "profit"
            else:
                profit = -amount
                outcome = "loss"

            new_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0] + profit
            c.execute("UPDATE users SET wallet = ? WHERE user_id = ?", (new_balance, user_id))

            c.execute("""
                UPDATE investments 
                SET status = ?, return_rate = ? 
                WHERE investment_id = ?
            """, (outcome, profit, investment_id))

            conn.commit()

            if success:
                st.toast(f"✅ Your investment in {company_name} has completed successfully! You earned :green[${numerize(profit)}].")
            else:
                st.toast(f"❌ Your investment in {company_name} failed. You lost :red[${numerize(amount)}].")

    conn.commit()

def register_user(conn, username, password, email = None, visible_name = None):
    c = conn.cursor()
    try:

        user_id_to_be_registered = random.randint(100000, 999999)
        hashed_password = hashPass(password)
                
        with st.spinner("Creatning your account..."):
            c.execute('''INSERT INTO users (user_id, username, level, visible_name, password, balance, wallet, has_savings_account, suspension, deposits, withdraws, incoming_transfers, outgoing_transfers, total_transactions, last_transaction_time, email, last_daily_reward_claimed)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (
                   user_id_to_be_registered,
                   username,
                   1,    # Default level
                   visible_name,
                   hashed_password, 
                   10,   # Default balance
                   0,    # Default wallet
                   0,    # Default savings account
                   0,    # Default suspension (0 = not suspended)
                   0,    # Default deposits
                   0,    # Default withdraws
                   0,    # Default incoming transfers
                   0,    # Default outgoing transfers
                   0,    # Default total transactions
                   None, # Default last transaction time
                   email,
                   datetime.datetime.today().strftime("%Y-%m-%d")
                   ))
            conn.commit()

        st.session_state.logged_in = True
        st.session_state.user_id = user_id_to_be_registered
        st.session_state.username = username
        time.sleep(2)

        st.session_state.current_menu = "Dashboard"
        st.balloons()
        dashboard(conn, st.session_state.user_id)

    except sqlite3.IntegrityError:
        st.error("Username already exists!")
        return False
    except Exception as e:
        st.error(f"Error: {e}")
        return False
        
def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
                  user_id INTEGER PRIMARY KEY NOT NULL,
                  username TEXT NOT NULL UNIQUE,
                  level INTEGER DEFAULT 0,
                  visible_name TEXT,
                  password TEXT NOT NULL,
                  balance REAL DEFAULT 10,
                  wallet REAL DEFAULT 0,
                  has_savings_account INTEGER DEFAULT 0,
                  suspension INTEGER DEFAULT 0,
                  deposits INTEGER DEFAULT 0,
                  withdraws INTEGER DEFAULT 0,
                  incoming_transfers INTEGER DEFAULT 0,
                  outgoing_transfers INTEGER DEFAULT 0,
                  total_transactions INTEGER DEFAULT 0,
                  last_transaction_time DATETIME DEFAULT NULL,
                  email TEXT,
                  last_daily_reward_claimed TIMESTAMP DEFAULT NULL,
                  login_streak INTEGER DEFAULT 0,
                  show_main_balance_on_leaderboard INTEGER DEFAULT 1,
                  show_wallet_on_leaderboard INTEGER DEFAULT 1,
                  show_savings_balance_on_leaderboard INTEGER DEFAULT 1,
                  last_savings_refresh DATETIME NOT NULL,
                  steal_cooldown DATETIME DEFAULT CURRENT_TIMESTAMP,
                  attack_level INTEGER DEFAULT 0,
                  defense_level INTEGER DEFAULT 0
                  )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                receiver_username TEXT DEFAULT None,
                status TEXT DEFAULT None,
                stock_id INTEGER DEFAULT 0,
                quantity INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (receiver_username) REFERENCES users(username)
                )''')
        
    c.execute('''CREATE TABLE IF NOT EXISTS savings (
                user_id INTEGER NOT NULL,
                balance REAL DEFAULT 0,
                interest_rate REAL DEFAULT 0.05,
                last_interest_applied DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id ) REFERENCES users(user_id)
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS marketplace_items (
                item_id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                rarity TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                boost_type TEXT NOT NULL,
                boost_value REAL NOT NULL,
                duration INTEGER DEFAULT NULL
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_inventory (
                instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                item_number INTEGER NOT NULL,
                acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (item_id) REFERENCES marketplace_items(item_id)
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS interest_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                interest_amount REAL NOT NULL,
                new_balance REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS stocks (
                stock_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                symbol TEXT NOT NULL UNIQUE,
                starting_price REAL NOT NULL,
                price REAL NOT NULL,
                stock_amount INTEGER NOT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                stock_id INTEGER NOT NULL,
                quantity REAL NOT NULL,
                avg_buy_price REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (stock_id) REFERENCES stocks(stock_id)
                );''')

    c.execute('''CREATE TABLE IF NOT EXISTS stock_history (
                stock_id INTEGER NOT NULL,
                price REAL NOT NULL,
                timestamp DATETIME NOT NULL
                );''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS inflation_history (
                date TEXT PRIMARY KEY,  
                inflation_rate REAL  
                );''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS investments (
                investment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_name TEXT NOT NULL,
                amount REAL NOT NULL,
                risk_level TEXT NOT NULL,
                return_rate REAL NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                );''')

    c.execute('''CREATE TABLE IF NOT EXISTS investment_companies (
                company_id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                risk_level REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS blackmarket_items (
              item_id INTEGER NOT NULL,
              item_number INTEGER NOT NULL,
              name TEXT NOT NULL,
              description TEXT,
              rarity TEXT NOT NULL,
              price REAL NOT NULL,
              image_url TEXT NOT NULL,
              seller_id INTEGER NOT NULL
              )
''')
    
    conn.commit()
    return conn, c
    
@st.dialog("Withdraw", width = "small")
def withdraw_dialog(conn, user_id):

    c = conn.cursor()
    has_savings = c.execute("SELECT has_savings_account FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    current_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    
    if "withdraw_value" not in st.session_state:
        st.session_state.withdraw_value = 0.00

    st.write(f"# Balance -> :green[${numerize(current_balance, 2)}]")
    st.header("", divider = "rainbow")
    
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("%25", use_container_width = True):
        st.session_state.withdraw_value = (current_balance / 100) * 25
    if c2.button("%50", use_container_width = True):
        st.session_state.withdraw_value = (current_balance / 100) * 50
    if c3.button("%75", use_container_width = True):
        st.session_state.withdraw_value = (current_balance / 100) * 75
    if c4.button("%100", use_container_width = True):
        st.session_state.withdraw_value = current_balance 
    
    amount = st.number_input("Amount", min_value = 0.0, step = 0.25, value = st.session_state.withdraw_value)
    st.divider()
    tax = (amount / 100) * 0.5
    net = amount - tax
    st.write(f"Net Withdraw -> :green[{numerize(net, 2)}] $|$ :red[${numerize(tax, 2)} Tax*]")
    c1, c2 = st.columns(2)
    c1.write(f"Remaining Balance -> :green[${numerize((current_balance - amount), 2)}]")
    if (current_balance - amount) < 0:
        c2.write("**:red[Insufficent]**")

    c1, c2 = st.columns(2)
    if c1.button("Withdraw to **Wallet**", type = "secondary", use_container_width = True, disabled = True if net <= 0 or (current_balance - amount) < 0 else False, help = "Insufficent funds" if net <= 0 or (current_balance - net) < 0 else None):
        if check_cooldown(conn, user_id):
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (net, user_id))
            conn.commit()
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount) VALUES (?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, "Withdraw From Main Account To Wallet", net))
            c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (tax,))
            conn.commit()
            update_last_transaction_time(conn, user_id)
            with st.spinner("Processing..."):
                time.sleep(random.uniform(1, 2))
                st.success(f"Successfully withdrawn ${net:.2f}")
            st.session_state.withdraw_value = 0.0
            time.sleep(1)
            st.rerun()
            
    if c2.button("Withdraw to **Savings**", type = "primary", use_container_width = True, disabled = True if net <= 0 or (current_balance - amount) < 0 or not has_savings else False, help = "Insufficent funds" if net <= 0 or (current_balance - net) < 0 else None):
        if check_cooldown(conn, user_id):
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            c.execute("UPDATE savings SET balance = balance + ? WHERE user_id = ?", (net, user_id))
            conn.commit()
            new_savings_balance = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount) VALUES (?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, "Withdraw From Main Account To Savings", amount))
            c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (tax,))
            conn.commit()
            update_last_transaction_time(conn, user_id)
            with st.spinner("Processing..."):
                time.sleep(random.uniform(1, 2))
                st.success(f"Successfully withdrawn ${amount:.2f}")
            st.session_state.withdraw_value = 0.0
            time.sleep(1)
            st.rerun()

    st.text(" ")
    st.caption("*All transactions are subject to %0.5 tax (VAT) and are irreversible.")

@st.dialog("Transfer Funds", width="small")
def transfer_dialog(conn, user_id):

    c = conn.cursor()
    all_users = [user[0] for user in c.execute("SELECT username FROM users WHERE username != ?", (st.session_state.username,)).fetchall()]
    st.header(" ", divider = "rainbow")

    current_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    st.header(f"Current Balance -> :green[${numerize(current_balance)}]")
    st.divider()
    receiver_username = st.selectbox("Recipient Username", options = all_users)
    amount = st.number_input("Amount", min_value = 0.0, step=0.25)
    tax = (amount / 100) * 0.5
    net = amount - tax
    st.divider()

    st.write(f"Net Transfer -> :green[${numerize(net, 2)}] $|$ :red[${numerize(tax, 2)} Tax]")
    st.caption("*Tax is not applied untill receiver accepts the transaction.")
    
    if st.button("Initiate Transfer", type = "primary", use_container_width = True, disabled = True if amount == 0.00 else False):
        if check_cooldown(conn, user_id):
            receiver_user_id = c.execute("SELECT user_id FROM users WHERE username = ?", (receiver_username,)).fetchone()

            if receiver_user_id:
                receiver_user_id = receiver_user_id[0]

                existing_transfer = c.execute("""
                    SELECT COUNT(*)
                    FROM transactions
                    WHERE user_id = ? AND  receiver_username = ? AND status = 'pending'
                """, (user_id, receiver_username)).fetchone()[0]
                
                if existing_transfer > 0:
                    st.warning(f"A pending transfer to {receiver_username} already exists. Please wait for it to be accepted or rejected.")
                    return

                current_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

                if amount <= current_balance:
                    c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
                    c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, receiver_username, status) VALUES (?, ?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f'Transfer to {receiver_username}', amount, receiver_username, 'pending'))
                    conn.commit()
                    with st.spinner("Processing"):
                        time.sleep(1)
                    st.success(f"Successfully initiated transfer of ${amount:.2f} to {receiver_username}. Awaiting acceptance.")
                    update_last_transaction_time(conn, user_id)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid transfer amount. Must be within current balance and below $1,000,000.")
            else:
                st.error(f"User {receiver_username} does not exist.")
    
    st.caption("All transactions are subject to %0.5 tax (VAT) and irreversible.*")
    
@st.dialog("Deposit To Savings", width = "small")
def deposit_to_savings_dialog(conn, user_id):

    c = conn.cursor()

    if "deposit_to_savings_value" not in st.session_state:
        st.session_state.deposit_to_savings_value = 0.00
    
    if "deposit_source" not in st.session_state:
        st.session_state.deposit_source = 0.00

    current_savings = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]
    main_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    st.header(f"Savings -> :green[${numerize(current_savings, 2)}]", divider = "rainbow")
    st.write("#### Deposit Source")
    st.session_state.deposit_source = st.radio("A", label_visibility = "collapsed", options = [f"Main Account   •   :green[${numerize(main_balance, 2)}]", f"Wallet   •   :green[${numerize(wallet_balance, 2)}]"])

    max_value = main_balance if "Main" in st.session_state.deposit_source else wallet_balance

    if st.session_state.deposit_to_savings_value > max_value:
        st.session_state.deposit_to_savings_value = max_value

    c1, c2, c3, c4 = st.columns(4)

    if c1.button("%25", use_container_width=True):
        st.session_state.deposit_to_savings_value = (main_balance / 100) * 25 if "Main" in st.session_state.deposit_source else (wallet_balance / 100) * 25
    if c2.button("%50", use_container_width=True):
        st.session_state.deposit_to_savings_value = (main_balance / 100) * 50 if "Main" in st.session_state.deposit_source else (wallet_balance / 100) * 50
    if c3.button("%75", use_container_width=True):
        st.session_state.deposit_to_savings_value = (main_balance / 100) * 75 if "Main" in st.session_state.deposit_source else (wallet_balance / 100) * 75
    if c4.button("%100", use_container_width=True):
        st.session_state.deposit_to_savings_value = main_balance if "Main" in st.session_state.deposit_source else wallet_balance

    amount = st.number_input("Amount", min_value = 0.00, max_value = max_value, value = st.session_state.deposit_to_savings_value)
    tax = (amount / 100) * 0.5
    net = amount - tax

    st.divider()
    st.write(f"Net Deposit -> :green[${numerize(net, )}]   $|$   :red[${numerize(tax, 2)} Tax]")
    st.write(f"New Savings -> :green[${numerize((current_savings + net), 2)}]")
    if st.button("Confirm Deposition From Main Account" if "Main" in st.session_state.deposit_source else "Confirm Deposition From Wallet", type="primary", use_container_width = True, disabled = True if amount <= 0.00 else False):
        if check_cooldown(conn, user_id):
            if "Main" in st.session_state.deposit_source:
                if amount > main_balance:
                    st.error("Insufficient funds in Main Account.")
                    return
            elif "Wallet" in st.session_state.deposit_source:
                if amount > wallet_balance:
                    st.error("Insufficient funds in Wallet.")
                    return

            if amount <= 0:
                st.error("Deposit amount must be greater than zero.")
                return

            if "Main" in st.session_state.deposit_source:
                c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            else:
                c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (amount, user_id))

            c.execute("UPDATE savings SET balance = balance + ? WHERE user_id = ?", (net, user_id))

            source = "Main Account" if "Main" in st.session_state.deposit_source else "Wallet"
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount) VALUES (?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f"Deposit To Savings From {source}", amount))
            c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (tax,))
            conn.commit()
            update_last_transaction_time(conn, user_id)
            with st.spinner("Processing..."):
                time.sleep(1)
            st.success(f"Successfully deposited ${numerize(net, 2)} from {source} to savings.")
            time.sleep(1)
            st.rerun()

    st.caption("All transactions are subject to %0.5 tax (VAT) and irreversible.*")

@st.dialog("Deposit To Vault", width = "small")
def deposit_from_wallet_dialog(conn, user_id):

    c = conn.cursor()
    wallet = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    if "wallet" not in st.session_state:
        st.session_state.wallet = 0.00

    st.title(f"Wallet | :green[${numerize(wallet)}]")
    st.header("", divider="rainbow")

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("%25", use_container_width = True):
        st.session_state.wallet = (wallet / 100) * 25
    if c2.button("%50", use_container_width = True):
        st.session_state.wallet = (wallet / 100) * 50
    if c3.button("%75", use_container_width = True):
        st.session_state.wallet = (wallet / 100) * 75
    if c4.button("%100", use_container_width = True):
        st.session_state.wallet = wallet 
    balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    amount = st.number_input("Amount", min_value=0.0, max_value=float(wallet), step = 0.25, value=st.session_state.wallet)
    tax = (amount / 100) * 0.5
    net = amount - tax
    st.divider()
    st.write(f"Net Deposit -> :green[${numerize(net)}] | :red[${numerize(tax)} Tax.]")
    st.write(f"Remaining Wallet -> :green[${numerize(wallet - amount)}]")
    if st.button("Confirm Deposition to Vault", use_container_width = True, type="primary", disabled = True if st.session_state.wallet <= 0 or amount <= 0 else False):
        with st.spinner("Processing..."):
            c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (amount, user_id))
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (net, user_id))
            c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (tax,))
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount) VALUES (?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f"Deposit To Vault From Wallet", amount))
            st.session_state.wallet = wallet - amount
            conn.commit()
            time.sleep(2)
        st.success(f"Successfully deposited ${numerize(net)}")
        time.sleep(1)
        st.rerun()
    
    st.caption("All transactions are subject to %0.5 tax (VAT) and irreversible.*")

@st.dialog("Withdraw Savings", width = "small")
def withdraw_from_savings_dialog(conn, user_id):

    c = conn.cursor()

    if "withdraw_from_savings_value" not in st.session_state:
        st.session_state.withdraw_from_savings_value = 0.00
    
    if "withdraw_target" not in st.session_state:
        st.session_state.withdraw_target = 0.00

    current_savings = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]
    
    st.header(f"Savings -> :green[${numerize((current_savings), 2)}]", divider = "rainbow")
    
    c1, c2, c3, c4 = st.columns(4)

    if c1.button("%25", use_container_width=True):
        st.session_state.withdraw_from_savings_value = (current_savings / 100) * 25
    if c2.button("%50", use_container_width=True):
        st.session_state.withdraw_from_savings_value = (current_savings / 100) * 50
    if c3.button("%75", use_container_width=True):
        st.session_state.withdraw_from_savings_value = (current_savings / 100) * 75
    if c4.button("%100", use_container_width=True):
        st.session_state.withdraw_from_savings_value = current_savings

    amount = st.number_input("Amount", min_value = 0.00, max_value = current_savings, value = st.session_state.withdraw_from_savings_value, step = 0.25)
    tax = (amount / 100) * 0.5
    net = amount - tax

    st.divider()
    st.write(f"Net Withdrawal -> :green[${numerize(net, 2)}] $|$ :red[${numerize(tax, 2)} Tax]")
    st.write(f"Remaining Savings -> :green[${numerize((current_savings - amount), 2)}]")
    c1, c2 = st.columns(2)

    if c1.button("Withdraw to Wallet", type = "secondary", use_container_width = True, disabled = True if amount <= 0.00 else False):
        if check_cooldown(conn, user_id):
            c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (net, user_id))
            c.execute("UPDATE savings SET balance = balance - ? WHERE user_id = ?", (amount, user_id))

            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount) VALUES (?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f"Withdraw from Savings to Wallet", amount))
            c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (tax,))
            conn.commit()

            update_last_transaction_time(conn, user_id)
            with st.spinner("Processing..."):
                time.sleep(random.uniform(1, 2))
            st.success(f"Successfully withdrawn ${numerize(net, 2)} to Wallet")
            time.sleep(1.5)
            st.session_state.withdraw_from_savings_value = 0.0
            st.rerun()

    if c2.button("Withdraw to Vault", type = "primary", use_container_width = True, disabled = True if amount <= 0.00 else False):
        if check_cooldown(conn, user_id):
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (net, user_id))
            c.execute("UPDATE savings SET balance = balance - ? WHERE user_id = ?", (amount, user_id))

            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount) VALUES (?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f"Withdraw from Savings to Vault", amount))
            c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (tax,))
            conn.commit()

            update_last_transaction_time(conn, user_id)
            with st.spinner("Processing..."):
                time.sleep(random.uniform(1, 2))
            st.success(f"Successfully withdrawn ${numerize(net, 2)} to Vault")
            time.sleep(1.5)
            st.session_state.withdraw_from_savings_value = 0.0
            st.rerun()

    st.caption("All transactions are subject to %0.5 tax (VAT) and irreversible.*")

@st.dialog("Item Details")
def item_options(conn, user_id, item_id):
    c = conn.cursor()
    owned_item_ids = [item_id[0] for item_id in c.execute("SELECT item_id FROM user_inventory WHERE user_id = ?", (user_id,)).fetchall()]
    item_data = c.execute("SELECT name, description, rarity, price, stock, image_url FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchall()[0]
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    st.header(f"{item_colors[item_data[2]]}[{item_data[0]}] :gray[  **•**   {item_data[2].upper()}]", divider = "rainbow")
    st.text("")
    st.text("")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        c1.image(image=item_data[5], use_container_width=True)

        c2.write(f"**:gray[[EFFECT]]** {item_data[1]}.")
        c2.write(f"**:gray[[PRICE]]** :green[${numerize(item_data[3], 2)}]")
        c2.write(f"**:gray[[STOCK]]** :green[{item_data[4]}]")

    st.divider()
    st.write(f"Wallet -> :green[${numerize(wallet_balance, 2)}]   **•**   :red[INSUFFICENT]" if wallet_balance < item_data[3] else f"Wallet   **•**   :green[${numerize(wallet_balance, 2)}]")
    if item_id in owned_item_ids:
        st.warning("You already own this item.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", use_container_width = True):
        st.rerun()
    if c2.button(f"**Pay :green[${numerize(item_data[3], 2)}] With Wallet**", type = "primary", use_container_width = True, disabled = True if wallet_balance < item_data[3] or item_id in owned_item_ids else False):
        buy_item(conn, user_id, item_id)
    st.caption(f":gray[ID   {item_id}]")

@st.dialog("Privacy Policy", width="large")
def privacy_policy_dialog():
    st.header("", divider="rainbow")
    st.title("**Last Updated: Jan 11, 2025**")
    st.write("This Privacy Policy describes Our policies and procedures in this :orange[game] on the collection, use and disclosure of Your information when You use the Service and tells You about Your privacy rights and how the law protects You.")
    st.write("We use Your Personal data to provide and improve the Service. By using the Service, You agree to the collection and use of information in accordance with this Privacy Policy.")
    st.title("**Interpretation and Definitions**")
    st.subheader("**Interpretation**")
    st.write("The words of which the initial letter is capitalized have meanings defined under the following conditions. The following definitions shall have the same meaning regardless of whether they appear in singular or in plural.")
    st.subheader("**Definitions**")
    st.write("For the purposes of this Privacy Policy:")
    st.write("* Account means a unique account created for You to access our Service or parts of our Service.")
    st.write("* Company (referred to as either 'the Company', 'We', 'Us' or 'Our' in this Agreement) refers to Bank Genova.")
    st.write("* Cookies are small files that are placed on Your computer, mobile device or any other device by a website, containing the details of Your browsing history on that website among its many uses.")
    st.write("* Country refers to: China")
    st.write("* Device means any device that can access the Service such as a computer, a cellphone or a digital tablet.")
    st.write("* Device means any device that can access the Service such as a computer, a cellphone or a digital tablet.")
    st.write("* Service refers to the Website.")
    st.write("* Service Provider means any natural or legal person who processes the data on behalf of the Company. It refers to third-party companies or individuals employed by the Company to facilitate the Service, to provide the Service on behalf of the Company, to perform services related to the Service or to assist the Company in analyzing how the Service is used.")
    st.write("* Usage Data refers to data collected automatically, either generated by the use of the Service or from the Service infrastructure itself (for example, the duration of a page visit).")
    st.write("* Website refers to Bank Genova, accessible from https://bank-genova.streamlit.app/")
    st.write("* You means the individual accessing or using the Service, or the company, or other legal entity on behalf of which such individual is accessing or using the Service, as applicable.")
    st.title("Collecting and Using Your Personal Data")
    st.subheader("Personal Data")
    st.write("While using Our Service, We may ask You to provide Us with certain personally identifiable information that can be used to contact or identify You. Personally identifiable information may include, but is not limited to:")
    st.write("* Email address")
    st.write("* First name and last name")
    st.write("* Usage Data")
    st.subheader("Usage Data")
    st.write("Usage Data is collected automatically when using the Service.")
    st.write("Usage Data may include information such as Your Device's Internet Protocol address (e.g. IP address), browser type, browser version, the pages of our Service that You visit, the time and date of Your visit, the time spent on those pages, unique device identifiers and other diagnostic data.")
    st.write("When You access the Service by or through a mobile device, We may collect certain information automatically, including, but not limited to, the type of mobile device You use, Your mobile device unique ID, the IP address of Your mobile device, Your mobile operating system, the type of mobile Internet browser You use, unique device identifiers and other diagnostic data.")
    st.write("We may also collect information that Your browser sends whenever You visit our Service or when You access the Service by or through a mobile device.")
    st.subheader("Tracking Technologies and Cookies")
    st.write("We use Cookies and similar tracking technologies to track the activity on Our Service and store certain information. Tracking technologies used are beacons, tags, and scripts to collect and track information and to improve and analyze Our Service. The technologies We use may include:")
    st.write("* Cookies or Browser Cookies. A cookie is a small file placed on Your Device. You can instruct Your browser to refuse all Cookies or to indicate when a Cookie is being sent. However, if You do not accept Cookies, You may not be able to use some parts of our Service. Unless you have adjusted Your browser setting so that it will refuse Cookies, our Service may use Cookies.")
    st.write("* Web Beacons. Certain sections of our Service and our emails may contain small electronic files known as web beacons (also referred to as clear gifs, pixel tags, and single-pixel gifs) that permit the Company, for example, to count users who have visited those pages or opened an email and for other related website statistics (for example, recording the popularity of a certain section and verifying system and server integrity).")
    st.write("Cookies can be 'Persistent' or 'Session' Cookies. Persistent Cookies remain on Your personal computer or mobile device when You go offline, while Session Cookies are deleted as soon as You close Your web browser. ")
    st.write("We use both Session and Persistent Cookies for the purposes set out below:")
    st.write("* Necessary / Essential Cookies")
    st.write("These Cookies are essential to provide You with services available through the Website and to enable You to use some of its features. They help to authenticate users and prevent fraudulent use of user accounts. Without these Cookies, the services that You have asked for cannot be provided, and We only use these Cookies to provide You with those services.")
    st.write("* Cookies Policy / Notice Acceptance Cookies")
    st.write("These Cookies identify if users have accepted the use of cookies on the Website.")
    st.write("* Functionality Cookies")
    st.write("Purpose: These Cookies allow us to remember choices You make when You use the Website, such as remembering your login details or language preference. The purpose of these Cookies is to provide You with a more personal experience and to avoid You having to re-enter your preferences every time You use the Website.")
    st.write("For more information about the cookies we use and your choices regarding cookies, please visit our Cookies Policy or the Cookies section of our Privacy Policy.")
    st.title("Use of Your Personal Data")
    st.write("The Company may use Personal Data for the following purposes:")
    st.write("* To provide and maintain our Service, including to monitor the usage of our Service.")
    st.write("* To manage Your Account: to manage Your registration as a user of the Service. The Personal Data You provide can give You access to different functionalities of the Service that are available to You as a registered user.")
    st.write("* For the performance of a contract: the development, compliance and undertaking of the purchase contract for the products, items or services You have purchased or of any other contract with Us through the Service.")
    st.write("* To contact You: To contact You by email, telephone calls, SMS, or other equivalent forms of electronic communication, such as a mobile application's push notifications regarding updates or informative communications related to the functionalities, products or contracted services, including the security updates, when necessary or reasonable for their implementation.")
    st.write("* To provide You with news, special offers and general information about other goods, services and events which we offer that are similar to those that you have already purchased or enquired about unless You have opted not to receive such information.")
    st.write("* To manage Your requests: To attend and manage Your requests to Us.")
    st.write("* For business transfers: We may use Your information to evaluate or conduct a merger, divestiture, restructuring, reorganization, dissolution, or other sale or transfer of some or all of Our assets, whether as a going concern or as part of bankruptcy, liquidation, or similar proceeding, in which Personal Data held by Us about our Service users is among the assets transferred.")
    st.write("* For other purposes: We may use Your information for other purposes, such as data analysis, identifying usage trends, determining the effectiveness of our promotional campaigns and to evaluate and improve our Service, products, services, marketing and your experience.")
    st.write("We may share Your personal information in the following situations:")
    st.write("* With Service Providers: We may share Your personal information with Service Providers to monitor and analyze the use of our Service, to contact You.")
    st.write("* For business transfers: We may share or transfer Your personal information in connection with, or during negotiations of, any merger, sale of Company assets, financing, or acquisition of all or a portion of Our business to another company.")
    st.write("* With Affiliates: We may share Your information with Our affiliates, in which case we will require those affiliates to honor this Privacy Policy. Affiliates include Our parent company and any other subsidiaries, joint venture partners or other companies that We control or that are under common control with Us.")
    st.write("* With business partners: We may share Your information with Our business partners to offer You certain products, services or promotions.")
    st.write("* With other users: when You share personal information or otherwise interact in the public areas with other users, such information may be viewed by all users and may be publicly distributed outside.")
    st.write("* With Your consent: We may disclose Your personal information for any other purpose with Your consent.")
    st.title("Retention of Your Personal Data")
    st.write("The Company will retain Your Personal Data only for as long as is necessary for the purposes set out in this Privacy Policy. We will retain and use Your Personal Data to the extent necessary to comply with our legal obligations (for example, if we are required to retain your data to comply with applicable laws), resolve disputes, and enforce our legal agreements and policies.")
    st.write("The Company will also retain Usage Data for internal analysis purposes. Usage Data is generally retained for a shorter period of time, except when this data is used to strengthen the security or to improve the functionality of Our Service, or We are legally obligated to retain this data for longer time periods.")
    st.title("Transfer of Your Personal Data")
    st.write("Your information, including Personal Data, is processed at the Company's operating offices and in any other places where the parties involved in the processing are located. It means that this information may be transferred to — and maintained on — computers located outside of Your state, province, country or other governmental jurisdiction where the data protection laws may differ than those from Your jurisdiction.")
    st.write("Your consent to this Privacy Policy followed by Your submission of such information represents Your agreement to that transfer.")
    st.write("The Company will take all steps reasonably necessary to ensure that Your data is treated securely and in accordance with this Privacy Policy and no transfer of Your Personal Data will take place to an organization or a country unless there are adequate controls in place including the security of Your data and other personal information.")
    st.title("Delete Your Personal Data")
    st.write("You have the right to delete or request that We assist in deleting the Personal Data that We have collected about You.")
    st.write("Our Service may give You the ability to delete certain information about You from within the Service.")
    st.write("You may update, amend, or delete Your information at any time by signing in to Your Account, if you have one, and visiting the account settings section that allows you to manage Your personal information. You may also contact Us to request access to, correct, or delete any personal information that You have provided to Us.")
    st.write("Please note, however, that We may need to retain certain information when we have a legal obligation or lawful basis to do so.")
    st.title("Disclosure of Your Personal Data")
    st.subheader("Business Transaction")
    st.write("If the Company is involved in a merger, acquisition or asset sale, Your Personal Data may be transferred. We will provide notice before Your Personal Data is transferred and becomes subject to a different Privacy Policy.")
    st.subheader("Law enforcement")
    st.write("Under certain circumstances, the Company may be required to disclose Your Personal Data if required to do so by law or in response to valid requests by public authorities (e.g. a court or a government agency).")
    st.subheader("Other legal requirements")
    st.write("The Company may disclose Your Personal Data in the good faith belief that such action is necessary to:")
    st.write("* Comply with a legal obligation")
    st.write("* Protect and defend the rights or property of the Company")
    st.write("* Prevent or investigate possible wrongdoing in connection with the Service")
    st.write("* Protect the personal safety of Users of the Service or the public")
    st.write("* Protect against legal liability")
    st.subheader("Security of Your Personal Data")
    st.write("The security of Your Personal Data is important to Us, but remember that no method of transmission over the Internet, or method of electronic storage is 100% secure. While We strive to use commercially acceptable means to protect Your Personal Data, We cannot guarantee its absolute security.")
    st.title("Children's Privacy")
    st.write("Our Service does not address anyone under the age of 13. We do not knowingly collect personally identifiable information from anyone under the age of 13. If You are a parent or guardian and You are aware that Your child has provided Us with Personal Data, please contact Us. If We become aware that We have collected Personal Data from anyone under the age of 13 without verification of parental consent, We take steps to remove that information from Our servers.")
    st.write("If We need to rely on consent as a legal basis for processing Your information and Your country requires consent from a parent, We may require Your parent's consent before We collect and use that information.")
    st.title("Links to Other Websites")
    st.write("Our Service may contain links to other websites that are not operated by Us. If You click on a third party link, You will be directed to that third party's site. We strongly advise You to review the Privacy Policy of every site You visit.")
    st.write("We have no control over and assume no responsibility for the content, privacy policies or practices of any third party sites or services.")
    st.title("Changes to this Privacy Policy")
    st.write("We may update Our Privacy Policy from time to time. We will notify You of any changes by posting the new Privacy Policy on this page.")
    st.write("We will let You know via email and/or a prominent notice on Our Service, prior to the change becoming effective and update the 'Last updated' date at the top of this Privacy Policy.")
    st.write("You are advised to review this Privacy Policy periodically for any changes. Changes to this Privacy Policy are effective when they are posted on this page.")
    st.title("Contact Us")
    st.write("If you have any questions about this Privacy Policy, You can contact us:")
    st.write("* By email: egeguvener0808@gmail.com")
    st.text("")
    st.text("")
    constent = st.checkbox('I agree')
    if st.button("I accept privacy policy", type = "primary", use_container_width = True, disabled = True if not constent else False):
        st.rerun()

def leaderboard(c):
    st.header("🏆 Leaderboard", divider="rainbow")

    tab1, tab2, tab3 = st.tabs(["💰 Vault", "👜 Wallet", "🏦 Savings"])

    main_balance_data = c.execute("""
        SELECT username, visible_name, balance FROM users 
        WHERE show_main_balance_on_leaderboard = 1 
        ORDER BY balance DESC
    """).fetchall()

    wallet_balance_data = c.execute("""
        SELECT username, visible_name, wallet FROM users 
        WHERE show_wallet_on_leaderboard = 1 
        ORDER BY wallet DESC
    """).fetchall()

    savings_balance_data = c.execute("""
        SELECT u.username, u.visible_name, s.balance 
        FROM users u JOIN savings s ON u.user_id = s.user_id 
        WHERE u.show_savings_balance_on_leaderboard = 1 
        ORDER BY s.balance DESC
    """).fetchall()

    def format_leaderboard(data):
        return [
            {"Rank": idx + 1, "Name": user[1] if user[1] else user[0], "Balance": f"${numerize(user[2], 2)}"}
            for idx, user in enumerate(data)
        ]

    with tab1:
        st.subheader("💰 Vault Ranking")
        st.table(format_leaderboard(main_balance_data) if main_balance_data else ["No users found."])

    with tab2:
        st.subheader("👜 Wallet Ranking")
        st.table(format_leaderboard(wallet_balance_data) if wallet_balance_data else ["No users found."])

    with tab3:
        st.subheader("🏦 Savings Balance Ranking")
        st.table(format_leaderboard(savings_balance_data) if savings_balance_data else ["No users found."])

@st.dialog("Item Options")
def inventory_item_options(conn, user_id, item_id):
    c = conn.cursor()
    item_number = c.execute("SELECT item_number FROM user_inventory WHERE item_id = ?", (item_id,)).fetchone()[0]
    item_data = c.execute("SELECT name, description, rarity, price, image_url FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchone()
    st.header(f"{item_colors[item_data[2]]}[{item_data[0]}]   **•**   :gray[{item_data[2].upper()}] **•** :gray[#{item_number}]", divider = "rainbow")
    with st.container(border = True):
        c1, c2 = st.columns([1, 2.5])
        c1.image(item_data[4], use_container_width=True)
        c2.write(f":gray[BOUGHT FOR]   $|$   :green[${item_data[3]}]")
        c2.write(f":gray[EFFECT]   $|$   {item_data[1]}")
    c1, c2 = st.columns(2)
    new_price = c1.number_input("a", label_visibility="collapsed", min_value=0, step=200, placeholder="Price")
    if c2.button("**Put on BlackMarket**", use_container_width=True):
        with st.spinner("Processing..."):
            c.execute("INSERT INTO blackmarket_items (item_id, item_number, name, description, rarity, price, image_url, seller_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (item_id, item_number, item_data[0], item_data[1], item_data[2], new_price, item_data[4], user_id))
            time.sleep(3)
        st.success("Item is now for sale on blackmarket!")
        time.sleep(2)
        st.rerun()
    if st.button("**Put Up For Auction (Cost: :green[$100])**", type="primary", use_container_width=True):
        pass

    st.header("GNFT Gifting", divider="rainbow")
    all_users = [user[0] for user in c.execute("SELECT username FROM users WHERE username != ?", (st.session_state.username,)).fetchall()]
    user_to_gift = st.selectbox("Select User", options=all_users)
    receiver_id = c.execute("SELECT user_id FROM users WHERE username = ?", (user_to_gift,)).fetchone()[0]
    if st.button("Send Gift", use_container_width=True):
        with st.spinner("Gifting NFT..."):
            c.execute("DELETE FROM user_inventory WHERE item_id = ?", (item_id,))
            c.execute("INSERT INTO user_inventory (user_id, item_id, item_number) VALUES (?, ?, ?)", (receiver_id, item_id, item_number))
            if item_data[3] == "interest_boost":
                c.execute("UPDATE savings SET interest_rate = interest_rate - ? WHERE user_id = ?", (item_data[4], receiver_id))
                conn.commit()
            if item_data[3] == "attack_boost":
                c.execute("UPDATE users SET attack_level = attack_level - ? WHERE user_id = ?", (item_data[4], receiver_id))
                conn.commit()
            if item_data[3] == "defense_boost":
                c.execute("UPDATE users SET defense_level = defense_level - ? WHERE user_id = ?", (item_data[4], receiver_id))
                conn.commit()
            time.sleep(2.5)
        st.success("Success!")
        time.sleep(1)
        st.rerun()

@st.dialog("Attempt Steal Money")
def steal_dialog(conn, attacker_id, target_id):
    c = conn.cursor()

    attacker = c.execute("SELECT wallet, attack_level, steal_cooldown FROM users WHERE user_id = ?", 
                         (attacker_id,)).fetchone()
    if not attacker:
        st.error("Attacker not found.")
        return

    attacker_wallet, attack_level, steal_cooldown = attacker

    target = c.execute("SELECT username, wallet, defense_level FROM users WHERE user_id = ?", (target_id,)).fetchone()
    if not target:
        st.error("Target user not found.")
        return

    target_username, target_wallet, defense_level = target

    if steal_cooldown:
        last_steal = datetime.datetime.strptime(steal_cooldown, "%Y-%m-%d %H:%M:%S")
        time_diff = (datetime.datetime.now() - last_steal).total_seconds()

        if time_diff < 600:
            st.warning(f"Wait {int(600 - time_diff)} seconds before stealing again!")
            return
    else:
        time_diff = 0

    if target_wallet <= 0:
        st.warning("Target has no money to steal!")
        return

    base_success_rate = 50
    success_rate = base_success_rate + (attack_level * 5) - (defense_level * 5)
    success_rate = max(10, min(success_rate, 90))

    st.write(f"Target: :red[{target_username}]")
    st.write("Target Wallet: :red[???]")
    st.info(f"Success Rate: :green[{success_rate}%]")

    if st.button("💰 Initiate Attack", use_container_width=True):
        
        success = random.randint(1, 100) <= success_rate

        if success:
            stolen_percentage = random.uniform(0.1, 0.3)
            stolen_amount = round(target_wallet * stolen_percentage, 2)  # Steal 10-30% of wallet
            stolen_amount = min(target_wallet, stolen_amount)  # Prevent stealing more than available

            c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (stolen_amount, attacker_id))
            c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (stolen_amount, target_id))
            conn.commit()
            result = "win"
        else:
            lost_percentage = random.uniform(0.05, 0.15)  # Lose 5-15%
            lost_amount = round(attacker_wallet * lost_percentage, 2)
            lost_amount = min(attacker_wallet, lost_amount)  # Prevent negative wallet

            c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (lost_amount, attacker_id))
            c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (lost_amount, target_id))
            conn.commit()
            result = "lost"

        c.execute("UPDATE users SET steal_cooldown = ? WHERE user_id = ?", 
                  (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), attacker_id))
        conn.commit()

        with st.status(f"🔍 Scanning {target_username}'s defenses...", expanded=True) as status:
            time.sleep(1)
            st.write("💠 Preparing attack tools...")
            time.sleep(2)
            st.write("💻 Bypassing Firewall...")
            time.sleep(3)
            st.write("🔓 Exploiting vulnerability...")
            time.sleep(2)
            st.write("🔥 Executing attack...")
            time.sleep(4)
            status.update(state="complete" if result == "win" else "error")

        if result == "win":
            st.success(f"💰 Success! You stole **${numerize(stolen_amount)}** ({numerize(stolen_percentage * 100)}%) from {target_username}!")
        else:
            st.error(f"🚨 You got caught! You lost **${numerize(lost_amount)}** ({numerize(lost_percentage * 100)}%) to {target_username}!")

        time.sleep(3)
        st.rerun()

def steal_view(conn, user_id):
    c = conn.cursor()
    st.header("Heist", divider="rainbow")

    all_users = [user[0] for user in c.execute("SELECT username FROM users WHERE username != ?", (st.session_state.username,)).fetchall()]    
    
    target_username = st.selectbox("Target", options = all_users)

    if st.button("💰 Attempt Steal", type="primary", use_container_width=True):
        if target_username:
            target_id = c.execute("SELECT user_id FROM users WHERE username = ?", (target_username,)).fetchone()[0]
            steal_dialog(conn, user_id, target_id)
        else:
            st.warning("Enter a valid username!")

def buy_item(conn, user_id, item_id):
    c = conn.cursor()

    item_data = c.execute("SELECT name, price, stock, boost_type, boost_value FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchall()[0]
    name, price, stock = item_data[0], item_data[1], item_data[2]
    if not price:
        st.toast("Item not found.")
        
    if stock != 0:
        with st.spinner("Purchasing..."):
            next_item_number = c.execute("""
                SELECT COALESCE(MAX(item_number), 0) + 1 
                FROM user_inventory 
                WHERE item_id = ?
            """, (item_id,)).fetchone()[0]
            c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (price, user_id))
            c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (price,))
            c.execute("INSERT INTO user_inventory (user_id, item_id, item_number) VALUES (?, ?, ?)", (user_id, item_id, next_item_number))
            c.execute("UPDATE marketplace_items SET stock = stock - 1 WHERE item_id = ?", (item_id,))
            conn.commit()

            if item_data[3] == "interest_boost":
                c.execute("UPDATE savings SET interest_rate = interest_rate + ? WHERE user_id = ?", (item_data[4], user_id))
                conn.commit()
            if item_data[3] == "attack_boost":
                c.execute("UPDATE users SET attack_level = attack_level + ? WHERE user_id = ?", (item_data[4], user_id))
                conn.commit()
            if item_data[3] == "defense_boost":
                c.execute("UPDATE users SET defense_level = defense_level + ? WHERE user_id = ?", (item_data[4], user_id))
                conn.commit()

            time.sleep(1.5)
        st.success(f"Item purchased!")
        time.sleep(1)
        st.rerun()
    else:
        st.warning("This item is out of stock.")

def marketplace_view(conn, user_id):
    c = conn.cursor()

    items = c.execute("SELECT item_id, name, description, rarity, price, stock, image_url FROM marketplace_items").fetchall()
    st.header("GNFTs", divider="rainbow")

    if not items:
        st.info("No items available in the marketplace.")
        return

    for item in items:
        image_col, details_col = st.columns([1, 3])

        with image_col:
            st.image(item[6], width=100, use_container_width=True, output_format="PNG")

        with details_col:
            st.write(f"#### **{item_colors[item[3]]}[{item[1]}]**")
            st.write(f":gray[{item[3].upper()}]   •   {item[2]}")
            st.write(f":green[${numerize(item[4], 2)}]  •  :orange[{item[5]} Left]")

            if st.button(f"🔧 Options", key=f"buy_{item[0]}", use_container_width=True):
                item_options(conn, user_id, item[0])

        st.divider()

def inventory_view(conn, user_id):
    c = conn.cursor()
    st.header("Your Inventory", divider="rainbow")
    
    owned_item_ids = [owned_item[0] for owned_item in c.execute("SELECT item_id FROM user_inventory WHERE user_id = ?", (user_id,)).fetchall()]
    if not owned_item_ids:
        st.write("No items in your inventory.")
        return

    st.subheader("Your GNFTs")
    
    for idx, item_id in enumerate(owned_item_ids):
        item_details = c.execute("SELECT name, description, rarity, image_url FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchone()

        if item_details is None:
            st.error(f"Item with ID {item_id} not found in the marketplace.")
            continue

        name, description, rarity, image_url = item_details
        
        item_number = c.execute("SELECT item_number FROM user_inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)).fetchone()[0]
        acquired_at = c.execute("SELECT acquired_at FROM user_inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id)).fetchone()[0]
        
        image_col, details_col = st.columns([1, 3])

        with image_col:
            if image_url:
                st.image(image_url, width=100, use_container_width=True, output_format="PNG")

        with details_col:
            st.write(f"#### **{item_colors[rarity]}[{name}]**")
            st.write(f":gray[#{item_number}]   •   {rarity.upper()}")
            st.write(description)

            if st.button(f"🔧 OPTIONS", key=f"options_{item_id}", use_container_width=True):
                inventory_item_options(conn, user_id, item_id)

            st.caption(f"Acquired: {acquired_at}")
        
        st.divider()

def manage_pending_transfers(conn, receiver_id):
    c = conn.cursor()
    st.header("📥 Pending Transfers", divider = "rainbow")
    pending_transfers = c.execute("""
        SELECT transaction_id, user_id, amount, timestamp
        FROM transactions
        WHERE  receiver_username = (SELECT username FROM users WHERE user_id = ?) AND status = 'pending'
    """, (receiver_id,)).fetchall()
    if st.button("Refresh", use_container_width = True):
        pending_transfers = c.execute("""
        SELECT transaction_id, user_id, amount, timestamp
        FROM transactions
        WHERE  receiver_username = (SELECT username FROM users WHERE user_id = ?) AND status = 'pending'
    """, (receiver_id,)).fetchall()

    if not pending_transfers:
        st.write("No pending transfers.")
        return

    for transaction in pending_transfers:
        transaction_id, sender_id, amount, timestamp = transaction
        sender_username = c.execute("SELECT username FROM users WHERE user_id = ?", (sender_id,)).fetchone()[0]
        tax = (amount / 100) * 0.5
        net = amount - tax

        st.write(f"💸   |   **{sender_username}** wants to transfer :green[${numerize(amount, 2)}]. You will receive :green[${numerize(net, 2)}]. :red[(%0.5 tax.)]")
        c1, c2 = st.columns(2)

        if c1.button(f"Accept", type = "primary", use_container_width = True, key = transaction_id):
            with st.spinner("Accepting Transfer"):
                c.execute("UPDATE transactions SET status = 'accepted' WHERE transaction_id = ?", (transaction_id,))
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (net, receiver_id))
                c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (tax,))
                conn.commit()
                time.sleep(2)
            st.toast("Transfer accepted!")
            time.sleep(2)
            st.rerun()

        if c2.button(f"Decline", use_container_width = True, key = transaction_id + 1):
            with st.spinner("Declining Transfer"):
                c.execute("UPDATE transactions SET status = 'rejected' WHERE transaction_id = ?", (transaction_id,))
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, sender_id))
                conn.commit()
                time.sleep(2)
            st.toast("Transfer declined!")
            time.sleep(2)
            st.rerun()
        
        st.caption(timestamp)

        st.divider()

def main_account_view(conn, user_id):
    c = conn.cursor()

    current_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    st.header("Main Account (Vault)", divider = "rainbow")
    st.subheader(f"Balance -> :green[${numerize(current_balance, 2)}]")
    st.text("")
    st.text("")

    col1, col2 = st.columns(2)
    if col1.button("Wallet -> Vault", type="primary", use_container_width = True):
        deposit_from_wallet_dialog(conn, user_id)
    if col2.button("Vault -> Wallet / Savings", use_container_width = True):
        withdraw_dialog(conn, user_id)
    if st.button("Transfer", use_container_width = True):
        transfer_dialog(conn, user_id)

    st.divider()
    
    deposits, withdrawals, incoming, outgoing = (
        c.execute("SELECT deposits, withdraws, incoming_transfers, outgoing_transfers FROM users WHERE user_id = ?", (user_id,)).fetchone()
    )
    
    total_transactions = deposits + withdrawals + incoming + outgoing
    recent_metrics = recent_transactions_metrics(c, user_id)
   
    st.header("Last 24 Hours", divider = "rainbow")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Deposits (24h)", recent_metrics["Top Ups"]["count"], f"${recent_metrics['Top Ups']['total']:.2f}")
    c2.metric("Withdrawals (24h)", recent_metrics["Withdrawals"]["count"], f"${recent_metrics['Withdrawals']['total']:.2f}")
    c3.metric("Incoming Transfers (24h)", recent_metrics["Incoming Transfers"]["count"], f"${recent_metrics['Incoming Transfers']['total']:.2f}")
    c4.metric("Outgoing Transfers (24h)", recent_metrics["Outgoing Transfers"]["count"], f"${recent_metrics['Outgoing Transfers']['total']:.2f}")
    
    st.text("")
    st.text("")
    st.header("Lifetime Metrics", divider = "rainbow")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Top Ups", deposits)
    c2.metric("Withdrawals", withdrawals)
    c3.metric("Incoming Transfers", incoming)
    c4.metric("Outgoing Transfers", outgoing)
    st.write(f"Total Transactions   |   :green[{total_transactions}]")

def savings_view(conn, user_id):
    c = conn.cursor()
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = 0
    apply_interest_if_due(conn, user_id, check = False)
    
    st.header("Savings Account", divider="rainbow")

    has_savings_account = c.execute("SELECT has_savings_account FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    if not has_savings_account:
        if st.button("Set Up a Savings Account (%0.005 Interest Per Hour) - Boostable", type = "primary", use_container_width = True):
            with st.spinner("Setting up a savings account for you..."):
                c.execute("UPDATE users SET has_savings_account = 1 WHERE user_id = ?", (user_id,))
                c.execute("INSERT INTO savings (user_id, balance, interest_rate, last_interest_applied) VALUES (?, 0, 0.005, ?)", 
                          (user_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                time.sleep(3)
            st.rerun()
    else:
        savings_balance = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]
        st.subheader(f"Savings -> :green[${numerize(savings_balance, 2)}]")
        st.text("")
        st.text("")

        c1, c2 = st.columns(2)
        if c1.button("**Wallet / Vault -> Savings**", type="primary", use_container_width=True):
            deposit_to_savings_dialog(conn, st.session_state.user_id)

        if c2.button("**Savings -> Wallet / Vault**", type="secondary", use_container_width=True):
            withdraw_from_savings_dialog(conn, st.session_state.user_id)
        
        if st.button("Refresh Savings Balance", use_container_width=True):
            apply_interest_if_due(conn, user_id)

    st.text("")
    if has_savings_account:
        interest = c.execute("SELECT interest_rate from savings WHERE user_id = ?", (user_id,)).fetchone()[0]
        with st.container(border=True):
            
            st.write(f":green[%{interest}] simple interest per **hour.**")
        st.caption(":gray[HINT: Some items can boost your interest rate!]")
    st.text("")
    
    st.header("📜 Interest History", divider="rainbow")
    if has_savings_account:
        interest_history = c.execute("""
            SELECT timestamp, interest_amount, new_balance 
            FROM interest_history 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 10
        """, (user_id,)).fetchall()

        if interest_history:
            df = pd.DataFrame(interest_history, columns=["Timestamp", "Interest Earned", "New Balance"])
            df["Timestamp"] = pd.to_datetime(df["Timestamp"])
            st.dataframe(df.set_index("Timestamp"), use_container_width = True)
        else:
            st.info("No interest history available.")
    else:
        st.write("You do not own a savings account.")

def dashboard(conn, user_id):
    c = conn.cursor()
    check_and_update_investments(conn, user_id)

    st.header(f"Welcome, {st.session_state.username}!", divider="rainbow")
    st.subheader("Daily Reward")
    if st.button("🎁     Claim Reward     🎁", use_container_width = True):
        claim_daily_reward(conn, user_id)

    balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    has_savings = c.execute("SELECT has_savings_account FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    if has_savings:
        savings_balance = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]

    for _ in range(4):
        st.write("")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.write("Wallet")
        st.subheader(f":green[${numerize(wallet_balance, 2)}]")

    with c2:
        st.write("Vault")
        st.subheader(f":green[${numerize(balance, 2)}]")

    with c3:
        st.write("Savings")
        if has_savings:
            st.subheader(f":green[${numerize(savings_balance, 2)}]")
        else:
            st.subheader(f":red[Not owned]")

    st.header("", divider="rainbow")
    st.subheader("📜 Recent Transactions")

    transactions = c.execute("""
        SELECT timestamp, type, amount 
        FROM transactions 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 5
    """, (user_id,)).fetchall()

    if transactions:
        df = pd.DataFrame(transactions, columns=["Timestamp", "Type", "Amount"])
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        st.dataframe(df.set_index("Timestamp"), use_container_width = True)
    else:
        st.info("No recent transactions.")

def get_latest_message_time(conn):
    """Fetch the most recent timestamp from the chats table."""
    c = conn.cursor()
    c.execute("SELECT MAX(timestamp) FROM chats")
    return c.fetchone()[0] or "1970-01-01 00:00:00"

def chat_view(conn):
    if "last_chat_time" not in st.session_state:
        st.session_state.last_chat_time = "1970-01-01 00:00:00"

    st_autorefresh(interval=5000, key="chat_autorefresh")

    c = conn.cursor()
    messages = c.execute("""
        SELECT u.username, c.message, c.timestamp 
        FROM chats c 
        JOIN users u ON c.user_id = u.user_id 
        ORDER BY c.timestamp DESC 
        LIMIT 6
    """).fetchall()

    messages.reverse()

    chat_container = st.container()
    with chat_container:
        for username, message, timestamp in messages:
            if username == "egegvner":
                with st.chat_message(name="ai"):
                    st.write(f":orange[[{username}] :gray[[{timestamp.split()[1]}]]] {message}")
            else:
                with st.chat_message(name="user"):
                    st.write(f":gray[[{username}] :gray[[{timestamp.split()[1]}]]] {message}")

    with st.container(border=True):
        new_message = st.text_input("", label_visibility = "collapsed", placeholder = "Your brilliant message goes here...", key = "chat_input")
        if st.button("Send", use_container_width = True):
            if new_message.strip():
                c.execute(
                    "INSERT INTO chats (user_id, message, timestamp) VALUES (?, ?, CURRENT_TIMESTAMP)", 
                    (st.session_state.user_id, new_message.strip())
                )
                conn.commit()

                st.session_state.last_chat_time = get_latest_message_time(conn)
                st.rerun()

def get_latest_message_time(conn):
    c = conn.cursor()
    c.execute("SELECT MAX(timestamp) FROM chats")
    return c.fetchone()[0] or "1970-01-01 00:00:00"

def display_transaction_history(conn, user_id):
    c = conn.cursor()
    st.header("Transaction History", divider = "rainbow")

    sent_transactions, received_transactions = get_transaction_history(conn, user_id)
    transactions = sent_transactions + received_transactions

    if transactions:
        for t in transactions:
            role = t[0]
            t_type = t[1]
            amount = t[2]
            timestamp = t[3]
            status = t[4]
            receiver_username = t[5] if role == "sent" else "N/A"
            from_username = (
                c.execute("SELECT username FROM users WHERE user_id = ?", (t[5],)).fetchone()[0]
                if role == "received" else "N/A"
            )

            if t_type == "Withdraw From Main Account To Wallet":
                st.warning(f"{t_type}", icon="💵")
                st.write(f"Amount   $|$   :red[-${numerize(amount, 2)}]")
                st.text("")
                st.caption(timestamp)

            elif t_type == "Withdraw From Main Account To Savings":
                st.warning(f"{t_type}", icon="💵")
                st.write(f"Amount   |   :red[-${numerize(amount, 2)}]")
                st.text("")
                st.caption(timestamp)

            elif role == "sent" and "transfer to" in t_type.lower():
                st.info(f"{t_type.title()} { receiver_username} $|$ (Status: **{status.capitalize()}**)", icon="💸")
                st.write(f"Amount   $|$   :red[-${numerize(amount, 2)}]")
                st.text("")
                st.caption(timestamp)

            elif role == "received" and "transfer from" in t_type.lower():
                st.info(f"{t_type.title()} {from_username} $|$ (Status: **{status.capitalize()}**)", icon="💸")
                st.write(f"Amount   $|$   :green[+${numerize(amount, 2)}]")
                st.text("")
                st.caption(timestamp)

            elif t_type.lower().startswith("deposit to savings"):
                st.info(f"{t_type.title()}", icon="🏦")
                st.write(f"Amount   $|$   :green[+${numerize(amount, 2)}]")
                st.text("")
                st.caption(timestamp)

            elif t_type.lower().startswith("withdraw to"):
                st.warning(f"{t_type.title()}", icon="🏧")
                st.write(f"Amount   $|$   :red[-${numerize(amount, 2)}]")
                st.text("")
                st.caption(timestamp)

            st.divider()
    else:
        st.info("No transactions found in your history.")

def buy_blackmarket_item(conn, buyer_id, item_id, item_number, seller_id, price):
    c = conn.cursor()
    c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (price, buyer_id))

    c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (price, seller_id))
    item = c.execute("SELECT boost_type, boost_value FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchone()
    boost_type, boost_value = item

    if boost_type == "interest_boost":
        c.execute("UPDATE savings SET interest_rate = interest_rate + ? WHERE user_id = ?", (boost_value, user_id))
        conn.commit()
    if boost_type == "attack_boost":
        c.execute("UPDATE users SET attack_level = attack_level + ? WHERE user_id = ?", (boost_value, user_id))
        conn.commit()
    if boost_type == "defense_boost":
        c.execute("UPDATE users SET defense_level = defense_level + ? WHERE user_id = ?", (boost_value, user_id))
        conn.commit()
                     
    c.execute("INSERT INTO user_inventory (user_id, item_id, item_number, acquired_at) VALUES (?, ?, ?, ?)", 
              (buyer_id, item_id, item_number, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    c.execute("DELETE FROM blackmarket_items WHERE item_id = ?", (item_id,))
    
    conn.commit()

def buy_stock(conn, user_id, stock_id, quantity):
    c = conn.cursor()

    price = c.execute("SELECT price FROM stocks WHERE stock_id = ?", (stock_id,)).fetchone()[0]
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    cost = price * quantity

    if wallet_balance < cost:
        st.toast("Insufficient funds.")
        return
    
    c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (cost, ))
    c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (cost, user_id))

    existing = c.execute("SELECT quantity, avg_buy_price FROM user_stocks WHERE user_id = ? AND stock_id = ?", 
                         (user_id, stock_id)).fetchone()

    if existing:
        old_quantity = existing[0]
        old_avg_price = existing[1]

        new_quantity = old_quantity + quantity
        new_avg_price = ((old_quantity * old_avg_price) + (quantity * price)) / new_quantity

        c.execute("UPDATE user_stocks SET quantity = ?, avg_buy_price = ? WHERE user_id = ? AND stock_id = ?", 
                  (new_quantity, new_avg_price, user_id, stock_id))
    else:
        c.execute("INSERT INTO user_stocks (user_id, stock_id, quantity, avg_buy_price) VALUES (?, ?, ?, ?)", 
                  (user_id, stock_id, quantity, price))

    c.execute("""
        INSERT INTO transactions (transaction_id, user_id, type, amount, stock_id, quantity, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (random.randint(100000000, 999999999), user_id, "Buy Stock", cost, stock_id, quantity))
    c.execute("UPDATE stocks SET stock_amount = stock_amount - ? WHERE stock_id = ?", (quantity, stock_id))
    
    conn.commit()
    st.toast(f"Purchased :blue[{quantity}] shares for :green[${numerize(cost, 2)}]")


def sell_stock(conn, user_id, stock_id, quantity):

    c = conn.cursor()

    price = c.execute("SELECT price FROM stocks WHERE stock_id = ?", (stock_id,)).fetchone()[0]

    user_stock = c.execute("SELECT quantity, avg_buy_price FROM user_stocks WHERE user_id = ? AND stock_id = ?", 
                           (user_id, stock_id)).fetchone()

    new_quantity = user_stock[0] - quantity
    profit = price * quantity
    tax = (profit / 100) * 0.05
    net_profit = profit - tax

    if new_quantity == 0:
        c.execute("DELETE FROM user_stocks WHERE user_id = ? AND stock_id = ?", (user_id, stock_id))
        c.execute("UPDATE stocks SET stock_amount = stock_amount + ? WHERE stock_id = ?", (quantity, stock_id))

    else:
        c.execute("UPDATE user_stocks SET quantity = ? WHERE user_id = ? AND stock_id = ?", 
                  (new_quantity, user_id, stock_id))
        c.execute("UPDATE stocks SET stock_amount = stock_amount + ? WHERE stock_id = ?", (quantity, stock_id))

    c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, stock_id, quantity) VALUES (?, ?, ?, ?, ?, ?)", (random.randint(100000000, 999999999), user_id, "Sell Stock", net_profit, stock_id, quantity))
    c.execute("UPDATE users SET balance = balance - ? WHERE username = 'Government'", (profit,))
    c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (net_profit, user_id))

    conn.commit()
    st.toast(f"Sold :blue[{quantity}] shares for :green[${numerize(net_profit, 2)}]") 

def stocks_view(conn, user_id):
    c = conn.cursor()
    st.header("📈 Stock Market", divider="rainbow")
    
    update_stock_prices(conn)
    st_autorefresh(interval=300000, key="stock_autorefresh")

    stocks = c.execute("SELECT stock_id, name, symbol, price, stock_amount FROM stocks").fetchall()
    
    if "selected_stock" not in st.session_state:
        st.session_state.selected_stock = stocks[0][0]

    if "ti" not in st.session_state:
        st.session_state.ti = 1
    
    if "range" not in st.session_state:
        st.session_state.range = 24

    if "graph_color" not in st.session_state:
        st.session_state.graph_color = (0, 255, 0)

    st.write("Available Stocks:")
    stock_buttons = st.columns(len(stocks))
    for idx, stock in enumerate(stocks):
        stock_id, name, symbol, price, stock_amount = stock
        if stock_buttons[idx].button(f"{symbol}", key=f"stock_btn_{stock_id}", use_container_width = True):
            st.session_state.selected_stock = stock_id
    
    st.divider()

    selected_stock = next(s for s in stocks if s[0] == st.session_state.selected_stock)
    stock_id, name, symbol, price, stock_amount = selected_stock

    now = datetime.datetime.now()
    start_time = now - datetime.timedelta(hours=24)  # Change time period as needed
    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

    history = c.execute("""
        SELECT timestamp, price FROM stock_history 
        WHERE stock_id = ? AND timestamp >= ?
        ORDER BY timestamp ASC
    """, (stock_id, start_time_str)).fetchall()

    history2 = c.execute("""
        SELECT timestamp, price FROM stock_history 
        WHERE stock_id = ?
        ORDER BY timestamp ASC
    """, (stock_id,)).fetchall()

    if len(history) > 1:
        last_price = history[-1][1]
        previous_price = history[-2][1]
        percentage_change = ((last_price - previous_price) / previous_price) * 100
        
        if last_price > previous_price:
            change_color = ":green[+{:.2f}% :gray[(24h)]".format(percentage_change)
            st.session_state.graph_color = (0, 255, 0)

        elif last_price < previous_price:
            change_color = ":red[-{:.2f}% :gray[(24h)]".format(abs(percentage_change))
            st.session_state.graph_color = (255, 0, 0)

        else:
            change_color = ":orange[0.00% :gray[(24h)]"
            st.session_state.graph_color = (255, 255, 0)

    else:
        percentage_change = 0
        change_color = ":orange[0.00%] :gray[(24h)]"

    st.subheader(f"{name} ({symbol})")
    st.header(f":green[${numerize(price, 2)}] \n ##### {change_color}]")
    st.text("")

    c1, c2 = st.columns(2)
    with c1:
        if len(history) > 1:
            df = pd.DataFrame(history, columns=["Timestamp", "Price"])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df.set_index('Timestamp', inplace=True)

            st.line_chart(df, color=st.session_state.graph_color)
        else:
            st.info("Stock history will be available after 60 seconds of stock creation.")

    with c2:
        user_stock = c.execute("SELECT quantity, avg_buy_price FROM user_stocks WHERE user_id = ? AND stock_id = ?", 
                                (user_id, stock_id)).fetchall()

        if user_stock:
            user_quantity = user_stock[0][0] if user_stock[0][0] else 0
            avg_price = user_stock[0][1] if user_stock[0][1] else 0
        else:
            user_quantity = 0
            avg_price = 0

        with st.container(border=True):
            st.write(f"**[HOLDING]** :blue[{numerize(user_quantity, 2)} {symbol}] ~ :green[${numerize(user_quantity * price, 2)}]")
            st.write(f"[AVG. Bought At] :green[${numerize(avg_price, 2)}]")

            st.write(f"[Available] :orange[{numerize(stock_amount, 2)} {symbol}]")                                

        col1, col2 = st.columns(2)
        
        with col1:
            buy_quantity = st.number_input(f"Buy {symbol}", min_value=0.0, step=0.25, key=f"buy_{stock_id}")
            st.write(f"[Cost]  :red[${numerize(buy_quantity * price, 2)}]")
            if st.button(f"Buy {symbol}", key=f"buy_btn_{stock_id}", type="primary", use_container_width=True, 
                        disabled=True if buy_quantity == 0 or stock_amount < buy_quantity else False, help="Not enough stock available in the market" if stock_amount < buy_quantity else "Insufficent balance"):
                with st.spinner("Purchasing..."):
                    time.sleep(3)
                    buy_stock(conn, user_id, stock_id, buy_quantity)
                time.sleep(2.5)
                st.rerun()
                        
        with col2:
            sell_quantity = st.number_input(f"Sell {symbol}", min_value=0.0, max_value=float(user_quantity), step=0.25, key=f"sell_{stock_id}")
            tax = ((sell_quantity * price) / 100) * 0.05
            net_profit = (sell_quantity * price) - tax
            st.write(f"[Profit] :green[${numerize(net_profit)}] | :red[${numerize(tax)}] [Capital Tax]")
            
            if st.button(f"Sell {symbol}", key=f"sell_btn_{stock_id}", use_container_width=True, 
                        disabled=True if sell_quantity == 0 else False):
                with st.spinner("Selling..."):
                    time.sleep(3)
                    sell_stock(conn, user_id, stock_id, sell_quantity)
                time.sleep(2.5)
                st.rerun()

            if st.button(f"Sell MAX", key=f"sell_max_btn_{stock_id}", use_container_width=True, disabled=True if not user_quantity else False):
                with st.spinner("Selling..."):
                    time.sleep(3)
                    sell_stock(conn, user_id, stock_id, user_quantity)
                time.sleep(2.5)
                st.rerun()

    stock_metrics = get_stock_metrics(conn, stock_id)

    st.subheader("Metrics", divider="rainbow")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    col1.metric("24H High", 
                f"${format_currency(stock_metrics['high_24h'])}" if stock_metrics['high_24h'] else "N/A",
                f"{format_currency(stock_metrics['delta_24h_high'])}" if stock_metrics['delta_24h_high'] else None)
    
    col2.metric("24H Low", 
                f"${format_currency(stock_metrics['low_24h'])}" if stock_metrics['low_24h'] else "N/A",
                f"{format_currency(stock_metrics['delta_24h_low'])}" if stock_metrics['delta_24h_low'] else None)
    
    col3.metric("All-Time High", 
                f"${format_currency(stock_metrics['all_time_high'])}" if stock_metrics['all_time_high'] else "N/A",
                f"{format_currency(stock_metrics['delta_all_time_high'])}" if stock_metrics['delta_all_time_high'] else None)
    
    col4.metric("All-Time Low", 
                f"${format_currency(stock_metrics['all_time_low'])}" if stock_metrics['all_time_low'] else "N/A",
                f"{format_currency(stock_metrics['delta_all_time_low'])}" if stock_metrics['delta_all_time_low'] else None)
    
    col5.metric("24H Change", 
                f"{stock_metrics['price_change']:.2f}%", 
                delta_color="inverse")

    st.header(f"Details for {name}", divider="rainbow")
    df = pd.DataFrame(history2, columns=["Timestamp", "Price"])
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df.set_index('Timestamp', inplace=True)
    df_resampled = df.resample(f"{st.session_state.ti}T").mean()  
    st.line_chart(df_resampled, color = st.session_state.graph_color)
    c1, c2 = st.columns(2)
    sample_rate = c1.slider("Sample Rate (Lower = More Lag)", min_value = 1, max_value = 100, step = 1)
    if c1.button("Set Resampling", use_container_width=True):
        st.session_state.t = sample_rate
        st.rerun() 

    with c2.popover("Graph Color", use_container_width = True):
        r = st.slider(":red[Red]", min_value = 0, max_value = 255, step = 1)
        g = st.slider(":green[Green]", min_value = 0, max_value = 255, step = 1)
        b = st.slider(":blue[Blue]", min_value = 0, max_value = 255, step = 1)
        if st.button("Apply Color", use_container_width = True):
            st.session_state.graph_color2 = (r, g, b)
            st.rerun()
        if c2.button("Price Prediction", type = "primary", use_container_width = True):
            st.toast("Coming Soon")
        if c2.button("Don't Click Here", type = "primary", use_container_width = True):
            st.toast("Congrats! You have clicked the button!")
    
    st.text("")
    st.text("")
    st.text("")

    leaderboard_data = []
    selected_stock_id = st.session_state.selected_stock  # Get the currently selected stock's ID
    
    stockholders = c.execute("""
        SELECT u.username, SUM(us.quantity) AS total_quantity
        FROM user_stocks us
        JOIN users u ON us.user_id = u.user_id
        WHERE us.stock_id = ?
        GROUP BY us.user_id
        ORDER BY total_quantity DESC
    """, (selected_stock_id,)).fetchall()
    
    for stockholder in stockholders:
        username = stockholder[0]
        total_quantity = stockholder[1]
        leaderboard_data.append([username, total_quantity])
    
    st.subheader("🏆 Stockholder Leaderboard", divider="rainbow")
    if leaderboard_data:
        leaderboard_df = pd.DataFrame(leaderboard_data, columns=["Stockholder", "Shares Held"])
        st.dataframe(leaderboard_df, use_container_width=True)
    else:
        st.info("No stockholder data available yet.")

def portfolio_view(conn, user_id):
    c = conn.cursor()
    st_autorefresh(interval=5000, key="p")

    if "portofolio_value" not in st.session_state:
        st.session_state.portofolio_value = 0

    st.header("📊 My Portfolio", divider="rainbow")

    user_stocks = c.execute("""
        SELECT us.stock_id, s.name, s.symbol, us.quantity, us.avg_buy_price, s.price 
        FROM user_stocks us
        JOIN stocks s ON us.stock_id = s.stock_id
        WHERE us.user_id = ? AND us.quantity > 0
    """, (user_id,)).fetchall()

    if not user_stocks:
        st.info("You don't own any stocks yet. Start investing now! 🚀")
        return
    
    st.text("")
    st.text("")

    for stock_id, name, symbol, quantity, avg_buy_price, current_price in user_stocks:
        stock_worth = quantity * current_price
        st.session_state.portofolio_value = stock_worth
        profit_loss = (current_price - avg_buy_price) * quantity
        profit_loss_percent = ((current_price - avg_buy_price) / avg_buy_price) * 100 if avg_buy_price > 0 else 0

        st.subheader(f"{name} ({symbol})")

        with st.container(border=True):  
            c1, c2, c3, c4, c5 = st.columns([2,2,2,2,3])

            with c1:
                st.write("Holding")
                st.write(f":blue[{numerize(quantity)}]")

            with c2:
                st.write("AVG Buy P.")
                st.write(f":red[{numerize(avg_buy_price)}]")

            with c3:
                st.write("Current P.")
                st.write(f":green[{numerize(current_price)}]")

            with c4:
                st.write("Total Worth")
                st.write(f":green[{numerize(stock_worth)}]")

            with c5:
                st.write("Gain / Loss")
                if profit_loss < 0:
                    st.subheader(f":red[{numerize(profit_loss)}]")
                    st.caption(f":red[-{numerize(profit_loss_percent)}%]")
                else:
                    st.subheader(f":green[{numerize(profit_loss)}]")
                    st.caption(f":green[+{numerize(profit_loss_percent)}%]")
            
        if st.button("Quick Sell (ALL)", use_container_width = True, key = stock_id):
            with st.spinner("Processing..."):
                sell_stock(conn, user_id, stock_id, quantity)
                time.sleep(2)
    
        st.divider()

def blackmarket_view(conn, user_id):
    c = conn.cursor()
    st.header("🖤 Black Market", divider="rainbow")
    
    blackmarket_items = c.execute("""
        SELECT item_id, item_number, name, description, rarity, price, image_url, seller_id 
        FROM blackmarket_items
    """).fetchall()
    
    if not blackmarket_items:
        st.info("The Black Market is currently empty. Check back later!")
        return
    
    for item in blackmarket_items:
        item_id, item_number, name, description, rarity, price, image_url, seller_id = item

        seller_username = c.execute("SELECT username FROM users WHERE user_id = ?", (seller_id,)).fetchone()[0]
        wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

        image_col, details_col = st.columns([1, 3])
        
        with image_col:
            st.image(image_url, width=100, use_container_width=True, output_format="PNG")
        
        with details_col:
            st.write(f"#### **{item_colors[rarity]}[{name}]** • :gray[#{item_number}]")
            st.write(f":gray[{rarity.upper()}]   •   {description}")
            st.write(f":green[${numerize(price)}]  •  By: :blue[@{seller_username}]")
            
            if st.button(f"Buy for :green[${numerize(price)}]", key=f"buy_{item_id}", use_container_width=True, 
                         disabled=True if wallet_balance < price else False):
                with st.spinner(f"Purchasing {name}..."):
                    buy_blackmarket_item(conn, user_id, item_id, item_number, seller_id, price)
                    time.sleep(2)
                    st.success(f"🎉 Successfully purchased **{name}**!")
                    st.rerun()

        st.divider()


def borrow_money(conn, user_id, amount, interest_rate):
    c = conn.cursor()

    current_loan = c.execute("SELECT loan FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    
    if current_loan > 0:
        st.toast("❌ You must repay your existing loan first!")
        return

    new_loan = round(amount * (1 + interest_rate), 2)
    due_date = (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")  # Due in 7 days

    c.execute("UPDATE users SET loan = ?, loan_due_date = ?, balance = balance + ? WHERE user_id = ?", 
              (new_loan, due_date, amount, user_id))
    conn.commit()

    st.toast(f"✅ Borrowed ${amount:.2f}. Due Date: {due_date}. You owe ${new_loan:.2f}.")
    st.rerun()


def borrow_money(conn, user_id, amount, interest_rate):
    c = conn.cursor()

    current_loan = c.execute("SELECT loan FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    
    if current_loan > 0:
        st.toast("❌ You must repay your existing loan first!")
        return

    new_loan = round(amount * (1 + interest_rate), 2)
    due_date = (datetime.date.today() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")  # Due in 7 days

    c.execute("UPDATE users SET balance = balance - ? WHERE username = 'Government'", (amount,))
    c.execute("UPDATE users SET loan = ?, loan_due_date = ?, balance = balance + ? WHERE user_id = ?", 
              (new_loan, due_date, amount, user_id))
    conn.commit()

    st.toast(f"✅ Borrowed ${amount:.2f}. Due Date: {due_date}. You owe ${new_loan:.2f}.")
    time.sleep(2.5)
    
def repay_loan(conn, user_id, amount):
    c = conn.cursor()
    
    user_data = c.execute("SELECT loan, balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
    loan, balance = user_data if user_data else (0, 0)
    
    if loan <= 0:
        st.toast("✅ You have no outstanding loans!")
        return

    if balance < amount:
        st.toast("❌ Insufficient balance to repay!")
        return

    new_loan = max(0, loan - amount)
    new_balance = balance - amount

    c.execute("UPDATE users SET balance = balance + ? WHERE username = 'Government'", (amount,))
    c.execute("UPDATE users SET loan = ?, balance = ? WHERE user_id = ?", (new_loan, new_balance, user_id))
    conn.commit()
    
    st.toast(f"✅ Loan repaid. Remaining debt: ${numerize(new_loan)}.")
    time.sleep(2.5)
    st.session_state.repay = 0.0

def bank_view(conn, user_id):
    st.header("🏦 The Bank", divider="rainbow")

    update_inflation(conn)
    check_and_apply_loan_penalty(conn, user_id)

    c = conn.cursor()

    if "repay" not in st.session_state:
        st.session_state.repay = 0.0

    if "amt" not in st.session_state:
        st.session_state.amt = 0.0
    
    df = get_inflation_history(c)
    gov_funds = c.execute("SELECT balance FROM users WHERE username = 'Government'").fetchone()[0]
    inflation_rate = c.execute("SELECT inflation_rate FROM inflation_history ORDER BY date DESC LIMIT 1").fetchone()
    inflation_rate = inflation_rate[0] if inflation_rate else 0.01  # Default 1% interest

    t1, t2 = st.tabs(["Economy", "Loans & Repayments"])
    with t1:
        st.header("Total Government Funds", divider="rainbow")
        c1, c2, c3 = st.columns([2, 1, 2])
        c2.title(f"**:green[${numerize(gov_funds)}]**")
        st.caption(f":green[${format_currency(gov_funds)}]")
        st.divider()
        st.subheader(f"Inflation: :red[{numerize(inflation_rate * -100)}%]")

        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            df.set_index("Date", inplace=True)
            st.line_chart(df["Inflation Rate"], color=(255, 0, 0))
        else:
            st.info("No inflation data available yet.")

    with t2:
        with st.container(border=True):
            user_data = c.execute("SELECT balance, loan, loan_due_date, loan_penalty FROM users WHERE user_id = ?", (user_id,)).fetchone()
            balance, loan, due_date, penalty = user_data if user_data else (0, None, None, 0)

            interest_rate = max(0.01, inflation_rate + 0.02)

            st.write(f"📊 **[Inflation]** :red[{numerize(inflation_rate * -100)}%]")
            st.write(f"💳 **[Loan Interest Rate]** :red[{numerize(interest_rate * 100)}% / day]")
            st.write(f"💰 **[Balance]** :green[${numerize(balance)}]")
            st.write(f"💳 **[Loan Debt]** :red[${numerize(loan)}]")

            if loan > 0 and due_date:
                due_date_obj = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()
                today = datetime.date.today()
                
                if today > due_date_obj:
                    st.error(f"⚠ **Your loan is overdue!** You now owe **${format_currency(loan)}** with a total penalty of **${format_currency(penalty)}**.")
                else:
                    st.info(f"📅 [You Have an Active Loan!] **Due:** {due_date}")
        
        st.session_state.amt = balance
        st.divider()
        st.warning(f"[Max Borrow] :green[${format_currency(st.session_state.amt)} || {numerize(st.session_state.amt)}]")
        st.subheader("Borrow Loan")
        borrow_amount = st.number_input("A", label_visibility="collapsed", min_value=100.0, max_value=float(st.session_state.amt), step=100.0)
        if st.button("Borrow", use_container_width=True):
            with st.spinner("Processing borrow"):
                time.sleep(3)
                borrow_money(conn, user_id, borrow_amount, interest_rate)
                st.session_state.amt = 0.0
                st.rerun()

        st.subheader("Repay Loan")
        c1, c2 = st.columns(2)
        
        st.session_state.repay = c1.number_input("d", label_visibility="collapsed", min_value=0.0, value=float(st.session_state.repay), step=10.0)
        if c2.button("Max", use_container_width=True):
            st.session_state.repay = loan
            st.rerun()

        if st.button("Repay", use_container_width=True):
            with st.spinner("Processing loan..."):
                time.sleep(3)
                repay_loan(conn, user_id, st.session_state.repay)
                st.rerun()
                
def investments_view(conn, user_id):
    st.header("📈 Investments", divider="rainbow")
    c = conn.cursor()

    check_and_update_investments(conn, user_id)
    balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
   
    if "s_c" not in st.session_state:
        st.session_state.s_c = None

    if "balance" not in st.session_state:
        st.session_state.balance = balance

    if "invest_value" not in st.session_state:
        st.session_state.invest_value = 0

    st.subheader(f"💰 Wallet: **:green[${numerize(balance)}]**")

    companies = c.execute("SELECT company_id, company_name, risk_level FROM investment_companies").fetchall()

    if not companies:
        st.info("No investment opportunities are currently available.")
        return

    st.write("Available Companies")
    columns = st.columns(len(companies))
    for idx, (company_id, company_name, risk_level) in enumerate(companies):
        if columns[idx].button(company_name, use_container_width=True):
            st.session_state.s_c = {"id": company_id, "name": company_name, "risk_level": risk_level}

    if not st.session_state.s_c:
        st.info("Click on a company to view investment options.")
        return

    selected_company = st.session_state.s_c  # Safely use the selected company

    st.divider()
    st.subheader(f"💼 {selected_company['name']}", divider="rainbow")
    st.subheader(f"**Risk:** :red[{numerize(selected_company['risk_level'] * 100)}%]")

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("%25", use_container_width = True):
        st.session_state.invest_value = (balance / 100) * 25
    if c2.button("%50", use_container_width = True):
        st.session_state.invest_value = (balance / 100) * 50
    if c3.button("%75", use_container_width = True):
        st.session_state.invest_value = (balance / 100) * 75
    if c4.button("%100", use_container_width = True):
        st.session_state.invest_value = balance 
    
    investment_amount = st.number_input(
        "Investment Amount",
        min_value=0.0,
        max_value=st.session_state.balance,
        step=1.0,
        value=float(st.session_state.invest_value),  # Set default value to the smaller of balance or 1.0
        key=f"investment_{selected_company['id']}",
    )

    if st.button(f"**Invest :green[${numerize(investment_amount)}] Now**", use_container_width=True, type="primary", disabled=True if investment_amount == 0 else False):
        active_investments_count = c.execute("""
        SELECT COUNT(*) FROM investments WHERE user_id = ? AND status = 'pending'
        """, (user_id,)).fetchone()[0]

        if active_investments_count >= 10:
            st.error("❌ You already have 10 active investments. Complete or wait for them to finish before starting a new one.")
        elif investment_amount > balance:
            st.error("Insufficient balance!")
        else:
            with st.spinner("Processing Investment"):
                return_rate = calculate_investment_return(st.session_state.s_c['risk_level'], investment_amount)
            
                duration_hours = random.randint(1, 24)  # Convert 7 days to hours
                start_date = datetime.datetime.now()
                end_date = start_date + datetime.timedelta(hours=duration_hours)

                c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (investment_amount, user_id))
                c.execute("""
                    INSERT INTO investments (user_id, company_name, amount, risk_level, return_rate, start_date, end_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    st.session_state.s_c['name'],
                    investment_amount,
                    st.session_state.s_c['risk_level'],
                    return_rate,
                    start_date.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date.strftime("%Y-%m-%d %H:%M:%S"),
                ))
                conn.commit()
                time.sleep(4)
            st.toast(f"Investment of :green[${numerize(investment_amount)}] in {selected_company['name']} has initiated! Ends on {end_date}.")
            time.sleep(2)
            st.session_state.balance = balance - investment_amount
            st.rerun()

    st.divider()
    st.subheader("📊 Active Investments", divider="rainbow")
    active_investments = c.execute("""
        SELECT company_name, amount, risk_level, start_date, end_date
        FROM investments WHERE user_id = ? AND status = 'pending'
    """, (user_id,)).fetchall()

    if active_investments:
        for company, amount, risk, start, end in active_investments:
            with st.container(border=True):
                st.write(f"**{company}** - :gray[[Invested]] :green[${numerize(amount)}] $|$ :gray[[Risk]] :red[{float(risk) * 100}%] $|$ :gray[[Ends]] :blue[{end}]")
    else:
        st.info("No active investments!")

    st.divider()
    st.subheader("✅ Completed Investments", divider="rainbow")
    completed_investments = c.execute("""
        SELECT company_name, amount, return_rate, status
        FROM investments WHERE user_id = ? AND status != 'pending'
    """, (user_id,)).fetchall()

    if completed_investments:
        for company, amount, rate, status in completed_investments:
            outcome = "Profit" if rate > 0 else "Loss"
            st.write(f"**{company}** - {outcome}: :green[${numerize(rate)}] ({status.title()})")
    else:
        st.info("No completed investments yet.")

def admin_panel(conn):
    c = conn.cursor()
    st.header("Marketplace Items", divider = "rainbow")

    with st.expander("New Item Creation"):
        with st.form(key= "q"):
            st.subheader("New Item Creation")
            item_id = st.text_input("Item ID", value = f"{random.randint(100000000, 999999999)}", disabled = True, help = "Item ID must be unique")
            name = st.text_input("A", label_visibility = "collapsed", placeholder = "Item  Name")
            description = st.text_input("A", label_visibility = "collapsed", placeholder = "Description")
            rarity = st.selectbox("A", label_visibility = "collapsed", placeholder = "Description", options = ["Common", "Uncommon", "Rare", "Epic", "Ultimate"])         
            price = st.text_input("A", label_visibility = "collapsed", placeholder = "Price")
            stock = st.text_input("A", label_visibility = "collapsed", placeholder = "Stock")
            boost_type = st.text_input("A", label_visibility = "collapsed", placeholder = "Boost Type")
            boost_value = st.text_input("A", label_visibility = "collapsed", placeholder = "Boost Value")
            img = st.text_input("A", label_visibility = "collapsed", placeholder = "Image Path (LOCAL ONLY)")
      
            st.divider()
            
            if st.form_submit_button("Add Item", use_container_width = True):
                existing_item_ids = c.execute("SELECT item_id FROM marketplace_items").fetchall()
                if item_id not in existing_item_ids:
                    with st.spinner("Creating item..."):
                        c.execute("INSERT INTO marketplace_items (item_id, name, description, rarity, price, stock, boost_type, boost_value, image_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (item_id, name, description, rarity, price, stock, boost_type, boost_value, img))
                        conn.commit()
                    st.rerun()
                else:
                    st.error("Duplicate item_id")

    st.header("Manage Items", divider = "rainbow")
    with st.spinner("Loading marketplace items..."):
        item_data = c.execute("SELECT item_id, name, description, rarity, price, stock, boost_type, boost_value, image_url FROM marketplace_items").fetchall()
   
    df = pd.DataFrame(item_data, columns = ["Item ID", "Item Name", "Description", "Rarity", "Price", "Stock", "Boost Type", "Boost Value", "Image URL"])
    edited_df = st.data_editor(df, key = "item_table", num_rows = "fixed", use_container_width = True, hide_index = True)
    if st.button("Update Items", use_container_width = True):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE marketplace_items SET name = ?, description = ?, rarity = ?, price = ?, stock = ?, boost_type = ?, boost_value = ?, image_url = ? WHERE item_id = ?", (row["Item Name"], row["Description"], row["Rarity"], row["Price"], row["Stock"], row["Boost Type"], row["Boost Value"], row["Image URL"], row["Item ID"]))
        conn.commit()
        st.rerun()

    item_id_to_delete = st.number_input("Enter Item ID to Delete", min_value = 0, step = 1)
    if st.button("Delete Item", use_container_width = True):
        with st.spinner("Processing..."):
            c.execute("DELETE FROM marketplace_items WHERE item_id = ?", (item_id_to_delete,))
        conn.commit()
        st.rerun()

    st.divider()
    st.header("Blackmarket Items", divider = "rainbow")
    st.text("")
    with st.spinner("Loading Blackmarket Data"):
        blackmarket_data = c.execute("SELECT item_id, item_number, name, description, rarity, price, image_url, seller_id FROM blackmarket_items").fetchall()
    df = pd.DataFrame(blackmarket_data, columns = ["Item ID", "Item Number", "Name", "Description", "Rarity", "Price", "Image", "Seller ID"])
    edited_df = st.data_editor(df, key = "bm_items", num_rows = "fixed", use_container_width = True, hide_index = False)

    for _ in range(4):
        st.text("")

    if st.button("Update Blackmarket", use_container_width = True, type = "secondary"):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE blackmarket SET username = ?, level = ?, visible_name = ?, password = ?, balance = ?, wallet = ?, has_savings_account = ?, suspension = ?, deposits = ?, withdraws = ?, incoming_transfers = ?, outgoing_transfers = ?, total_transactions = ?, last_transaction_time = ?, email = ?, last_daily_reward_claimed = ?, login_streak = ? WHERE user_id = ?", (row["Username"], row["Level"], row["Visible Name"], row["Pass"], row["Balance"], row["Wallet"], row["Has Savings Account"], row["Suspension"], row["Deposits"], row["Withdraws"], row["Transfers Received"], row["Transfers Sent"], row["Total Transactions"], row["Last Transaction Time"], row["Email"], row["Last Daily Reward Claimed"], row["Login Streak"], row["User ID"]))
        conn.commit()
        st.rerun()

    bm_id_to_delete = st.number_input("Enter BM Item ID to Delete", min_value = 0, step = 1)
    if st.button("Delete BM Item", use_container_width = True):
        with st.spinner("Processing..."):
            c.execute("DELETE FROM blackmarket_items WHERE item_id = ?", (bm_id_to_delete,))
        conn.commit()
        st.rerun()

    st.header("Stocks", divider = "rainbow")

    with st.expander("New Stock Creation"):
        with st.form(key =  "Stocks"):
            st.subheader("New Stock Creation")
            stock_id = st.text_input("Stock ID", value = f"{random.randint(100000000, 999999999)}", disabled = True, help = "Item ID must be unique")
            stock_name = st.text_input("Ab", label_visibility = "collapsed", placeholder = "Stock  Name")
            stock_symbol = st.text_input("Ab", label_visibility = "collapsed", placeholder = "Symbol")
            starting_price = st.text_input("Ab", label_visibility = "collapsed", placeholder = "Starting Price")
            stock_amount = st.text_input("Ab", label_visibility = "collapsed", placeholder = "Stock Amount")
            change_rate = st.text_input("Ab", label_visibility = "collapsed", placeholder = "Change Rate (i.e 0.5 means ±0.5% in each  update)")

            st.divider()
            
            if st.form_submit_button("Add to QubitTrades™", use_container_width = True):
                existing_stock_ids = c.execute("SELECT stock_id FROM stocks").fetchall()
                if item_id not in existing_stock_ids:
                    c.execute("INSERT INTO stocks (stock_id, name, symbol, starting_price, price, stock_amount, change_rate) VALUES (?, ?, ?, ?, ?, ?, ?)", (stock_id, stock_name, stock_symbol, starting_price, starting_price, stock_amount, change_rate))
                    conn.commit()
                    st.rerun()
                else:
                    st.error("Duplicate item_id")

    st.header("Manage Stocks", divider = "rainbow")
    with st.spinner("Loading QubitTrades™..."):
        stock_data = c.execute("SELECT stock_id, name, symbol, starting_price, price, stock_amount, change_rate FROM stocks").fetchall()
   
    df = pd.DataFrame(stock_data, columns = ["Stock ID", "Stock Name", "Symbol", "Starting Price", "Current Price", "Stock Amount", "Change Rate"])
    edited_df = st.data_editor(df, key = "stock_table", num_rows = "fixed", use_container_width = True, hide_index = True)
    if st.button("Update Stocks", use_container_width = True):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE stocks SET name = ?, symbol = ?, price = ?, stock_amount = ?, change_rate = ? WHERE stock_id = ?", (row["Stock Name"], row["Symbol"], row["Current Price"], row["Stock Amount"], row["Change Rate"], row["Stock ID"]))
        conn.commit()
        st.rerun()

    stock_id_to_delete = st.number_input("Enter Stock ID to Delete", min_value = 0, step = 1)
    if st.button("Delete Stock", use_container_width = True):
        with st.spinner("Processing..."):
            c.execute("DELETE FROM stocks WHERE stock_id = ?", (stock_id_to_delete,))
        conn.commit()
        st.rerun()
        
    st.header("Investment Companies", divider = "rainbow")

    with st.expander("New Company Creation"):
        with st.form(key =  "Company"):
            st.subheader("New Company Creation")
            comp_id = st.text_input("Company ID", value = f"{random.randint(100000000, 999999999)}", disabled = True, help = "Item ID must be unique")
            comp_name = st.text_input("Ab", label_visibility = "collapsed", placeholder = "Company Name")
            risk_level = st.text_input("Ab", label_visibility = "collapsed", placeholder = "Risk Level (0.5 means 50%)")

            st.divider()
            
            if st.form_submit_button("Add to Investronix™", use_container_width = True):
                existing_company_ids = c.execute("SELECT company_id FROM investment_companies").fetchall()
                if item_id not in existing_company_ids:
                    c.execute("INSERT INTO investment_companies (company_id, company_name, risk_level) VALUES (?, ?, ?)", (comp_id, comp_name, risk_level))
                    conn.commit()
                    st.rerun()
                else:
                    st.error("Duplicate item_id")

    st.header("Manage Companies", divider = "rainbow")
    with st.spinner("Loading Investronix™..."):
        company_data = c.execute("SELECT company_id, company_name, risk_level FROM investment_companies").fetchall()
    df = pd.DataFrame(company_data, columns = ["Company ID", "Name", "Risk Level"])
    edited_df = st.data_editor(df, key = "company_table", num_rows = "fixed", use_container_width = True, hide_index = True)
    if st.button("Update Companies", use_container_width = True):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE investment_companies SET company_name = ?, risk_level = ? WHERE company_id = ?", (row["Name"], row["Risk Level"], row["Company ID"]))
        conn.commit()
        st.rerun()

    company_id_to_delete = st.number_input("Enter Company ID to Delete", min_value = 0, step = 1)
    if st.button("Delete Company", use_container_width = True):
        with st.spinner("Processing..."):
            c.execute("DELETE FROM investment_companies WHERE company_id = ?", (company_id_to_delete,))
        conn.commit()
        st.rerun()

    st.divider()
    st.header("Manage User Investments", divider = "rainbow")
    st.text("")

    user = st.selectbox("Select User", [u[0] for u in c.execute("SELECT username FROM users").fetchall()])
    if user:
        user_id = c.execute("SELECT user_id FROM users WHERE username = ?", (user,)).fetchone()[0]
        investments = c.execute("SELECT investment_id, user_id, company_name, amount, risk_level, return_rate, start_date, end_date, status FROM investments WHERE user_id = ? ORDER BY start_date DESC", (user_id,)).fetchall()

        if investments:
            df = pd.DataFrame(investments, columns = ["Investment ID", "User ID", "Company Name", "Amount", "Risk Level", "Return Rate", "Start Date", "End Date", "Status"])
            edited_df = st.data_editor(df, key = "investments_table", num_rows = "fixed", use_container_width = True, hide_index = False)
            
            if st.button("Update Investments", use_container_width = True):
                for _, row in edited_df.iterrows():
                    c.execute("""
                        UPDATE OR IGNORE investments 
                        SET company_name = ?, amount = ?, risk_level = ?,  return_rate = ?, start_date = ?, end_date = ?, status = ?
                        WHERE investment_id = ?
                    """, (row["Company Name"], row["Amount"], row["Risk Level"], row["Return Rate"], row["Start Date"], row["End Date"], row["Status"], row["Investment ID"]))
                conn.commit()
                st.rerun()
            
            st.text("")
            investment_id_to_delete = st.number_input("Enter Investment ID to Delete", min_value=0, step=1)
            if st.button("Delete Investment", use_container_width = True):
                with st.spinner("Processing..."):
                    c.execute("DELETE FROM investments WHERE investment_id = ?", (investment_id_to_delete,))
                conn.commit()
                st.rerun()

        else:
            st.write(f"No investments found for {user}.")
    
    st.header("User Removal", divider = "rainbow")
    
    users = c.execute("SELECT username FROM users").fetchall()
    if not users:
        st.warning("No users found in the database.")
        return
    
    temp_user = st.selectbox(label = "Select user", options=[user[0] for user in users])
    
    temp_user_id = c.execute("SELECT user_id FROM users WHERE username = ?", (temp_user,)).fetchone()
    
    if st.button(f"Delete {temp_user}", type="secondary", use_container_width = True):
        if temp_user_id:
            c.execute("DELETE FROM users WHERE username = ?", (temp_user,))
            c.execute("DELETE FROM transactions WHERE user_id = ?", (temp_user_id[0],))
            c.execute("DELETE FROM user_inventory WHERE user_id = ?", (temp_user_id[0],))
            c.execute("DELETE FROM savings WHERE user_id = ?", (temp_user_id[0],))
            conn.commit()
            
            st.success(f"User {temp_user.capitalize()} and their associated data have been deleted.")
            time.sleep(2)
            st.rerun()
        else:
            st.error(f"User {temp_user.capitalize()} not found in the database!")

    st.divider()
    st.header("Manage User Transactions", divider = "rainbow")
    st.text("")

    user = st.selectbox("Select User", [u[0] for u in c.execute("SELECT username FROM users").fetchall()], key="inv")
    if user:
        user_id = c.execute("SELECT user_id FROM users WHERE username = ?", (user,)).fetchone()[0]
        transactions = c.execute("SELECT transaction_id, type, amount, receiver_username, status, stock_id, quantity, timestamp FROM transactions WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)).fetchall()

        if transactions:
            df = pd.DataFrame(transactions, columns = ["Transaction ID", "Type", "Amount", "To Username", "Status", "Stock ID", "Quantity", "Timestamp"])
            edited_df = st.data_editor(df, key = "transaction_table", num_rows = "fixed", use_container_width = True, hide_index = False)
            
            if st.button("Update Transaction(s)", use_container_width = True):
                for _, row in edited_df.iterrows():
                    c.execute("""
                        UPDATE OR IGNORE transactions 
                        SET type = ?, amount = ?, balance = ?,  receiver_username = ?, status = ?, stock_id = ?, quantity = ?
                        WHERE transaction_id = ?
                    """, (row["Type"], row["Amount"], row["Balance"], row["To Username"], row["Status"], row["Stock ID"], row["Quantity"], row["Transaction ID"]))
                conn.commit()
                st.success("Transactions updated successfully.")
                st.rerun()
            
            st.text("")
            transaction_id_to_delete = st.number_input("Enter Transaction ID to Delete", min_value=0, step=1)
            if st.button("Delete Transaction", use_container_width = True):
                with st.spinner("Processing..."):
                    c.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id_to_delete,))
                conn.commit()
                st.rerun()

        else:
            st.write(f"No transactions found for {user}.")

    st.divider()
    st.header("Users", divider = "rainbow")
    st.text("")
    st.write(":red[Editing data from the dataframes below without proper permission will trigger a legal punishment by law.]")
    with st.spinner("Loading User Data"):
        userData = c.execute("SELECT user_id, username, level, visible_name, password, balance, wallet, has_savings_account, suspension, deposits, withdraws, incoming_transfers, outgoing_transfers, total_transactions, last_transaction_time, email, last_daily_reward_claimed, login_streak FROM users").fetchall()
    df = pd.DataFrame(userData, columns = ["User ID", "Username", "Level", "Visible Name", "Pass", "Balance", "Wallet", "Has Savings Account", "Suspension", "Deposits", "Withdraws", "Transfers Received", "Transfers Sent", "Total Transactions", "Last Transaction Time", "Email", "Last Daily Reward Claimed", "Login Streak"])
    edited_df = st.data_editor(df, key = "users_table", num_rows = "fixed", use_container_width = True, hide_index = False)

    for _ in range(4):
        st.text("")

    if st.button("Update Data", use_container_width = True, type = "secondary"):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE users SET username = ?, level = ?, visible_name = ?, password = ?, balance = ?, wallet = ?, has_savings_account = ?, suspension = ?, deposits = ?, withdraws = ?, incoming_transfers = ?, outgoing_transfers = ?, total_transactions = ?, last_transaction_time = ?, email = ?, last_daily_reward_claimed = ?, login_streak = ? WHERE user_id = ?", (row["Username"], row["Level"], row["Visible Name"], row["Pass"], row["Balance"], row["Wallet"], row["Has Savings Account"], row["Suspension"], row["Deposits"], row["Withdraws"], row["Transfers Received"], row["Transfers Sent"], row["Total Transactions"], row["Last Transaction Time"], row["Email"], row["Last Daily Reward Claimed"], row["Login Streak"], row["User ID"]))
        conn.commit()
        st.rerun()

    st.header("Savings Data", divider = "rainbow")
    with st.spinner("Loading User Data"):
        savings_data = c.execute("SELECT user_id, balance, interest_rate, last_interest_applied FROM savings").fetchall()
    df = pd.DataFrame(savings_data, columns = ["User ID", "Balance", "Interest Rate", "Last Interest Applied"])
    edited_df = st.data_editor(df, key = "savings_table", num_rows = "fixed", use_container_width = True, hide_index = False)

    for _ in range(4):
        st.text("")

    if st.button("Update Savings Data", use_container_width = True, type = "secondary"):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE savings SET balance = ?, interest_rate = ?, last_interest_applied = ? WHERE user_id = ?", (row["Balance"], row["Interest Rate"], row["Last Interest Applied"], row["User ID"]))
        conn.commit()
        st.rerun()

    temp_user_id_to_delete_savings = st.number_input("Enter User ID to Delete Savings", min_value = 0)
    if st.button("Delete Savings Account", use_container_width = True):
        c.execute("DELETE FROM savings WHERE user_id = ?", (temp_user_id_to_delete_savings,))
        c.execute("UPDATE users SET has_savings_account = 0 WHERE user_id = ?", (temp_user_id_to_delete_savings,))
        conn.commit()
        st.rerun()

    user = st.selectbox("Select User", [u[0] for u in c.execute("SELECT username FROM users").fetchall()], key="inv2")
    if user:
        user_id = c.execute("SELECT user_id FROM users WHERE username = ?", (user,)).fetchone()[0]
        user_items = c.execute("SELECT * FROM user_inventory WHERE user_id = ? ORDER BY acquired_at DESC", (user_id,)).fetchall()

        if user_items:
            df = pd.DataFrame(user_items, columns = ["Instance ID", "User ID", "Item ID", "Item Number", "Acquired At", "Expires At"])
            edited_df = st.data_editor(df, key = "user_inventory_table", num_rows = "fixed", use_container_width = True, hide_index = False)
            
            if st.button("Update User Inventory", use_container_width = True):
                for _, row in edited_df.iterrows():
                    c.execute("""
                        UPDATE OR IGNORE user_inventory 
                        SET item_number = ?, acquired_at = ?, expires_at = ? 
                        WHERE instance_id = ?
                    """, (row["Item Number"], row["Acquired At"], row["Expires At"], row["Instance ID"]))
                conn.commit()
                st.success("User inventory updated successfully.")
                st.rerun()
            
            st.text("")

            with st.container(border=True):
                c1, c2 = st.columns(2)
                item_id_to_delete2 = c1.number_input("Enter item ID to Delete", min_value=0, step=1)
                instance_id_to_delete = c2.number_input("Enter instance ID to Delete", min_value=0, step=1)

            if st.button("Delete Item(s)", use_container_width = True):
                with st.spinner("Processing..."):
                    c.execute("DELETE FROM user_inventory WHERE item_id = ? AND instance_id = ?", (item_id_to_delete2, instance_id_to_delete))
                conn.commit()
                st.rerun()

        else:
            st.write(f"No transactions found for {user}.")

def settings(conn, username):
    c = conn.cursor()
    st.header("⚙️ Settings", divider = "rainbow")

    st.subheader("🔑 Change Password")
    current_password = st.text_input("Current Password", type = "password")
    new_password = st.text_input("New Password", type = "password")
    if st.button("Update Password", use_container_width = True):
        change_password(c, conn, username, current_password, new_password)
        time.sleep(2)
        st.rerun()

    st.divider()
    st.subheader("📧 Add/Update Email")
    current_email = c.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()[0]
    st.write(f"Current Email `{current_email}`")
    email = st.text_input("Email", placeholder = "yourname@domain.com")
    if st.button("Update Email", use_container_width = True):
        add_email(c, conn, username, email)

    st.divider()
    st.subheader("🖊️ Change Visible Name")
    current_visible_name = c.execute("SELECT visible_name FROM users WHERE username = ?", (username,)).fetchone()[0]
    st.write(f"Current visible name `{current_visible_name}`")
    new_name = st.text_input("New Visible Name")
    if st.button("Update Visible Name", use_container_width = True):
        change_visible_name(c, conn, username, new_name)
    
    visibility_settings = c.execute("""
        SELECT show_main_balance_on_leaderboard, show_wallet_on_leaderboard, show_savings_balance_on_leaderboard 
        FROM users WHERE user_id = ?
    """, (st.session_state.user_id,)).fetchone()

    show_main, show_wallet, show_savings = visibility_settings

    st.divider()
    st.subheader("🏆 Leaderboard Privacy")
    show_main = st.checkbox("Show my Main (Vault) Balance", value=bool(show_main))
    show_wallet = st.checkbox("Show my Wallet Balance", value=bool(show_wallet))
    show_savings = st.checkbox("Show my Savings Balance", value=bool(show_savings))

    if st.button("Save Preferences", use_container_width = True):
        c.execute("""
            UPDATE users 
            SET show_main_balance_on_leaderboard = ?, show_wallet_on_leaderboard = ?, show_savings_balance_on_leaderboard = ? 
            WHERE user_id = ?
        """, (int(show_main), int(show_wallet), int(show_savings), st.session_state.user_id))
        conn.commit()
        st.rerun()

    for _ in range(5):
        st.text("")

    st.button("Ege Güvener • © 2024", type = "tertiary", use_container_width = True, disabled = True)

def main(conn):
    if 'current_menu' not in st.session_state:
        st.session_state.current_menu = "Deposit"

    conn, c = init_db()
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.current_menu = "Dashboard"

    if not st.session_state.logged_in:
        st.title("Bank :red[Genova] ™", anchor = False)

        login_option = st.radio("A", ["Login", "Register"], label_visibility="hidden", horizontal=True)
        
        if login_option == "Login":
            username = st.text_input("A", label_visibility="hidden", placeholder="Your remarkable username")
            password = st.text_input("A", label_visibility="collapsed", placeholder="Password", type="password")
            st.caption("Password Hashing by Argon2i")

            st.text("")
            st.text("")

            if st.button("**Log In**", use_container_width = True, type="primary"):
                user = c.execute("SELECT user_id, password FROM users WHERE username = ?", (username,)).fetchone()
                if user and verifyPass(user[1], password):
                    if c.execute("SELECT suspension FROM users WHERE username = ?", (username,)).fetchone()[0] == 1:
                        st.error("Your account has been suspended. Please contact admin (Ege).")
                    else:
                        with st.spinner("Logging you in..."):
                            st.session_state.logged_in = True
                            st.session_state.user_id = user[0]
                            st.session_state.username = username
                            time.sleep(1)
                            
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            st.button("Password Reset", type = "tertiary", use_container_width = True, help = "Not yet available")
            st.text("")
            st.text("")

            c1, c2, c3 = st.columns([1, 1, 1])
            with c2:
                c1, c2 = st.columns(2)
                if c1.button("[ Privacy Policy", type = "tertiary"):
                    privacy_policy_dialog()

                c2.button("Terms of Use ]", type = "tertiary")
            
            st.write('<div style="position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%); color: slategray; text-align: center;"><marquee>Simple and educational bank / finance simulator by Ege. Specifically built for IB Computer Science IA. All rights of this "game" is reserved.</marquee></div>', unsafe_allow_html=True)

        else:
            new_username = st.text_input("A", label_visibility = "hidden", placeholder = "Choose a remarkable username")
            new_password = st.text_input("A", label_visibility = "collapsed", placeholder = "Create a password", type = "password")
            confirm_password = st.text_input("A", label_visibility = "collapsed", placeholder = "Re-password", type = "password")
            st.caption("Password Hashing by Argon2i")
            
            st.text("")
            st.text("")

            if st.button("Register", use_container_width = True, type = "primary"):
                if new_username != "":
                    if len(new_username) >= 5:
                        if new_password != "":
                            if len(new_password) >= 8:
                                if new_password == confirm_password:
                                    register_user(conn, new_username, new_password)
                                    st.rerun()
                                else:
                                    st.error("Passwords do not match.")
                            else:
                                st.error("Password must contain **at least** 8 chars.")
                        else:
                            st.error("Empty password is illegal.")
                    else:
                        st.error("Username must be **at least 5 chars** long.")
                else:
                    st.error("Empty username is illegal.")
            
            st.text("")
            c1, c2, c3 = st.columns([1, 1, 1])
            with c2:
                c1, c2 = st.columns(2)
                if c1.button("[ Privacy Policy", type = "tertiary"):
                    privacy_policy_dialog()

                c2.button("Terms of Use ]", type = "tertiary")
            st.write('<div style="position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%); color: slategray; text-align: center;"><marquee>Simple and educational bank / finance simulator by Ege. Specifically built for IB Computer Science IA. All rights of this "game" is reserved.</marquee></div>', unsafe_allow_html=True)

    elif st.session_state.logged_in:
        st.sidebar.write(f"# Welcome, **{st.session_state.username}**!")
        
        with st.sidebar:
            wallet = c.execute('SELECT wallet FROM users WHERE user_id = ?', (st.session_state.user_id,)).fetchone()[0]
            st.sidebar.write(f"Wallet   |   :green[${numerize(wallet, 2)}]")
            st.sidebar.header(" ", divider="rainbow")

        t1, t2 = st.sidebar.tabs(["🌐 Global", "💠 Personal"])
        
        with t1:
            c1, c2 = st.columns(2)
            if c1.button("Dashboard", type="primary", use_container_width=True):
                st.session_state.current_menu = "Dashboard"
                st.rerun()
            
            if c2.button("Leaderboard", type="primary", use_container_width=True):
                st.session_state.current_menu = "Leaderboard"
                st.rerun()
            
            if st.button("InvestSphere™", type="primary", use_container_width=True):
                st.session_state.current_menu = "Investments"
                st.rerun()

            if st.button("QubitTrades™", type="primary", use_container_width=True):
                st.session_state.current_menu = "Stocks"
                st.rerun()
            
            if st.button("#Global Chat", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Chat"
                st.rerun()
            
            c1, c2 = st.columns(2)
            if c1.button("Shop", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Marketplace"
                st.rerun()

            if c2.button("Blackmarket", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Blackmarket"
                st.rerun()

            if st.button("Heist", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Heist"
                st.rerun()

            if st.button("Gov. & Economy", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Bank"
                st.rerun()

        with t2:
            c1, c2 = st.columns(2)
            if c1.button("Vault", type="primary", use_container_width=True):
                st.session_state.current_menu = "Main Account"
                st.rerun()

            if c2.button("Savings", type="primary", use_container_width=True):
                st.session_state.current_menu = "View Savings"
                st.rerun()

            if st.button("Transaction History", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Transaction History"
                st.rerun()

            if st.button("Pending Transfers", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Manage Pending Transfers"
                st.rerun()
            
            c1, c2 = st.columns(2)
            if c1.button("Inventory", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Inventory"
                st.rerun()

            if c2.button("Holdings", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Holdings"
                st.rerun()

            st.divider()
            if st.session_state.username in admins:
                if st.button("Admin Panel", type="secondary", use_container_width=True):
                    st.session_state.current_menu = "Admin Panel"
                    st.rerun()

            c1, c2 = st.columns(2)
            if c1.button("Log Out", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Logout"
                st.rerun()

            if c2.button("Settings", type="secondary", use_container_width=True):
                st.session_state.current_menu = "Settings"
                st.rerun()

            

############################################################################################################################################################################################################################################################################################################


        if st.session_state.current_menu == "Dashboard":
            dashboard(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Leaderboard":
            leaderboard(c)
        
        elif st.session_state.current_menu == "Marketplace":
            marketplace_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Inventory":
            inventory_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Main Account":
            main_account_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Manage Pending Transfers":
            manage_pending_transfers(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Transaction History":
            display_transaction_history(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "View Savings":
            savings_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Chat":
            chat_view(conn)

        elif st.session_state.current_menu == "Manage Pending Transfers":
            manage_pending_transfers(conn, st.session_state.user_id)
        
        elif st.session_state.current_menu == "Stocks":
            stocks_view(conn, st.session_state.user_id)
        
        elif st.session_state.current_menu == "Holdings":
            portfolio_view(conn, st.session_state.user_id)
        
        elif st.session_state.current_menu == "Heist":
            steal_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Bank":
            bank_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Investments":
            investments_view(conn, st.session_state.user_id)
        
        elif st.session_state.current_menu == "Blackmarket":
            blackmarket_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Logout":
            st.sidebar.info("Logging you out...")
            time.sleep(2.5)
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.current_menu = "Dashboard"
            st.rerun()

        elif st.session_state.current_menu == "Settings":
            settings(conn, st.session_state.username)

        elif st.session_state.current_menu == "Admin Panel":
                admin_panel(conn)

def add_column_if_not_exists(conn):
    c = conn.cursor()

    c.execute("PRAGMA table_info(transactions);")
    columns = [column[1] for column in c.fetchall()]
    if "stock_id" not in columns:
        c.execute("ALTER TABLE transactions ADD COLUMN stock_id INTEGER DEFAULT 0;")
    if "quantity" not in columns:
        c.execute("ALTER TABLE transactions ADD COLUMN quantity INTEGER DEFAULT 0;")

    conn.commit()

if __name__ == "__main__":
    conn = get_db_connection()
    init_db()
    add_column_if_not_exists(conn)
    main(conn)
