# Simple Bank App Simulation.
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

def hashPass(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def verifyPass(hashed_password, entered_password):
    # Ensure both are in bytes for bcrypt
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode()  # Convert to bytes if it's a string
    return bcrypt.checkpw(entered_password.encode(), hashed_password)

admins = [
    "egegvner",
    "believedreams",
]

def register_user(conn, c, username, password, email = None, visible_name = None):
    try:
        hashed_password = hashPass(password)
        
        c.execute('''INSERT INTO users (userId, username, visible_name, password, balance, suspension, deposits, withdraws, incoming_transfers, outgoing_transfers, total_transactions, last_transaction_time, email)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (
                   random.randint(100000, 999999), 
                   username, 
                   visible_name,
                   hashed_password, 
                   10,  # Default balance
                   0,   # Default suspension (0 = not suspended)
                   0,   # Default deposits
                   0,   # Default withdraws
                   0,   # Default incoming transfers
                   0,   # Default outgoing transfers
                   0,   # Default total transactions
                   None,
                   email
                   ))  # Default last transaction time
        
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
        return False
    except Exception as e:
        st.error(f"Error: {e}")
        return False
        
import sqlite3

def init_db():
    conn = sqlite3.connect('qq.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
                  userId INTEGER PRIMARY KEY NOT NULL,
                  username TEXT NOT NULL UNIQUE,
                  visible_name TEXT,
                  password TEXT NOT NULL,
                  balance REAL DEFAULT 10,
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
                  transactionId INTEGER PRIMARY KEY NOT NULL,
                  userId INTEGER NOT NULL,
                  type TEXT NOT NULL,
                  amount REAL NOT NULL,
                  balance REAL NOT NULL,
                  toUsername TEXT,
                  status TEXT DEFAULT 'pending',
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (userId) REFERENCES users(userId),
                  FOREIGN KEY (toUsername) REFERENCES users(username)
                  )''')

    c.execute('CREATE INDEX IF NOT EXISTS idx_userId ON transactions(userId)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON transactions(timestamp)')

    conn.commit()
    return conn, c

def change_password(c, conn, username, current_password, new_password):
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    real_password = result[0]
    if verifyPass(real_password, current_password):
        if new_password != "":
            if len(new_password) >= 8:
                hashed_new_password = hashPass(new_password)
                c.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_new_password, username))
                conn.commit()  # Commit the changes to the database
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

def check_cooldown(c, uid):
    last_transaction = c.execute("SELECT last_transaction_time FROM users WHERE userId = ?", (uid,)).fetchone()[0]
    if last_transaction:
        last_time = pd.to_datetime(last_transaction)
        current_time = pd.Timestamp.now()
        time_diff = (current_time - last_time).total_seconds()
        if time_diff < 60:
            st.warning(f"Cooldown in effect. Please wait {60 - int(time_diff)} seconds before your next transaction.")
            return False
    return True

def update_last_transaction_time(c, conn, uid):
    current_time = pd.Timestamp.now()
    current_time_dt = current_time.to_pydatetime()
    current_time_str = current_time_dt.isoformat()
    c.execute("UPDATE users SET last_transaction_time = ? WHERE userId = ?", (current_time_str, uid))

    conn.commit()

def recent_transactions_metrics(c, uid):
    current_time = pd.Timestamp.now()
    last_24_hours = current_time - pd.Timedelta(days = 1)

    transactions = c.execute("SELECT type, COUNT(*), SUM(amount) FROM transactions WHERE userId = ? AND timestamp >= ? GROUP BY type", (uid, last_24_hours.strftime('%Y-%m-%d %H:%M:%S'))).fetchall()

    metrics = {
        "Deposits": {"count": 0, "total": 0},
        "Withdrawals": {"count": 0, "total": 0},
        "Incoming Transfers": {"count": 0, "total": 0},
        "Outgoing Transfers": {"count": 0, "total": 0},
    }

    for trans_type, count, total in transactions:
        if "deposit" in trans_type.lower():
            metrics["Deposits"] = {"count": count, "total": total}
        elif "withdrawal" in trans_type.lower():
            metrics["Withdrawals"] = {"count": count, "total": total}
        elif "Transfer to" in trans_type:
            metrics["Outgoing Transfers"] = {"count": count, "total": total}
        elif "Transfer from" in trans_type:
            metrics["Incoming Transfers"] = {"count": count, "total": total}

    return metrics

