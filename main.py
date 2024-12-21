# Simple Bank App Simulation.
# Copyright Ege Güvener, 20/12/2024

import streamlit as st
import sqlite3
import hashlib
import random
import time
import pandas as pd

st.set_page_config(
    page_title = "Bank Genova",
    page_icon = "🏦",
    layout = "centered",
    initial_sidebar_state = "expanded",
)

def hashPass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verifyPass(hashed_password, entered_password):
    return hashed_password == hashlib.sha256(entered_password.encode()).hexdigest()

admins = [
    "egegvner",
]

def init_db():
    conn = sqlite3.connect('Banker.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
              (userId INTEGER PRIMARY KEY NOT NULL,
              username TEXT NOT NULL UNIQUE,
              password TEXT NOT NULL,
              balance REAL DEFAULT 0,
              suspention INTEGER DEFAULT 0
              )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                    transactionId INTEGER PRIMARY KEY AUTOINCREMENT,
                    userId INTEGER NOT NULL,
                    type TEXT NOT NULL, 
                    amount REAL NOT NULL,
                    balance REAL NOT NULL,
                    toUsername TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (userId) REFERENCES users(userId)
                )''')
    
    conn.commit()
    return conn, c

def register_user(conn, c, username, password):
    try:
        hashed_password = hashPass(password)
        c.execute("INSERT INTO users (userId, username, password) VALUES (?, ?, ?)", (random.randint(100000, 999999), username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        st.error("Username already exists!")
        return False
        
def deposit(conn, c, uid, amount):
    if amount > 0 and amount <= 1000000:
        c.execute("UPDATE users SET balance = balance + ? WHERE userId = ?", (amount, uid))
        balance = c.execute('SELECT balance FROM users WHERE userId = ?', (uid,)).fetchone()[0]
        c.execute("INSERT INTO transactions (userId, type, amount, balance) VALUES (?, ?, ?, ?)", (uid, 'deposit', amount, balance))
        conn.commit()
        with st.spinner("Processing..."):
            time.sleep(random.uniform(0.1, 3))
            st.success(f"Successfully deposited ${amount:.2f}")
        time.sleep(2)
        st.rerun()

    else:
        st.error("Invalid deposit amount. Must be between $0 and $1,000,000.")

def withdraw(conn, c, uid, amount):
    current_balance = c.execute('SELECT balance FROM users WHERE userId = ?', (uid,)).fetchone()[0]
    if 0 < amount <= 1000000 and amount <= current_balance:
        c.execute("UPDATE users SET balance = balance - ? WHERE userId = ?", (amount, uid))
        balance = c.execute('SELECT balance FROM users WHERE userId = ?', (uid,)).fetchone()[0]
        c.execute("INSERT INTO transactions (userId, type, amount, balance) VALUES (?, ?, ?, ?)", (uid, 'withdrawal', amount, balance))
        conn.commit()
        with st.spinner("Processing..."):
            time.sleep(random.uniform(0.1, 3))
            st.success(f"Successfully withdrawn ${amount:.2f}")
        time.sleep(2)
        st.rerun()
    else:
        st.error("Invalid withdrawal amount. Must be between $0 and current balance, max $1,000,000.")

def transfer(conn, c, uid, to_username, amount):
    sender_username = c.execute("SELECT username FROM users WHERE userId = ?", (uid,)).fetchone()[0]
    receiver = c.execute("SELECT userId FROM users WHERE username = ?", (to_username,)).fetchone()
    
    if receiver:
        receiver_uid = receiver[0]
        current_balance = c.execute('SELECT balance FROM users WHERE userId = ?', (uid,)).fetchone()[0]
        
        if 0 < amount <= 1000000 and amount <= current_balance:
            c.execute("UPDATE users SET balance = balance - ? WHERE userId = ?", (amount, uid))
            sender_balance = c.execute("SELECT balance FROM users WHERE userId = ?", (uid,)).fetchone()[0]
            c.execute("INSERT INTO transactions (userId, type, amount, balance, toUsername) VALUES (?, ?, ?, ?, ?)", (uid, 'Transfer to', amount, sender_balance, to_username))
            
            c.execute("UPDATE users SET balance = balance + ? WHERE userId = ?", (amount, receiver_uid))
            receiver_balance = c.execute("SELECT balance FROM users WHERE userId = ?", (receiver_uid,)).fetchone()[0]
            c.execute("INSERT INTO transactions (userId, type, amount, balance, toUsername) VALUES (?, ?, ?, ?, ?)", (receiver_uid, f'Transfer from {sender_username}', amount, receiver_balance, sender_username))
            
            conn.commit()
            with st.spinner("Processing..."):
                time.sleep(random.uniform(0.1, 3))
                st.success(f"Successfully transferred ${amount:.2f} to {to_username}")
            time.sleep(2)
            st.rerun()
        else:
            st.error("Invalid transfer amount. Must be between $0 and current balance, max $1,000,000.")
    else:
        st.error(f"User {to_username} does not exist.")

def get_transaction_history(c, uid):
    transactions = c.execute("SELECT * FROM transactions WHERE userId = ? ORDER BY timestamp DESC", (uid,)).fetchall()
    return transactions

def adminPanel(conn):
    c = conn.cursor()
    st.divider()

    tempUser = st.selectbox(label="Select user", options=[user[0] for user in c.execute("SELECT username FROM users").fetchall()])
    if f"confirm_delete_{tempUser}" not in st.session_state:
        st.session_state[f"confirm_delete_{tempUser}"] = False

    if st.button(f"Delete {tempUser.capitalize()}", use_container_width=1, type="secondary"):
        st.session_state[f"confirm_delete_{tempUser}"] = True

    if st.session_state[f"confirm_delete_{tempUser}"]:
        st.error(f"Are you sure you want to delete {tempUser.capitalize()}? This action cannot be undone.")
        if st.button("Confirm Deletion", use_container_width=1):
            tempUserId = c.execute("SELECT userId FROM users WHERE username = ?", (tempUser,)).fetchone()
            if tempUserId:
                c.execute("DELETE FROM users WHERE username = ?", (tempUser,))
                c.execute("DELETE FROM transactions WHERE userId = ?", (tempUserId[0],))
                conn.commit()
                st.success(f"User {tempUser.capitalize()} and their associated data have been deleted.")
                st.session_state[f"confirm_delete_{tempUser}"] = False
                time.sleep(3)
                st.rerun()
            else:
                st.error(f"User {tempUser.capitalize()} not found in the database!")
                st.session_state[f"confirm_delete_{tempUser}"] = False
    
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
                        UPDATE transactions 
                        SET type = ?, amount = ?, balance = ?, toUsername = ? 
                        WHERE transactionId = ?
                    """, (row["Type"], row["Amount"], row["Balance"], row["To Username"], row["Transaction ID"]))
                conn.commit()
                st.success("Transactions updated successfully.")
                st.rerun()
            
            st.text("")
            transaction_id_to_delete = st.number_input("Enter Transaction ID to Delete", min_value=0, step=1)
            if st.button("Delete Transaction", use_container_width = 1):
                c.execute("DELETE FROM transactions WHERE transactionId = ?", (transaction_id_to_delete,))
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
        userData = c.execute("SELECT userId, username, balance, suspention FROM users")
        time.sleep(1)
    df = pd.DataFrame(userData, columns = ["User ID", "Username", "Balance", "Suspention"])
    edited_df = st.data_editor(df, key = "edit_table", num_rows = "fixed", use_container_width = 1, hide_index = False)
    for MrBob in range(4):
        st.text("")

    if st.button("Update Data", use_container_width=1, type="secondary"):
        for _, row in edited_df.iterrows():
            c.execute("UPDATE OR IGNORE users SET username = ?, balance = ?, suspention = ? WHERE userId = ?", (row["username"], row["balance"], row["suspention"], row["userId"]))
        conn.commit()
        with st.spinner("Processing Changes..."):
            time.sleep(3)
        st.success("User data updated.")
        st.rerun()

def main():

    st.title("🏦 Bank :red[Genova] ™", anchor = False)

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
            for MrHoolin in range(4):
                st.text("")
            if st.button("**Log Me In**", use_container_width = 1, type="primary"):
                user = c.execute("SELECT userId, password FROM users WHERE username = ?", (username,)).fetchone()
                if user and verifyPass(user[1], password):
                    if c.execute("SELECT suspention FROM users WHERE username = ?", (username,)).fetchone()[0] == 1:
                        st.error("Your account has been suspended. Please contact admin (Ege).")
                    else:
                        with st.spinner("Logging you in..."):
                            st.session_state.logged_in = True
                            st.session_state.user_id = user[0]
                            st.session_state.username = username
                            time.sleep(2)
                    time.sleep(4)
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            st.button("forgot password?", type = "tertiary", use_container_width = 1)
        
        else:
            new_username = st.text_input("A", label_visibility="hidden", placeholder="Choose a remarkable username")
            new_password = st.text_input("A", label_visibility="collapsed", placeholder="Create a password", type="password")
            confirm_password = st.text_input("A", label_visibility="collapsed", placeholder="Re-password", type="password")
            for i in range(4):
                st.text("")

            if st.button("Register", use_container_width=1, type="primary"):
                if new_password != "":
                    if len(new_password) >= 8:
                        if new_password == confirm_password:
                            if register_user(conn, c, new_username, new_password):
                                with st.spinner("We are creating your account..."):
                                    time.sleep(3)
                                    st.balloons()
                                st.success("Success! You can now log in with your credentials!")
                        else:
                            st.error("Passwords do not match")
                    else:
                        st.error("Password must contain **at least** 8 chars.")
                else:
                    st.error("Empty password is illegal.")

    if st.session_state.logged_in:
        st.sidebar.title(f"Welcome, **{st.session_state.username.capitalize()}**!")
        
        balance = c.execute('SELECT balance FROM users WHERE userId = ?', (st.session_state.user_id,)).fetchone()[0]
        st.sidebar.success(f"Balance :green[${balance:.2f}]")
        for i in range(4):
            st.sidebar.text("")
        
        if st.sidebar.button("Deposit", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Deposit"
        
        if st.sidebar.button("Withdraw", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Withdraw"

        if st.sidebar.button("Transfer", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Transfer"

        if st.sidebar.button("Transaction History", type = "secondary", use_container_width = 1):
            st.session_state.current_menu = "Transaction History"

        for i in range(4):
            st.sidebar.text("")

        if st.session_state.username in admins:
            if st.sidebar.button("Admin Panel", type = "primary", use_container_width = 1):
                st.session_state.current_menu = "Admin Panel"
        else:
            st.sidebar.button("Admin Panel", type = "primary", use_container_width = 1, disabled = True, help = "Not Allowed")

        if st.sidebar.button("Log Out", type = "primary", use_container_width = 1):
            st.session_state.current_menu = "Logout"

        if st.session_state.current_menu == "Deposit":
            st.header("Deposit")
            st.text("")
            amount = st.number_input("*Amount*", min_value = 0.0, max_value = 1000000.0, step = 0.5)
            for i in range(4):
                st.text("")
            if st.button(":green[Deposit Funds]", use_container_width = 1, type="secondary"):
                deposit(conn, c, st.session_state.user_id, amount)
                
        elif st.session_state.current_menu == "Withdraw":
            st.header("Withdraw")
            amount = st.number_input("*Amount*", min_value = 0.0, max_value = 1000000.0, step = 0.5)
            for i in range(4):
                st.text("")
            if st.button(":red[Withdraw Funds]", use_container_width = 1, type = "secondary"):
                withdraw(conn, c, st.session_state.user_id, amount)

        elif st.session_state.current_menu == "Transfer":
            st.header("Transfer Funds")
            to_username = st.text_input("A", label_visibility = "hidden", placeholder = "Recipient username")
            amount = st.number_input("Amount to Transfer", min_value = 0.0, max_value = 1000000.0, step = 10.0)
            for i in range(4):
                st.text("")
            if st.button(":blue[Transfer]", use_container_width = 1, type = "secondary"):
                transfer(conn, c, st.session_state.user_id, to_username, amount)

        elif st.session_state.current_menu == "Transaction History":
            st.header("Transaction History")
            transactions = get_transaction_history(c, st.session_state.user_id)
            
            if transactions:
                for t in transactions:
                    transaction_type, amount, balance, timestamp = t[2], t[3], t[4], t[6]
                    to_username = t[5] if t[2] == "transfer" else "N/A"
                    
                    if transaction_type == "deposit":
                        st.success(f"Deposit | {timestamp}")
                        st.write(f"Amount: :green[+${amount:.2f}]")
                        st.write(f"New Balance: :green[${balance:.2f}]")

                    elif transaction_type == "withdrawal":
                        st.error(f"Withdrawal | {timestamp}")
                        st.write(f"Amount: :red[-${amount:.2f}]")
                        st.write(f"New Balance: :red[${balance:.2f}]")

                    elif "Transfer from" in transaction_type:
                        st.success(f"Transfer from {t[5].capitalize()} | {timestamp}")
                        st.write(f"Amount: :green[+${amount:.2f}]")
                        st.write(f"New Balance: :green[${balance:.2f}]")

                    elif "Transfer to" in transaction_type:
                        st.error(f"Transfer to {t[5].capitalize()} | {timestamp}")
                        st.write(f"Amount: :green[+${amount:.2f}]")
                        st.write(f"New Balance: :green[${balance:.2f}]")
                    
                    st.divider()
            else:
                st.write("No transactions found.")

        elif st.session_state.current_menu == "Logout":
            st.sidebar.info("Logging you out...")
            time.sleep(2)
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.current_menu = "Dashboard"
            st.rerun()

        elif st.session_state.current_menu == "Admin Panel":
            if st.session_state.username in admins:
                adminPanel(conn)
            else:
                st.error("You do not have permission to access the Admin Panel.")

if __name__ == "__main__":
    main()
