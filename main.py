# Simple ATM Simulator.
# Copyright Ege Güvener, 20/12/2024
# License: MIT

import streamlit as st
import sqlite3
import random
import time
import pandas as pd
import datetime
import re
import bcrypt

st.set_page_config(
    page_title = "Bank Genova",
    page_icon = "🏦",
    layout = "centered",
    initial_sidebar_state = "expanded"
)

item_colors = {
        "Common":"",
        "Uncommon":":green",
        "Rare":":blue",
        "Epic":":violet",
        "Mythic":":yellow",
        "Ultimate":":orange"
    }

def format_currency(amount):
   return "{:,.2f}".format(amount)

# def format_currency(amount):
#     return "{:,.2f}".format(amount).replace(",", "X").replace(".", ",").replace("X", ".")


def hashPass(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def verifyPass(hashed_password, entered_password):
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode()
    return bcrypt.checkpw(entered_password.encode(), hashed_password)

admins = [
    "egegvner",
    "believedreams",
]

def calculate_new_quota(c, user_id):
    has_quota_bonus_item = 0
    user_level = c.execute("SELECT level FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    return user_level * 100

def check_and_reset_quota(conn, user_id):
    c = conn.cursor()
    user_data = c.execute("SELECT deposit_quota, last_quota_reset FROM users WHERE user_id = ?", (user_id,)).fetchone()

    current_quota, last_reset = user_data

    if last_reset is None:
        last_reset_time = datetime.datetime(1970, 1, 1)
    else:
        last_reset_time = datetime.datetime.strptime(last_reset, "%Y-%m-%d %H:%M:%S")
    
    now = datetime.datetime.now()

    if (now - last_reset_time).total_seconds() >= 3600:
        new_quota = calculate_new_quota(c, user_id)
        if not current_quota == new_quota:
            c.execute("UPDATE users SET deposit_quota = ?, last_quota_reset = ? WHERE user_id = ?", (new_quota, now.strftime("%Y-%m-%d %H:%M:%S"), user_id))
            conn.commit()
            print(f"Quota reset for user {user_id}.")
            st.toast(f"Quota Refilled! (max: {new_quota})")
            return new_quota
    return current_quota

def apply_interest_if_due(conn, user_id):
    check_and_reset_quota(conn, user_id)

    c = conn.cursor()
    has_savings_account = c.execute("SELECT has_savings_account FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    
    if has_savings_account:
        savings_data = c.execute("SELECT balance, last_interest_applied FROM savings WHERE user_id = ?", (user_id,)).fetchone()
        
        balance, last_applied = savings_data[0], savings_data[1]
        if last_applied is None:
            last_applied_time = datetime.datetime(1970, 1, 1)
        else:
            last_applied_time = datetime.datetime.strptime(last_applied, "%Y-%m-%d %H:%M:%S")
        
        now = datetime.datetime.now()

        hours_passed = (now - last_applied_time).total_seconds() // 3600 
        if hours_passed >= 24:
            days_passed = int(hours_passed // 24)

            daily_interest_rate = 0.5
            total_interest = balance * daily_interest_rate * days_passed
            new_balance = balance + total_interest

            new_last_applied_time = last_applied_time + datetime.timedelta(days = days_passed)
            c.execute("""
                UPDATE savings
                SET balance = ?, last_interest_applied = ?
                WHERE user_id = ?
            """, (new_balance, new_last_applied_time.strftime("%Y-%m-%d %H:%M:%S"), user_id))

            conn.commit()
            print(f"Applied ${total_interest:.2f} interest ({days_passed} days) to user {user_id}'s savings account.")

def change_password(c, conn, username, current_password, new_password):
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

def check_cooldown(c, user_id):
    last_transaction = c.execute("SELECT last_transaction_time FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    if last_transaction:
        last_time = pd.to_datetime(last_transaction)
        current_time = pd.Timestamp.now()
        time_diff = (current_time - last_time).total_seconds()
        if time_diff < 3:
            st.warning(f"Cooldown in effect. Please wait {3 - int(time_diff)} seconds before your next transaction.")
            return False
    return True

def update_last_transaction_time(c, conn, user_id):
    current_time = pd.Timestamp.now().to_pydatetime().isoformat()
    c.execute("UPDATE users SET last_transaction_time = ? WHERE user_id = ?", (current_time, user_id))

    conn.commit()

def recent_transactions_metrics(c, user_id):
    current_time = pd.Timestamp.now()
    last_24_hours = current_time - pd.Timedelta(days = 1)

    transactions = c.execute("SELECT type, COUNT(*), SUM(amount) FROM transactions WHERE user_id = ? AND timestamp >= ? GROUP BY type", (user_id, last_24_hours.strftime('%Y-%m-%d %H:%M:%S'))).fetchall()

    metrics = {
        "Top Ups": {"count": 0, "total": 0},
        "Withdrawals": {"count": 0, "total": 0},
        "Incoming Transfers": {"count": 0, "total": 0},
        "Outgoing Transfers": {"count": 0, "total": 0},
    }

    for trans_type, count, total in transactions:
        if "top up" in trans_type.lower():
            metrics["Deposits"] = {"count": count, "total": total}
        elif "withdrawal" in trans_type.lower():
            metrics["Withdrawals"] = {"count": count, "total": total}
        elif "Transfer to" in trans_type:
            metrics["Outgoing Transfers"] = {"count": count, "total": total}
        elif "Transfer from" in trans_type:
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

def leaderboard_logic2(c):
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

def get_transaction_history(c, user_id):
    username = c.execute("SELECT username FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    # Fetch sent transactions
    sender_query = """
        SELECT 'sent' AS role, type, amount, balance, timestamp, status,  receiver_username
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
    """
    sent_transactions = c.execute(sender_query, (user_id,)).fetchall()

    # Fetch received transactions
    receiver_query = """
        SELECT 'received' AS role, type, amount, balance, timestamp, status, user_id AS from_user_id
        FROM transactions
        WHERE  receiver_username = ?
        ORDER BY timestamp DESC
    """
    received_transactions = c.execute(receiver_query, (username,)).fetchall()

    return sent_transactions, received_transactions



def register_user(conn, c, username, password, email = None, visible_name = None):
    try:

        user_id_to_be_registered = random.randint(100000, 999999)
        hashed_password = hashPass(password)
                
        with st.spinner("Creatning your account..."):
            c.execute('''INSERT INTO users (user_id, username, level, visible_name, password, balance, wallet, has_savings_account, deposit_quota, last_quota_reset, suspension, deposits, withdraws, incoming_transfers, outgoing_transfers, total_transactions, last_transaction_time, email)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (
                   user_id_to_be_registered,
                   username,
                   1,    # Default level
                   visible_name,
                   hashed_password, 
                   10,   # Default balance
                   0,    # Default wallet
                   0,    # Default savings account
                   100,  # Default deposit quota
                   None, # Default last quota reset
                   0,    # Default suspension (0 = not suspended)
                   0,    # Default deposits
                   0,    # Default withdraws
                   0,    # Default incoming transfers
                   0,    # Default outgoing transfers
                   0,    # Default total transactions
                   None, # Default last transaction time
                   email
                   ))
            conn.commit()

        st.session_state.logged_in = True
        st.session_state.user_id = user_id_to_be_registered
        st.session_state.username = username
        time.sleep(2)

        st.session_state.current_menu = "Main Account View"

    except sqlite3.IntegrityError:
        st.error("Username already exists!")
        return False
    except Exception as e:
        st.error(f"Error: {e}")
        return False
        
def init_db():
    conn = sqlite3.connect('eggggggggg.db')
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
                  deposit_quota INTEGER DEFAULT 100,
                  last_quota_reset DATETIME DEFAULT CURRENT_TIMESTAMP,
                  suspension INTEGER DEFAULT 0,
                  deposits INTEGER DEFAULT 0,
                  withdraws INTEGER DEFAULT 0,
                  incoming_transfers INTEGER DEFAULT 0,
                  outgoing_transfers INTEGER DEFAULT 0,
                  total_transactions INTEGER DEFAULT 0,
                  last_transaction_time DATETIME DEFAULT NULL,
                  email TEXT
                  )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                  transaction_id INTEGER PRIMARY KEY NOT NULL,
                  user_id INTEGER NOT NULL,
                  type TEXT NOT NULL,
                  amount REAL NOT NULL,
                  balance REAL NOT NULL,
                  receiver_username TEXT DEFAULT None,
                  status TEXT DEFAULT None,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users(user_id),
                  FOREIGN KEY ( receiver_username) REFERENCES users(username)
                  )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS savings (
              user_id INTEGER NOT NULL,
              balance REAL DEFAULT 0,
              interest_rate REAL DEFAULT 0.05,
              last_interest_applied DATETIME DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id ) REFERENCES users(user_id)
              )
              ''')
    
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
              )
              ''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_inventory (
              user_id INTEGER NOT NULL,
              item_id INTEGER NOT NULL,
              acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES users(user_id),
              FOREIGN KEY (item_id) REFERENCES marketplace_items(item_id)
              )
              ''')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON transactions(user_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON transactions(timestamp)')

    conn.commit()
    return conn, c

@st.dialog("Top Up", width = "small")
def deposit_dialog(conn, user_id):
    check_and_reset_quota(conn, user_id)

    c = conn.cursor()
    current_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    current_deposit_quota = float(check_and_reset_quota(conn, user_id))
    
    if "top_up_value" not in st.session_state:
        st.session_state.top_up_value = 0.00
    
    if "amount" not in st.session_state:
        st.session_state.amount = 0.00

    if "quota" not in st.session_state:
        st.session_state.quota = c.execute("SELECT deposit_quota FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    st.write(f"# Balance \a **•** \a :green[${format_currency(current_balance)}]")
    st.header("", divider = "rainbow")
    
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("%25", use_container_width = True):
        st.session_state.top_up_value = (current_deposit_quota / 100) * 25
    if c2.button("%50", use_container_width = True):
        st.session_state.top_up_value = (current_deposit_quota / 100) * 50
    if c3.button("%75", use_container_width = True):
        st.session_state.top_up_value = (current_deposit_quota / 100) * 75
    if c4.button("%100", use_container_width = True):
        st.session_state.top_up_value = current_deposit_quota

    c1, c2 = st.columns(2)
    c1.write(f"Top Up Quota \a $|$ \a :green[${format_currency(st.session_state.quota)}]")
    if c2.button("Reload Quota", type = "primary", use_container_width = True):
        st.session_state.quota = c.execute("SELECT deposit_quota FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
        
    amount = st.session_state.amount
    st.session_state.amount = st.number_input("Amount", min_value = 0.0, step = 0.25, value = st.session_state.top_up_value)
    st.divider()
    tax = (amount / 100) * 0.5
    net = amount - tax

    st.write(f"Net Deposit \a $|$ \a :green[${format_currency(net)}] \a $|$ \a :red[${format_currency(tax)} Tax*]")
    st.write(f"New Main Balance \a $|$ \a :green[${format_currency(current_balance + amount - tax)}]")
    
    if st.button("**Confirm Top Up**", type = "primary", use_container_width = True, disabled = True if amount <= 0 else False):
        if check_cooldown(c, user_id):
            balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
            if net > 0:
                if net <= current_deposit_quota:
                    c.execute("UPDATE users SET balance = balance + ?, deposits = deposits + 1, deposit_quota = deposit_quota - ? WHERE user_id = ?", (net, net, user_id))
                    c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, balance) VALUES (?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, 'Top Up', net, balance))
                    update_last_transaction_time(c, conn, user_id)
                    conn.commit()
                    with st.spinner("Processing..."):
                        time.sleep(random.uniform(2, 4))
                        st.success(f"Successfully deposited ${net:.2f}")
                    time.sleep(2.5)
                    st.rerun()
                else:
                    st.warning("Not enough quota.")
            else:
                st.error("Invalid deposit amount. Must be between $0 and $1,000,000.")
    st.text(" ")
    st.caption("*All transactions are subject to %0.5 tax (VAT) and are irreversible.")
    
@st.dialog("Withdraw", width = "small")
def withdraw_dialog(conn, user_id):
    check_and_reset_quota(conn, user_id)

    c = conn.cursor()
    current_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    
    if "withdraw_value" not in st.session_state:
        st.session_state.withdraw_value = 0.00

    st.write(f"# Balance \a **•** \a :green[${format_currency(current_balance)}]")
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
    st.write(f"Net Withdraw \a $|$ \a :green[{format_currency(net)}] \a $|$ \a :red[${format_currency(tax)} Tax*]")
    c1, c2 = st.columns(2)
    c1.write(f"Remaining Balance \a $|$ \a :green[${format_currency(current_balance - amount)}]")
    if (current_balance - amount) < 0:
        c2.write("**:red[Insufficent]**")

    c1, c2 = st.columns(2)
    if c1.button("Withdraw to Wallet", type = "secondary", use_container_width = True, disabled = True if net <= 0 or (current_balance - amount) < 0 else False, help = "Insufficent funds" if net <= 0 or (current_balance - net) < 0 else None):
        if check_cooldown(c, user_id):
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (net, user_id))
            conn.commit()
            new_wallet = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, balance) VALUES (?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, "Withdraw From Main Account To Wallet", net, new_wallet))
            conn.commit()
            update_last_transaction_time(c, conn, user_id)
            with st.spinner("Processing..."):
                time.sleep(random.uniform(2, 4))
                st.success(f"Successfully withdrawn ${net:.2f}")
            st.session_state.withdraw_value = 0.0
            time.sleep(2.5)
            st.rerun()
            
    if c2.button("Withdraw to Savings", type = "primary", use_container_width = True, disabled = True if net <= 0 or (current_balance - amount) < 0 else False, help = "Insufficent funds" if net <= 0 or (current_balance - net) < 0 else None):
        if check_cooldown(c, user_id):
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            c.execute("UPDATE savings SET balance = balance + ? WHERE user_id = ?", (net, user_id))
            conn.commit()
            new_savings_balance = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, balance) VALUES (?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, "Withdraw From Main Account To Savings", amount, new_savings_balance))
            conn.commit()
            update_last_transaction_time(c, conn, user_id)
            with st.spinner("Processing..."):
                time.sleep(random.uniform(2, 4))
                st.success(f"Successfully withdrawn ${amount:.2f}")
            st.session_state.withdraw_value = 0.0
            time.sleep(2.5)
            st.rerun()

    st.text(" ")
    st.caption("*All transactions are subject to %0.5 tax (VAT) and are irreversible.")

@st.dialog("Transfer Funds", width="small")
def transfer_dialog(conn, user_id):
    check_and_reset_quota(conn, user_id)

    c = conn.cursor()
    all_users = [user[0] for user in c.execute("SELECT username FROM users WHERE username != ?", (st.session_state.username,)).fetchall()]
    st.header(" ", divider = "rainbow")
    receiver_username = st.selectbox("Recipient Username", options = all_users)
    amount = st.number_input("Amount", min_value = 0.0, step=0.25)
    tax = (amount / 100) * 0.5
    net = amount - tax
    st.divider()

    st.write(f"Net Transfer $|$ :green[${format_currency(net)}] $|$ :red[${format_currency(tax)} Tax]")
    st.caption("*Tax is not applied untill receiver accepts the transaction.")
    
    if st.button("Initiate Transfer", type = "primary", use_container_width = True, disabled = True if amount == 0.00 else False):
        if check_cooldown(c, user_id):
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

                if 0 < amount <= 1000000 and amount <= current_balance:
                    c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
                    c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, balance,  receiver_username, status) VALUES (?, ?, ?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f'Transfer to {receiver_username}', amount, current_balance, receiver_username, 'pending'))
                    
                    conn.commit()
                    with st.spinner("Processing"):
                        time.sleep(2)
                    st.success(f"Successfully initiated transfer of ${amount:.2f} to {receiver_username}. Awaiting acceptance.")
                    time.sleep(2.5)
                    st.rerun()
                else:
                    st.error("Invalid transfer amount. Must be within current balance and below $1,000,000.")
            else:
                st.error(f"User {receiver_username} does not exist.")
    
    st.caption("All transactions are subject to %0.5 tax (VAT) and irreversible.*")
    
@st.dialog("Deposit To Savings", width = "small")
def deposit_to_savings_dialog(conn, user_id):
    check_and_reset_quota(conn, user_id)

    c = conn.cursor()

    if "deposit_to_savings_value" not in st.session_state:
        st.session_state.deposit_to_savings_value = 0.00
    
    if "deposit_source" not in st.session_state:
        st.session_state.deposit_source = 0.00

    current_savings = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]
    main_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    st.header(f"Savings \a **•** \a :green[${format_currency(current_savings)}]", divider = "rainbow")
    st.write("#### Deposit Source")
    st.session_state.deposit_source = st.radio("A", label_visibility = "collapsed", options = [f"Main Account \a • \a :green[${format_currency(main_balance)}]", f"Wallet \a • \a :green[${format_currency(wallet_balance)}]"])

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
    st.write(f"Net Deposit \a $|$ \a :green[${format_currency(net)}] \a $|$ \a :red[${format_currency(tax)} Tax]")
    st.write(f"New Savings \a $|$ \a :green[${format_currency(current_savings + net)}]")
    if st.button("Confirm Deposition From Main Account" if "Main" in st.session_state.deposit_source else "Confirm Deposition From Wallet", type="primary", use_container_width = True, disabled = True if amount <= 0.00 else False):
        if check_cooldown(c, user_id):
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
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, balance) VALUES (?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f"Deposit To Savings From {source}", amount, format_currency(current_savings + amount)))

            conn.commit()
            with st.spinner("Processing..."):
                time.sleep(2)
            st.success(f"Successfully deposited ${format_currency(net)} from {source} to your savings.")
            time.sleep(2.5)
            st.rerun()

    st.caption("All transactions are subject to %0.5 tax (VAT) and irreversible.*")

@st.dialog("Withdraw Savings", width = "small")
def withdraw_from_savings_dialog(conn, user_id):
    check_and_reset_quota(conn, user_id)

    c = conn.cursor()

    if "withdraw_from_savings_value" not in st.session_state:
        st.session_state.withdraw_from_savings_value = 0.00
    
    if "withdraw_target" not in st.session_state:
        st.session_state.withdraw_target = 0.00

    current_savings = c.execute("SELECT balance FROM savings WHERE user_id = ?", (user_id,)).fetchone()[0]
    main_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    st.header(f"Savings \a **•** \a :green[${format_currency(current_savings)}]", divider = "rainbow")
    st.write("**Target**")
    st.session_state.withdraw_target = st.radio("A", label_visibility = "collapsed", options = [f"Main Account \a • \a :green[${format_currency(main_balance)}]", f"Wallet \a • \a :green[${format_currency(wallet_balance)}]"])
    
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
    st.write(f"Net Withdrawal $|$ :green[${format_currency(net)}] $|$ :red[${format_currency(tax)} Tax]")
    st.write(f"Remaining Savings $|$ :green[${format_currency(current_savings - amount)}]")
    if st.button("Confirm Withdrawal Into Main Account" if "Main" in st.session_state.withdraw_target else "Confirm Withdrawal Into Wallet", type = "primary", use_container_width = True, disabled = True if amount <= 0.00 else False):
        if check_cooldown(c, user_id):
            if "Main" in st.session_state.withdraw_target:
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            else:
                c.execute("UPDATE users SET wallet = wallet + ? WHERE user_id = ?", (amount, user_id))

            c.execute("UPDATE savings SET balance = balance - ? WHERE user_id = ?", (amount, user_id))

            target = "Main Account" if "Main" in st.session_state.withdraw_target else "Wallet"
            c.execute("INSERT INTO transactions (transaction_id, user_id, type, amount, balance) VALUES (?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), user_id, f"Withdraw From Savings To {target}", amount, format_currency(current_savings - amount)))

            conn.commit()
            with st.spinner("Processing..."):
                time.sleep(2)
            st.success(f"Successfully withdrawn ${format_currency(net)} into {target}")
            time.sleep(2.5)
            st.rerun()

    st.caption("All transactions are subject to %0.5 tax (VAT) and irreversible.*")

@st.dialog("Item Details")
def item_options(conn, user_id, item_id):
    c = conn.cursor()
    item_data = c.execute("SELECT name, description, rarity, price, stock FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchall()[0]
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
    st.header(f"{item_colors[item_data[2]]}[{item_data[0]}] :gray[\a **•** \a {item_data[2].upper()}]", divider = "rainbow")
    st.text("")
    st.text("")
    with st.container(border=True):
        st.write(f"**:gray[EFFECT \a $|$ \a ]** {item_data[1]}.")

        st.write(f"**:gray[PRICE \a $|$ \a ]** :green[${format_currency(item_data[3])}]")
    st.divider()
    st.write(f"Wallet \a **•** \a :green[${format_currency(wallet_balance)}] \a **•** \a :red[INSUFFICENT]" if wallet_balance < item_data[3] else f"Wallet \a **•** \a :green[${format_currency(wallet_balance)}]")

    c1, c2 = st.columns(2)
    if c1.button("Cancel", use_container_width = True):
        st.rerun()
    if c2.button(f"**Pay :green[${format_currency(item_data[3])}] With Wallet**", type = "primary", use_container_width = True, disabled = True if wallet_balance < item_data[3] else False):
        buy_item(conn, user_id, item_id)

def leaderboard(c):
    st.divider()
    st.header("🏆 Leaderboard")
    leaderboard_data = leaderboard_logic(c)

    if leaderboard_data:
        st.table([{"Rank": user["rank"], "Name": user["name"], "Balance": f"${user['balance']:.2f}"} for user in leaderboard_data])
    else:
        st.write("No users found in the database!")

def buy_item(conn, user_id, item_id):
    c = conn.cursor()

    item = c.execute("SELECT price FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchone()[0]
    stock = c.execute("SELECT stock FROM marketplace_items WHERE item_id = ?", (item_id,)).fetchone()[0]
    if not item:
        st.toast("Item not found.")

    price = item
    wallet_balance = c.execute("SELECT wallet FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    if wallet_balance < price:
        st.warning("Insufficent wallet balance! Withdraw money to your wallet.")
    else:
        if stock != 0:
            with st.spinner("Purchasing..."):
                c.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (price, user_id))
                c.execute("INSERT INTO user_inventory (user_id, item_id) VALUES (?, ?)", (user_id, item_id))
                c.execute("UPDATE marketplace_items SET stock = stock - 1 WHERE item_id = ?", (item_id,))
                conn.commit()
                time.sleep(3)
            st.success(f"Item purchased!")
            time.sleep(2)
            st.rerun()
        else:
            st.warning("This item is out of stock.")

def marketplace_view(conn, user_id):
    c = conn.cursor()

    items = c.execute("SELECT item_id, name, description, rarity, price, stock FROM marketplace_items").fetchall()
    st.header("Marketplace", divider = "rainbow")
    for item in items:
        st.write(f"#### **{item_colors[item[3]]}[{item[1]}]**")
        st.write(f":gray[{item[3].upper()}] \a • \a {item[2]}")
        st.write(f":green[${format_currency(item[4])}]")
        if st.button(f"Options", key = f"buy_{item[0]}", use_container_width = True):
            item_options(conn, user_id, item[0])
        st.divider()

def inventory_view(conn, user_id):
    c = conn.cursor()
    st.header("Inventory", divider = "rainbow")
    owned_item_ids = [owned_item[1] for owned_item in c.execute("SELECT * FROM user_inventory").fetchall()]
    
    for id in owned_item_ids:
        name, description, rarity, price, boost_type, boost_value  = c.execute("SELECT name, description, rarity, price, boost_type, boost_value FROM marketplace_items WHERE item_id = ?", (id,)).fetchall()
        st.subheader(f"{item_colors[rarity]}[{name}]")
        st.caption(rarity.upper())
        st.write(description)
        if st.button("**OPTIONS**", use_container_width = True, key = id):
            pass
        st.divider()

def manage_pending_transfers(c, conn, receiver_id):
    st.header("📥 Pending Transfers", divider = "rainbow")
    '/..hfyhyfdt'
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

        st.write(f"💸 \a | \a **{sender_username}** wants to transfer :green[${format_currency(amount)}]. You will receive :green[${format_currency(net)}]. :red[(%0.5 tax.)]")
        c1, c2 = st.columns(2)

        if c1.button(f"Accept", type = "primary", use_container_width = True, key = transaction_id):
            with st.spinner("Accepting Transfer"):
                c.execute("UPDATE transactions SET status = 'accepted' WHERE transaction_id = ?", (transaction_id,))
                c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (net, receiver_id))
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
    check_and_reset_quota(conn, user_id)
    c = conn.cursor()

    current_balance = c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]

    st.header("Main Account", divider="rainbow")
    st.write(f"Current Balance \a | \a :green[${current_balance:.2f}]")

    col1, col2 = st.columns(2)
    if col1.button("Top Up", type = "primary", use_container_width = True):
        deposit_dialog(conn, user_id)
    if col2.button("Withdraw", use_container_width = True):
        withdraw_dialog(conn, user_id)
    if st.button("Transfer", use_container_width = True):
        transfer_dialog(conn, user_id)
    if st.button("Pending Transfers", use_container_width = True):
        st.session_state.current_menu = "Manage Pending Transfers"
        st.rerun()

    for _ in range(5):
        st.text("")
    
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
    st.write(f"Total Transactions \a | \a :green[{total_transactions}]")

    st.divider()
    st.subheader("Balance Trend")
    transactions = c.execute("SELECT timestamp, balance FROM transactions WHERE user_id = ? ORDER BY timestamp ASC", (user_id,)).fetchall()
    if transactions:
        df = pd.DataFrame(transactions, columns = ["Timestamp", "Balance"])
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        st.line_chart(df.set_index("Timestamp")["Balance"])
    else:
        st.info("No transaction data available for trends.")

def savings_view(conn, user_id):
    c = conn.cursor()
    apply_interest_if_due(conn, user_id)
    check_and_reset_quota(conn, user_id)
    
    st.header("Savings", divider="rainbow")
    
    has_savings_account = c.execute("""
        SELECT has_savings_account
        FROM users
        WHERE user_id = ?
    """, (user_id,)).fetchone()[0]
    
    if not has_savings_account:
        if st.button("Set up a Savings Account (%0.5 Interest Rate)", type="primary", use_container_width = True):
            with st.spinner("Setting up a savings account for you..."):
                c.execute("""
                    UPDATE users
                    SET has_savings_account = 1
                    WHERE user_id = ?
                """, (user_id,))
                c.execute("""
                    INSERT INTO savings (user_id, balance, interest_rate, last_interest_applied)
                    VALUES (?, 0, 0.005, ?)
                """, (user_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                time.sleep(2)
            st.success("Congrats! You now have a savings account!")
            st.rerun()
    else:
        savings_balance = c.execute("""
            SELECT balance
            FROM savings
            WHERE user_id = ?
        """, (user_id,)).fetchone()[0]
        st.write(f"Savings Balance \a | \a :green[${format_currency(savings_balance)}]")

        c1, c2, = st.columns(2)
        if c1.button("Deposit", type = "primary", use_container_width = True):
            deposit_to_savings_dialog(conn, st.session_state.user_id)

        if c2.button("Withdraw", type = "secondary", use_container_width = True, key = "a"):
            withdraw_from_savings_dialog(conn, st.session_state.user_id)

def display_transaction_history(c, user_id):
    st.header("Transaction History", divider = "rainbow")

    sent_transactions, received_transactions = get_transaction_history(c, user_id)
    transactions = sent_transactions + received_transactions

    if transactions:
        for t in transactions:
            role = t[0]
            t_type = t[1]
            amount = t[2]
            balance = t[3]
            timestamp = t[4]
            status = t[5]
            receiver_username = t[6] if role == "sent" else "N/A"
            from_username = (
                c.execute("SELECT username FROM users WHERE user_id = ?", (t[6],)).fetchone()[0]
                if role == "received" else "N/A"
            )

            if t_type == "Top Up":
                st.success(f"Top Up", icon="💵")
                st.write(f"**Amount** \a $|$ \a :green[+${format_currency(amount)}]")
                st.write(f"New Main Balance \a $|$ \a :green[+${format_currency(balance)}]")
                st.text("")
                st.text("")
                st.caption(timestamp)

            elif t_type == "Withdraw From Main Account To Wallet":
                st.warning(f"{t_type}", icon="💵")
                st.write(f"Amount \a $|$ \a :red[-${format_currency(amount)}]")
                st.write(f"New Balance \a $|$ \a :red[${format_currency(balance)}]")
                st.text("")
                st.text("")
                st.caption(timestamp)

            elif t_type == "Withdraw From Main Account To Savings":
                st.warning(f"{t_type}", icon="💵")
                st.write(f"Amount \a | \a :red[-${format_currency(amount)}]")
                st.write(f"New Balance \a $|$ \a :red[${format_currency(balance)}]")
                st.text("")
                st.text("")
                st.caption(timestamp)

            elif role == "sent" and "transfer to" in t_type.lower():
                st.info(f"{t_type.title()} { receiver_username} $|$ (Status: **{status.capitalize()}**)", icon="💸")
                st.write(f"Amount \a $|$ \a :red[-${format_currency(amount)}]")
                st.write(f"New Balance \a $|$ \a :red[${format_currency(balance)}]")
                st.text("")
                st.text("")
                st.caption(timestamp)

            elif role == "received" and "transfer from" in t_type.lower():
                st.info(f"{t_type.title()} {from_username} $|$ (Status: **{status.capitalize()}**)", icon="💸")
                st.write(f"Amount \a $|$ \a :green[+${format_currency(amount)}]")
                st.write(f"New Balance \a $|$ \a :green[${format_currency(balance)}]")
                st.text("")
                st.text("")
                st.caption(timestamp)

            elif t_type.lower().startswith("deposit to savings"):
                st.info(f"{t_type.title()}", icon="🏦")
                st.write(f"Amount \a $|$ \a :green[+${format_currency(amount)}]")
                st.write(f"New Savings Balance \a $|$ \a :green[${format_currency(balance)}]")
                st.text("")
                st.text("")
                st.caption(timestamp)

            elif t_type.lower().startswith("withdraw to"):
                st.warning(f"{t_type.title()}", icon="🏧")
                st.write(f"Amount \a $|$ \a :red[-${format_currency(amount)}]")
                st.write(f"Remaining Balance \a $|$ \a :green[${format_currency(balance)}]")
                st.text("")
                st.text("")
                st.caption(timestamp)
            else:
                st.warning(f"Other Transaction $|$ (Status: {status})")
                st.write(f"Amount \a $|$ \a ${format_currency(amount)}")
                st.write(f"Balance \a $|$ \a ${format_currency(balance)}")
                st.text("")
                st.text("")                
                st.caption(timestamp)

            st.divider()
    else:
        st.info("No transactions found in your history.")

def admin_panel(conn):
    c = conn.cursor()
    st.divider()
    st.header("Marketplace Items", divider = "rainbow")

    with st.expander("New Item Creation"):
        with st.form(key= "q"):
            st.subheader("New Item Creation")
            item_id = st.text_input("Item ID", value = f"{random.randint(100000000, 999999999)}", disabled = True, help = "Item ID must be unique")
            name = st.text_input("", label_visibility = "collapsed", placeholder = "Item  Name")
            description = st.text_input("", label_visibility = "collapsed", placeholder = "Description")
            rarity = st.selectbox("", label_visibility = "collapsed", placeholder = "Description", options = ["Common", "Uncommon", "Rare", "Epic", "Ultimate"])         
            price = st.text_input("", label_visibility = "collapsed", placeholder = "Price")
            stock = st.text_input("", label_visibility = "collapsed", placeholder = "Stock")
            boost_type = st.text_input("", label_visibility = "collapsed", placeholder = "Boost Type")
            boost_value = st.text_input("", label_visibility = "collapsed", placeholder = "Boost Value")
            st.divider()
            
            if st.form_submit_button("Add Item", use_container_width = True):
                existing_item_ids = c.execute("SELECT item_id FROM marketplace_items").fetchall()
                if item_id not in existing_item_ids:
                    with st.spinner("Creating item..."):
                        c.execute("INSERT INTO marketplace_items (item_id, name, description, rarity, price, stock, boost_type, boost_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (item_id, name, description, rarity, price, stock, boost_type, boost_value))
                        conn.commit()
                    st.success("Item created!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Duplicate item_id")

    st.header("Manage Items", divider = "rainbow")
    with st.spinner("Loading marketplace items..."):
        item_data = c.execute("SELECT item_id, name, description, rarity, price, stock, boost_type, boost_value FROM marketplace_items").fetchall()
   
    df = pd.DataFrame(item_data, columns = ["Item ID", "Item Name", "Description", "Rarity", "Price", "Stock", "Boost Type", "Boost Value"])
    edited_df = st.data_editor(df, key = "item_table", num_rows = "fixed", use_container_width = True, hide_index = True)
    if st.button("Update Items", use_container_width = True):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE marketplace_items SET name = ?, description = ?, rarity = ?, price = ?, stock = ?, boost_type = ?, boost_value = ? WHERE item_id = ?", (row["Item Name"], row["Description"], row["Rarity"], row["Price"], row["Stock"], row["Boost Type"], row["Boost Value"], row["Item ID"]))
        conn.commit()
        with st.spinner("Processing Changes..."):
            time.sleep(2)
        st.success("User data updated.")
        time.sleep(1)
        st.rerun()

    item_id_to_delete = st.number_input("Enter Item ID to Delete", min_value = 0, step = 1)
    if st.button("Delete Item", use_container_width = True):
        with st.spinner("Processing..."):
            c.execute("DELETE FROM marketplace_items WHERE item_id = ?", (item_id_to_delete,))
            time.sleep(2)
        conn.commit()
        st.success(f"Item {item_id_to_delete} deleted successfully.")
        st.rerun()

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
            conn.commit()
            
            st.success(f"User {temp_user.capitalize()} and their associated data have been deleted.")
            time.sleep(2)
            st.rerun()
        else:
            st.error(f"User {temp_user.capitalize()} not found in the database!")

    st.divider()
    st.header("Manage User Transactions", divider = "rainbow")
    st.text("")

    user = st.selectbox("Select User", [u[0] for u in c.execute("SELECT username FROM users").fetchall()])
    if user:
        user_id = c.execute("SELECT user_id FROM users WHERE username = ?", (user,)).fetchone()[0]
        transactions = c.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC", (user_id,)).fetchall()

        if transactions:
            df = pd.DataFrame(transactions, columns = ["Transaction ID", "User ID", "Type", "Amount", "Balance", "To Username", "Status", "Timestamp"])
            edited_df = st.data_editor(df, key = "transaction_editor", num_rows = "fixed", use_container_width = True, hide_index = False)
            
            if st.button("Update Transaction(s)", use_container_width = True):
                for _, row in edited_df.iterrows():
                    c.execute("""
                        UPDATE OR IGNOREtransactions 
                        SET type = ?, amount = ?, balance = ?,  receiver_username = ? 
                        WHERE transaction_id = ?
                    """, (row["Type"], row["Amount"], row["Balance"], row["To Username"], row["Transaction ID"]))
                conn.commit()
                st.success("Transactions updated successfully.")
                st.rerun()
            
            st.text("")
            transaction_id_to_delete = st.number_input("Enter Transaction ID to Delete", min_value=0, step=1)
            if st.button("Delete Transaction", use_container_width = True):
                with st.spinner("Processing..."):
                    c.execute("DELETE FROM transactions WHERE transaction_id = ?", (transaction_id_to_delete,))
                    time.sleep(2)
                conn.commit()
                st.success(f"Transaction {transaction_id_to_delete} deleted successfully.")
                st.rerun()

        else:
            st.write(f"No transactions found for {user}.")

    st.divider()
    st.header("Users", divider = "rainbow")
    st.text("")
    st.write(":red[Editing data from the dataframes below without proper permission will trigger a legal punishment by law.]")
    with st.spinner("Loading User Data"):
        userData = c.execute("SELECT user_id, username, level, visible_name, password, balance, wallet, has_savings_account, deposit_quota, last_quota_reset, suspension, deposits, withdraws, incoming_transfers, outgoing_transfers, total_transactions, last_transaction_time, email FROM users").fetchall()
        time.sleep(1)
    df = pd.DataFrame(userData, columns = ["User ID", "Username", "Level", "Visible Name", "Pass", "Balance", "Wallet", "Has Savings Account", "Deposit Quota", "Last Quota Reset", "Suspension", "Deposits", "Withdraws", "Transfers Received", "Transfers Sent", "Total Transactions", "Last Transaction Time", "Email"])
    edited_df = st.data_editor(df, key = "edit_table", num_rows = "fixed", use_container_width = True, hide_index = False)

    for _ in range(4):
        st.text("")

    if st.button("Update Data", use_container_width = True, type = "secondary"):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE users SET username = ?, level = ?, visible_name = ?, password = ?, balance = ?, wallet = ?, has_savings_account = ?, deposit_quota = ?, last_quota_reset = ?, suspension = ?, deposits = ?, withdraws = ?, incoming_transfers = ?, outgoing_transfers = ?, total_transactions = ?, last_transaction_time = ?, email = ? WHERE user_id = ?", (row["Username"], row["Level"], row["Visible Name"], row["Pass"], row["Balance"], row["Wallet"], row["Has Savings Account"], row["Deposit Quota"], row["Last Quota Reset"], row["Suspension"], row["Deposits"], row["Withdraws"], row["Transfers Received"], row["Transfers Sent"], row["Total Transactions"], row["Last Transaction Time"], row["Email"], row["User ID"]))
        conn.commit()
        with st.spinner("Processing Changes..."):
            time.sleep(2)
        st.success("User data updated.")
        st.rerun()

    st.header("Savings Data", divider = "rainbow")
    with st.spinner("Loading User Data"):
        savings_data = c.execute("SELECT user_id, balance, interest_rate, last_interest_applied FROM savings").fetchall()
        time.sleep(1)
    df = pd.DataFrame(savings_data, columns = ["User ID", "Balance", "Interest Rate", "Last Interest Applied"])
    edited_df = st.data_editor(df, key = "edit_table2", num_rows = "fixed", use_container_width = True, hide_index = False)

    for _ in range(4):
        st.text("")

    if st.button("Update Savings Data", use_container_width = True, type = "secondary"):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE users SET balance = ?, interest_rate = ?, last_interest_applied = ? WHERE user_id = ?", (row["Balance"], row["Interest Rate"], row["Last Interest Applied"]))
        conn.commit()
        with st.spinner("Processing Changes..."):
            time.sleep(2)
        st.success("User data updated.")
        st.rerun()

def settings(c, conn, username):
    st.title("⚙️ Settings")

    st.divider()
    st.subheader("🔑 Change Password")
    current_password = st.text_input("Current Password", type = "password")
    new_password = st.text_input("New Password", type = "password")
    if st.button("Update Password"):
        change_password(c, conn, username, current_password, new_password)
        time.sleep(2)
        st.rerun()

    st.divider()
    st.subheader("📧 Add/Update Email")
    current_email = c.execute("SELECT email FROM users WHERE username = ?", (username,)).fetchone()[0]
    st.write(f"Current Email `{current_email}`")
    email = st.text_input("Email", placeholder = "yourname@domain.com")
    if st.button("Update Email"):
        add_email(c, conn, username, email)

    st.divider()
    st.subheader("🖊️ Change Visible Name")
    current_visible_name = c.execute("SELECT visible_name FROM users WHERE username = ?", (username,)).fetchone()[0]
    st.write(f"Current visible name `{current_visible_name}`")
    new_name = st.text_input("New Visible Name")
    if st.button("Update Visible Name"):
        change_visible_name(c, conn, username, new_name)
    
    for _ in range(5):
        st.text("")

    st.button("Ege Güvener • © 2024", type = "tertiary", use_container_width = True, disabled = True)

def main(conn):

    st.title("Bank :red[Genova] ™", anchor = False)

    if 'current_menu' not in st.session_state:
        st.session_state.current_menu = "Deposit"

    conn, c = init_db()
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.current_menu = "Dashboard"

    if not st.session_state.logged_in:
        login_option = st.radio("A", ["Login", "Register"], label_visibility="hidden")
        
        if login_option == "Login":
            username = st.text_input("A", label_visibility="hidden", placeholder="Your remarkable username")
            password = st.text_input("A", label_visibility="collapsed", placeholder="Password", type="password")

            for _ in range(4):
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
                            
                    time.sleep(4)
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            st.button("forgot password?", type = "tertiary", use_container_width = True, help = "Not yet available")
        
        else:
            new_username = st.text_input("A", label_visibility = "hidden", placeholder = "Choose a remarkable username")
            new_password = st.text_input("A", label_visibility = "collapsed", placeholder = "Create a password", type = "password")
            confirm_password = st.text_input("A", label_visibility = "collapsed", placeholder = "Re-password", type = "password")

            for _ in range(4):
                st.text("")

            if st.button("Register", use_container_width = True, type = "primary"):
                if new_username != "":
                    if len(new_username) >= 5:
                        if new_password != "":
                            if len(new_password) >= 8:
                                if new_password == confirm_password:
                                    register_user(conn, c, new_username, new_password)
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

    if st.session_state.logged_in:
        st.sidebar.write(f"# Welcome, **{st.session_state.username}**!")
        
        with st.sidebar:
            wallet = c.execute('SELECT wallet FROM users WHERE user_id = ?', (st.session_state.user_id,)).fetchone()[0]
            st.sidebar.write(f"Wallet \a | \a :green[${format_currency(wallet)}]")
            st.sidebar.header(" ", divider = "rainbow")

            c1, c2 = st.sidebar.columns(2)
            if c1.button("Dashboard", type = "primary", use_container_width = True):
                st.session_state.current_menu = "Dashboard"
            
            if c2.button("Leaderboard", type = "primary", use_container_width = True):
                st.session_state.current_menu = "Leaderboard"
            
            if st.button("Inventory", type = "primary", use_container_width = True):
                st.session_state.current_menu = "Inventory"
            
            if st.button("Marketplace", use_container_width = True):
                st.session_state.current_menu = "Marketplace"
            
            if st.button("Transaction History", use_container_width = True):
                st.session_state.current_menu = "Transaction History"

            with st.expander("Accounts"):
                if st.button("Main Account", use_container_width = True):
                    st.session_state.current_menu = "Main Account"

                if st.button("Savings Account", use_container_width = True):
                    st.session_state.current_menu = "View Savings"
        
        st.sidebar.divider()

        if st.session_state.username in admins:
            if st.sidebar.button("Admin Panel", type = "secondary", use_container_width = True):
                st.session_state.current_menu = "Admin Panel"

        c1, c2 = st.sidebar.columns(2)

        if c1.button("Log Out", type = "secondary", use_container_width = True):
            st.session_state.current_menu = "Logout"

        if c2.button("Settings", type = "secondary", use_container_width = True):
            st.session_state.current_menu = "Settings"


############################################################################################################################################################################################################################################################################################################


        if st.session_state.current_menu == "Dashboard":
            # dashboard(c, conn, st.session_state.user_id)
            pass

        elif st.session_state.current_menu == "Leaderboard":
            leaderboard(c)
        
        elif st.session_state.current_menu == "Marketplace":
            marketplace_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Inventory":
            inventory_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Main Account":
            main_account_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Manage Pending Transfers":
            manage_pending_transfers(c, conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Transaction History":
            display_transaction_history(c, st.session_state.user_id)

        elif st.session_state.current_menu == "View Savings":
            savings_view(conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Logout":
            st.sidebar.info("Logging you out...")
            time.sleep(2.5)
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.current_menu = "Dashboard"
            st.rerun()

        elif st.session_state.current_menu == "Settings":
            settings(c, conn, st.session_state.username)

        elif st.session_state.current_menu == "Admin Panel":
                admin_panel(conn)

if __name__ == "__main__":
    conn = sqlite3.connect('eggggggggg.db')
    main(conn)