def dashboard(c, conn, uid):
    st.header("Dashboard Overview")
    
    deposits, withdrawals, incoming, outgoing = (
        c.execute("SELECT deposits, withdraws, incoming_transfers, outgoing_transfers FROM users WHERE userId = ?", (uid,)).fetchone()
    )
    
    total_transactions = deposits + withdrawals + incoming + outgoing
    recent_metrics = recent_transactions_metrics(c, uid)

    st.divider()
    st.subheader("Lifetime Metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Deposits", deposits)
    c2.metric("Withdrawals", withdrawals)
    c3.metric("Incoming Transfers", incoming)
    c4.metric("Outgoing Transfers", outgoing)
    c5.metric("Total Transactions", total_transactions)

    st.divider()
    st.subheader("Last 24 Hours")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Deposits (24h)", recent_metrics["Deposits"]["count"], f"${recent_metrics['Deposits']['total']:.2f}")
    c2.metric("Withdrawals (24h)", recent_metrics["Withdrawals"]["count"], f"${recent_metrics['Withdrawals']['total']:.2f}")
    c3.metric("Incoming Transfers (24h)", recent_metrics["Incoming Transfers"]["count"], f"${recent_metrics['Incoming Transfers']['total']:.2f}")
    c4.metric("Outgoing Transfers (24h)", recent_metrics["Outgoing Transfers"]["count"], f"${recent_metrics['Outgoing Transfers']['total']:.2f}")

    st.divider()
    st.subheader("Balance Trend")
    transactions = c.execute("SELECT timestamp, balance FROM transactions WHERE userId = ? ORDER BY timestamp ASC", (uid,)).fetchall()
    if transactions:
        df = pd.DataFrame(transactions, columns = ["Timestamp", "Balance"])
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        st.line_chart(df.set_index("Timestamp")["Balance"])
    else:
        st.info("No transaction data available for trends.")

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

def leaderboard(c):
    st.divider()
    st.header("🏆 Leaderboard")
    leaderboard_data = leaderboard_logic(c)

    if leaderboard_data:
        st.table([{"Rank": user["rank"], "Name": user["name"], "Balance": f"${user['balance']:.2f}"} for user in leaderboard_data])
    else:
        st.write("No users found in the database!")

def deposit(conn, c, uid, amount):
    if check_cooldown(c, uid):
        balance = c.execute('SELECT balance FROM users WHERE userId = ?', (uid,)).fetchone()[0]
        if amount > 0:
            if amount <= (((balance / 100) * 75)):
                c.execute("UPDATE users SET balance = balance + ?, deposits = deposits + 1 WHERE userId = ?", (amount, uid))
                c.execute("INSERT INTO transactions (transactionId, userId, type, amount, balance) VALUES (?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), uid, 'deposit', amount, balance))
                update_last_transaction_time(c, conn, uid)
                conn.commit()
                with st.spinner("Processing..."):
                    time.sleep(random.uniform(0.1, 2))
                    st.success(f"Successfully deposited ${amount:.2f}")
                time.sleep(2)
                st.rerun()
            else:
                st.warning("Your deposit must not exceed **%75** of your current balance.")
        else:
            st.error("Invalid deposit amount. Must be between $0 and $1,000,000.")

def withdraw(conn, c, uid, amount):
    if check_cooldown(c, uid):
        current_balance = c.execute('SELECT balance FROM users WHERE userId = ?', (uid,)).fetchone()[0]
        if 0 < amount <= 1000000 and amount <= current_balance:
            c.execute("UPDATE users SET balance = balance - ?, withdraws = withdraws + 1 WHERE userId = ?", (amount, uid))
            balance = c.execute('SELECT balance FROM users WHERE userId = ?', (uid,)).fetchone()[0]
            c.execute("INSERT INTO transactions (transactionId, userId, type, amount, balance) VALUES (?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), uid, 'withdrawal', amount, balance))
            update_last_transaction_time(c, conn, uid)
            conn.commit()
            with st.spinner("Processing..."):
                time.sleep(random.uniform(0.1, 2))
                st.success(f"Successfully withdrawn ${amount:.2f}")
            time.sleep(2)
            st.rerun()
        else:
            st.error("Invalid withdrawal amount. Must be between 0 and current balance, max 1,000,000.")

def transfer(conn, c, uid, to_username, amount):
    receiver_uid = c.execute("SELECT userId FROM users WHERE username = ?", (to_username,)).fetchone()

    if receiver_uid:
        receiver_uid = receiver_uid[0]

        existing_transfer = c.execute("""
            SELECT COUNT(*)
            FROM transactions
            WHERE userId = ? AND toUsername = ? AND status = 'pending'
        """, (uid, to_username)).fetchone()[0]
        
        if existing_transfer > 0:
            st.warning(f"A pending transfer to {to_username} already exists. Please wait for it to be accepted or rejected.")
            return

        current_balance = c.execute("SELECT balance FROM users WHERE userId = ?", (uid,)).fetchone()[0]

        if 0 < amount <= 1000000 and amount <= current_balance:
            c.execute("UPDATE users SET balance = balance - ? WHERE userId = ?", (amount, uid))
            c.execute("INSERT INTO transactions (transactionId, userId, type, amount, balance, toUsername, status) VALUES (?, ?, ?, ?, ?, ?, ?)", (random.randint(100000000000, 999999999999), uid, f'Transfer to {to_username}', amount, current_balance, to_username, 'pending'))
            
            conn.commit()
            with st.spinner("Processing"):
                time.sleep(2)
            st.success(f"Successfully initiated transfer of ${amount:.2f} to {to_username}. Awaiting acceptance.")
            time.sleep(2.5)
            st.rerun()
        else:
            st.error("Invalid transfer amount. Must be within current balance and below $1,000,000.")
    else:
        st.error(f"User {to_username} does not exist.")

def manage_pending_transfers(c, conn, receiver_id):
    st.header("📥 Pending Transfers")
    st.divider()

    pending_transfers = c.execute("""
        SELECT transactionId, userId, amount, timestamp
        FROM transactions
        WHERE toUsername = (SELECT username FROM users WHERE userId = ?) AND status = 'pending'
    """, (receiver_id,)).fetchall()

    if not pending_transfers:
        st.write("No pending transfers.")
        return

    for transaction in pending_transfers:
        transaction_id, sender_id, amount, timestamp = transaction
        sender_username = c.execute("SELECT username FROM users WHERE userId = ?", (sender_id,)).fetchone()[0]

        st.subheader(f" 💸 **{sender_username}** wants to transfer **${amount:.2f}** ({timestamp}).", divider="rainbow")
        col1, col2 = st.columns(2)

        if col1.button(f"Accept", type = "primary", use_container_width = 1, key = transaction_id):
            with st.spinner("Accepting Transfer"):
                c.execute("UPDATE transactions SET status = 'accepted' WHERE transactionId = ?", (transaction_id,))
                c.execute("UPDATE users SET balance = balance + ? WHERE userId = ?", (amount, receiver_id))
                conn.commit()
                time.sleep(2)
            st.toast("Transfer accepted!")
            time.sleep(2)
            st.rerun()

        if col2.button(f"Reject", use_container_width = 1, key = transaction_id + 1):
            with st.spinner("Rejecting Transfer"):
                c.execute("UPDATE transactions SET status = 'rejected' WHERE transactionId = ?", (transaction_id,))
                c.execute("UPDATE users SET balance = balance + ? WHERE userId = ?", (amount, sender_id))
                conn.commit()
                time.sleep(2)
            st.toast("Transfer rejected!")
            time.sleep(2)
            st.rerun()

        st.divider()

def get_transaction_history(c, user_id):
    username = c.execute("SELECT username FROM users WHERE userId = ?", (user_id,)).fetchone()[0]

    sender_query = """
        SELECT 'sent' AS role, type, amount, balance, timestamp, status, toUsername
        FROM transactions
        WHERE userId = ?
        ORDER BY timestamp DESC
    """
    sent_transactions = c.execute(sender_query, (user_id,)).fetchall()

    receiver_query = """
        SELECT 'received' AS role, type, amount, balance, timestamp, status, userId AS fromUserId
        FROM transactions
        WHERE toUsername = ?
        ORDER BY timestamp DESC
    """
    received_transactions = c.execute(receiver_query, (username,)).fetchall()

    return sent_transactions, received_transactions

def display_transaction_history(c, user_id):
    st.header("Transaction History")

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
            to_username = t[6] if role == "sent" else "N/A"
            from_username = (
                c.execute("SELECT username FROM users WHERE userId = ?", (t[6],)).fetchone()[0]
                if role == "received" else "N/A"
            )

            if t_type == "deposit":
                st.success(f"Deposit | {timestamp}", icon = "💵")
                st.write(f"Amount: :green[+${amount:.2f}]")
                st.write(f"New Balance: :green[${balance:.2f}]")

            elif t_type == "withdrawal":
                st.error(f"Withdrawal | {timestamp}", icon = "💵")
                st.write(f"Amount: :red[-${amount:.2f}]")
                st.write(f"New Balance: :red[${balance:.2f}]")

            elif role == "sent" and t_type.startswith("Transfer to"):
                st.error(f"Transfer to {to_username.capitalize()} | {timestamp} (Status: **{status.capitalize()}**)", icon = "💸")
                st.write(f"Amount: :red[-${amount:.2f}]")
                st.write(f"New Balance: :red[${balance:.2f}]")

            elif role == "received":
                st.success(f"Transfer from {from_username.capitalize()} | {timestamp} (Status: **{status.capitalize()}**)", icon = "💸")
                st.write(f"Amount: :green[+${amount:.2f}]")
                st.write(f"New Balance: :green[${balance:.2f}]")

            else:
                st.warning(f"Other Transaction | {timestamp} (Status: {status})")
                st.write(f"Amount: ${amount}")
                st.write(f"Balance: ${balance:.2f}")

            st.divider()
    else:
        st.info("No transactions found in your history.")

def admin_panel(conn):
    c = conn.cursor()
    st.divider()
    st.header("User Removal")
    
    users = c.execute("SELECT username FROM users").fetchall()
    if not users:
        st.warning("No users found in the database.")
        return
    
    tempUser = st.selectbox(label="Select user", options=[user[0] for user in users])
    
    tempUserId = c.execute("SELECT userId FROM users WHERE username = ?", (tempUser,)).fetchone()
    
    if st.button(f"Delete {tempUser.capitalize()}", type="secondary", use_container_width=1):
        if tempUserId:
            c.execute("DELETE FROM users WHERE username = ?", (tempUser,))
            c.execute("DELETE FROM transactions WHERE userId = ?", (tempUserId[0],))
            conn.commit()
            
            st.success(f"User {tempUser.capitalize()} and their associated data have been deleted.")
            time.sleep(2)
            st.rerun()
        else:
            st.error(f"User {tempUser.capitalize()} not found in the database!")

    st.divider()
    st.header("Manage User Transactions")
    st.text("")

    user = st.selectbox("Select User", [u[0] for u in c.execute("SELECT username FROM users").fetchall()])
    if user:
        user_id = c.execute("SELECT userId FROM users WHERE username = ?", (user,)).fetchone()[0]
        transactions = c.execute("SELECT * FROM transactions WHERE userId = ? ORDER BY timestamp DESC", (user_id,)).fetchall()

        if transactions:
            df = pd.DataFrame(transactions, columns = ["Transaction ID", "User ID", "Type", "Amount", "Balance", "To Username", "Timestamp"])
            edited_df = st.data_editor(df, key = "transaction_editor", num_rows = "fixed", use_container_width = 1, hide_index = False)
            
            if st.button("Update Transaction(s)", use_container_width = 1):
                for _, row in edited_df.iterrows():
                    c.execute("""
                        UPDATE OR IGNOREtransactions 
                        SET type = ?, amount = ?, balance = ?, toUsername = ? 
                        WHERE transactionId = ?
                    """, (row["Type"], row["Amount"], row["Balance"], row["To Username"], row["Transaction ID"]))
                conn.commit()
                st.success("Transactions updated successfully.")
                st.rerun()
            
            st.text("")
            transaction_id_to_delete = st.number_input("Enter Transaction ID to Delete", min_value=0, step=1)
            if st.button("Delete Transaction", use_container_width = 1):
                with st.spinner("Processing..."):
                    c.execute("DELETE FROM transactions WHERE transactionId = ?", (transaction_id_to_delete,))
                    time.sleep(2)
                conn.commit()
                st.success(f"Transaction {transaction_id_to_delete} deleted successfully.")
                st.rerun()

        else:
            st.write(f"No transactions found for {user}.")

    st.divider()
    st.header("Users")
    st.text("")
    st.write(":red[Editing data from the dataframe below without proper permission will trigger a legal punishment by law.]")
    with st.spinner("Loading User Data"):
        userData = c.execute("SELECT userId, username, visible_name, password, balance, suspension, deposits, withdraws, incoming_transfers, outgoing_transfers, total_transactions, last_transaction_time, email FROM users").fetchall()
        time.sleep(1)
    df = pd.DataFrame(userData, columns = ["User ID", "Username", "Visible Name", "Pass", "Balance", "Suspension", "Deposits", "Withdraws", "Transfers Received", "Transfers Sent", "Total Transactions", "Last Transaction Time", "Email"])
    edited_df = st.data_editor(df, key = "edit_table", num_rows = "fixed", use_container_width = 1, hide_index = False)

    for _ in range(4):
        st.text("")

    if st.button("Update Data", use_container_width = 1, type = "secondary"):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE users SET username = ?, visible_name = ?, password = ?, balance = ?, suspension = ?, deposits = ?, withdraws = ?, incoming_transfers = ?, outgoing_transfers = ?, total_transactions = ?, last_transaction_time = ?, email = ? WHERE userId = ?", (row["Username"], row["Visible Name"], row["Pass"], row["Balance"], row["Suspension"], row["Deposits"], row["Withdraws"], row["Transfers Received"], row["Transfers Sent"], row["Total Transactions"], row["Last Transaction Time"], row["Email"], row["User ID"]))
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

    st.button("Ege Güvener • © 2024", type = "tertiary", use_container_width = 1, disabled = True)

def main(conn):
    c = conn.cursor()

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

            if st.button("**Log In**", use_container_width = 1, type="primary"):
                user = c.execute("SELECT userId, password FROM users WHERE username = ?", (username,)).fetchone()
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
            st.button("forgot password?", type = "tertiary", use_container_width = 1, help = "Not yet available")
        
        else:
            new_username = st.text_input("A", label_visibility = "hidden", placeholder = "Choose a remarkable username")
            new_password = st.text_input("A", label_visibility = "collapsed", placeholder = "Create a password", type = "password")
            confirm_password = st.text_input("A", label_visibility = "collapsed", placeholder = "Re-password", type = "password")

            for _ in range(4):
                st.text("")

            if st.button("Register", use_container_width = 1, type = "primary"):
                if new_username != "":
                    if len(new_username) >= 5:
                        if new_password != "":
                            if len(new_password) >= 8:
                                if new_password == confirm_password:
                                    if register_user(conn, c, new_username, new_password):
                                        with st.spinner("We are creating your account..."):
                                            time.sleep(2)
                                            st.balloons()
                                        st.success("Success! You can now log in with your credentials!")
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
        st.sidebar.title(f"Welcome, **{st.session_state.username}**!")
        
        balance = c.execute('SELECT balance FROM users WHERE userId = ?', (st.session_state.user_id,)).fetchone()[0]
        st.sidebar.success(f"Balance :green[${balance:.2f}]")

        c1, c2 = st.sidebar.columns(2)
        if c1.button("Dashboard", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Dashboard"

        if c2.button("Leaderboard", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Leaderboard"
        
        st.sidebar.divider()

        c1, c2 = st.sidebar.columns(2)
        
        if c1.button("Deposit", type = "primary", use_container_width = 1):
            st.session_state.current_menu = "Deposit"
        
        if c2.button("Withdraw", type = "primary", use_container_width = 1):
            st.session_state.current_menu = "Withdraw"

        c1, c2 = st.sidebar.columns(2)

        if c1.button("Transfer", type = "primary", use_container_width = 1):
            st.session_state.current_menu = "Transfer"

        if c2.button("Pendings", type = "primary", use_container_width = 1):
            st.session_state.current_menu = "Manage Pending Transfers"

        if st.sidebar.button("Transaction History", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Transaction History"

        st.sidebar.divider()

        if st.session_state.username in admins:
            if st.sidebar.button("Admin Panel", type = "secondary", use_container_width = 1):
                st.session_state.current_menu = "Admin Panel"
        else:
            st.sidebar.button("Admin Panel", type = "primary", use_container_width = 1, disabled = True, help = "Not Allowed")

        c1, c2 = st.sidebar.columns(2)

        if c1.button("Log Out", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Logout"

        if c2.button("Settings", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Settings"

        if st.session_state.current_menu == "Dashboard":
            dashboard(conn, c, st.session_state.user_id)

        if st.session_state.current_menu == "Leaderboard":
            leaderboard(c)

        if st.session_state.current_menu == "Deposit":
            b = c.execute("SELECT balance FROM users WHERE userId = ?", (st.session_state.user_id,)).fetchone()[0]
            st.header("Deposit")
            st.text("")
            amount = st.number_input("*Amount*", min_value = 0.0, max_value = 1000000.0, step = 0.5)
            st.write(f"Current max deposit: :green[${((b / 100) * 75):.2f}]")

            for _ in range(4):
                st.text("")

            if st.button(":green[Deposit Funds]", use_container_width = 1, type = "secondary"):
                deposit(conn, c, st.session_state.user_id, amount)
                
        elif st.session_state.current_menu == "Withdraw":
            st.header("Withdraw")
            amount = st.number_input("*Amount*", min_value = 0.0, max_value = 1000000.0, step = 0.5)
            
            for _ in range(4):
                st.text("")

            if st.button(":red[Withdraw Funds]", use_container_width = 1, type = "secondary"):
                withdraw(conn, c, st.session_state.user_id, amount)

        elif st.session_state.current_menu == "Transfer":
            st.header("Transfer Funds")
            all_users = c.execute("SELECT username FROM users")
            to_username = st.selectbox("A", label_visibility = "hidden", options = all_users, placeholder = "Receiver username")
            amount = st.number_input("Amount to Transfer", min_value = 0.0, max_value = 1000000.0, step = 10.0)
            
            for _ in range(4):
                st.text("")

            if st.button(":blue[Transfer]", use_container_width = 1, type = "secondary"):
                if st.session_state.username != to_username:
                    transfer(conn, c, st.session_state.user_id, to_username, amount)
                else:
                    st.warning("Why would you transfer money to yourself?")

        elif st.session_state.current_menu == "Manage Pending Transfers":
            manage_pending_transfers(c, conn, st.session_state.user_id)

        elif st.session_state.current_menu == "Transaction History":
            display_transaction_history(c, st.session_state.user_id)

        elif st.session_state.current_menu == "Logout":
            st.sidebar.info("Logging you out...")
            time.sleep(2)
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.current_menu = "Dashboard"
            st.rerun()

        elif st.session_state.current_menu == "Settings":
            settings(c, conn, st.session_state.username)

        elif st.session_state.current_menu == "Admin Panel":
            if st.session_state.username in admins:
                admin_panel(conn)
            else:
                st.error("You do not have permission to access the Admin Panel.")

if __name__ == "__main__":
    conn = sqlite3.connect('qq.db')
    main(conn)
