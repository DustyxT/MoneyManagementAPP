from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import datetime
import pandas as pd

app = Flask(__name__)
DB_NAME = 'finance.db'

# --- Database Management ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Transactions
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            type TEXT, 
            category TEXT,
            amount REAL,
            description TEXT
        )
    ''')
    # Categories
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            group_type TEXT
        )
    ''')
    # Budgets
    c.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            amount REAL,
            month TEXT,
            UNIQUE(category, month)
        )
    ''')
    conn.commit()
    conn.close()
    seed_categories()

def seed_categories():
    initial_categories = [
        ('Part-time Job', 'Income'), ('Scholarship', 'Income'), ('Other Income', 'Income'),
        ('Rent', 'Bill'), ('Phone Plan', 'Bill'), ('Internet', 'Bill'), ('Utilities (Water/Elec)', 'Bill'), ('Health Cover (OSHC)', 'Bill'), ('Tuition Fees', 'Bill'),
        ('Groceries', 'Expense'), ('Transport (Myki)', 'Expense'), ('Eat Out', 'Expense'), ('Shopping', 'Expense'), ('Entertainment', 'Expense'), ('University Materials', 'Expense'), ('International Calls', 'Expense'), ('Remittance (Parents)', 'Expense'),
        ('Emergency Fund', 'Saving'), ('Travel Fund', 'Saving'), ('Return Ticket', 'Saving'),
        ('Student Loan', 'Debt'), ('Credit Card', 'Debt')
    ]
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for cat, grp in initial_categories:
        try:
            c.execute('INSERT INTO categories (name, group_type) VALUES (?, ?)', (cat, grp))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()

def add_transaction_db(date, type, category, amount, description):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT INTO transactions (date, type, category, amount, description) VALUES (?, ?, ?, ?, ?)',
              (date, type, category, amount, description))
    conn.commit()
    conn.close()

def set_budget_db(category, amount, month='DEFAULT'):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO budgets (category, amount, month) VALUES (?, ?, ?)
        ON CONFLICT(category, month) DO UPDATE SET amount=excluded.amount
    ''', (category, amount, month))
    conn.commit()
    conn.close()

def get_budget_vs_actual(start_date, end_date, days_ratio=1.0):
    conn = sqlite3.connect(DB_NAME)
    # Categories
    cats_df = pd.read_sql_query("SELECT name as category, group_type FROM categories", conn)
    # Budgets (Default)
    defs_df = pd.read_sql_query("SELECT category, amount as full_budget FROM budgets WHERE month = 'DEFAULT'", conn)
    # Actuals
    query = "SELECT category, SUM(amount) as actual FROM transactions WHERE date >= ? AND date <= ? GROUP BY category"
    actuals_df = pd.read_sql_query(query, conn, params=(str(start_date), str(end_date)))
    conn.close()

    df = pd.merge(cats_df, defs_df, on='category', how='left').fillna(0.0)
    df = pd.merge(df, actuals_df, on='category', how='left').fillna(0.0)
    
    df['budgeted'] = df['full_budget'] * days_ratio
    
    # Calculate Diff
    df['diff'] = 0.0
    # For Income/Saving: Positive diff means Actual > Budget (Good/Normal)
    mask_pos = df['group_type'].isin(['Income', 'Saving'])
    df.loc[mask_pos, 'diff'] = df.loc[mask_pos, 'actual'] - df.loc[mask_pos, 'budgeted']
    # For Expense/Bill/Debt: Positive diff means Budget > Actual (Under Budget - Good)
    mask_neg = df['group_type'].isin(['Bill', 'Expense', 'Debt'])
    df.loc[mask_neg, 'diff'] = df.loc[mask_neg, 'budgeted'] - df.loc[mask_neg, 'actual']
    
    # Usage %
    df['usage'] = df.apply(lambda x: (x['actual'] / x['budgeted'] * 100) if x['budgeted'] > 0 else (100 if x['actual'] > 0 else 0), axis=1)
    
    return df

def delete_transaction_db(tx_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM transactions WHERE id = ?', (tx_id,))
    conn.commit()
    conn.close()

# --- Routes ---

@app.route('/')
def daily():
    date_str = request.args.get('date', str(datetime.date.today()))
    try:
        selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = datetime.date.today()

    pretty_date = selected_date.strftime("%d %B %Y")
    
    # Get Data for just this day
    # Ratio = 1/30.44 approx for daily budget from monthly
    df = get_budget_vs_actual(selected_date, selected_date, days_ratio=1/30.44)
    
    # KPI Totals
    total_income = df[df['group_type'] == 'Income']['actual'].sum()
    total_spend = df[df['group_type'].isin(['Bill', 'Expense', 'Debt'])]['actual'].sum()
    expense_budget_daily = df[df['group_type'].isin(['Bill', 'Expense', 'Debt'])]['budgeted'].sum()
    total_saved = df[df['group_type'] == 'Saving']['actual'].sum()
    
    expense_left = expense_budget_daily - total_spend
    net_balance = total_income - total_spend - total_saved
    
    # Group Data for Tables
    grouped_data = {}
    for grp in ['Income', 'Bill', 'Expense', 'Saving', 'Debt']:
        subset = df[df['group_type'] == grp].sort_values('category')
        grouped_data[grp] = subset.to_dict('records')

    # Fetch daily transactions for list view
    conn = sqlite3.connect(DB_NAME)
    tx_df = pd.read_sql_query("SELECT * FROM transactions WHERE date = ? ORDER BY id DESC", conn, params=(date_str,))
    conn.close()
    daily_transactions = tx_df.to_dict('records')

    return render_template('daily.html', 
                           selected_date=date_str,
                           pretty_date=pretty_date,
                           total_income=total_income,
                           total_spend=total_spend,
                           total_saved=total_saved,
                           net_balance=net_balance,
                           expense_left=expense_left,
                           grouped_data=grouped_data,
                           daily_transactions=daily_transactions)

@app.route('/update_daily_budget', methods=['POST'])
def update_daily_budget():
    date_str = request.form.get('date')
    ratio = 1/30.44
    
    conn = sqlite3.connect(DB_NAME)

    # iterate inputs
    for key, value in request.form.items():
        # Handle Budget Updates
        if key.startswith('budget_'):
            cat_name = key.replace('budget_', '')
            try:
                val = float(value)
                # Save as Monthly (Daily / (1/30.44) = Daily * 30.44)
                monthly_val = val / ratio
                # Use a separate simplified connection or function if needed, but here:
                # We can't use set_budget_db because it opens its own connection.
                # Inline the SQL for efficiency or re-open. Re-opening is safer for simplicity.
                set_budget_db(cat_name, monthly_val)
            except ValueError:
                pass
        
        # Handle Actual Updates (Reconciliation)
        elif key.startswith('actual_'):
            cat_name = key.replace('actual_', '')
            try:
                new_total = float(value)
                
                # Fetch current sum for this day/category
                cur = conn.cursor()
                cur.execute("SELECT SUM(amount) FROM transactions WHERE date = ? AND category = ?", (date_str, cat_name))
                res = cur.fetchone()
                current_total = res[0] if res[0] is not None else 0.0
                
                diff = new_total - current_total
                
                # If there's a meaningful difference, insert an adjustment transaction
                if abs(diff) > 0.001:
                    # Determine Type (Income vs Expense)
                    cur.execute("SELECT group_type FROM categories WHERE name = ?", (cat_name,))
                    grp_res = cur.fetchone()
                    grp_type = grp_res[0] if grp_res else 'Expense'
                    tx_type = 'Income' if grp_type == 'Income' else 'Expense'
                    
                    description = "Daily Manager Adjustment"
                    cur.execute('INSERT INTO transactions (date, type, category, amount, description) VALUES (?, ?, ?, ?, ?)',
                                (date_str, tx_type, cat_name, diff, description))
                    conn.commit()
            except ValueError:
                pass

    conn.close()         
    return redirect(url_for('daily', date=date_str))

@app.route('/add_transaction', methods=['POST'])
def add_transaction_route():
    date_str = request.form.get('date')
    group = request.form.get('group')
    category = request.form.get('category')
    amount = float(request.form.get('amount', 0))
    desc = request.form.get('description', '')
    
    # Map group to Type (Income vs Expense)
    tx_type = 'Income' if group == 'Income' else 'Expense'
    
    # Check if category exists, if not add it
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM categories WHERE name = ?", (category,))
    if not c.fetchone():
        c.execute("INSERT INTO categories (name, group_type) VALUES (?, ?)", (category, group))
        conn.commit()
    conn.close()
    
    add_transaction_db(date_str, tx_type, category, amount, desc)
    
    return redirect(url_for('daily', date=date_str))

@app.route('/delete_transaction/<int:id>', methods=['POST'])
def delete_transaction(id):
    date_str = request.args.get('date', str(datetime.date.today()))
    next_url = request.args.get('next')
    delete_transaction_db(id)
    if next_url:
        return redirect(next_url)
    return redirect(url_for('logs', date=date_str))

@app.route('/clear_daily_category', methods=['POST'])
def clear_daily_category():
    date_str = request.form.get('date')
    category = request.form.get('category')
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE date = ? AND category = ?", (date_str, category))
    conn.commit()
    conn.close()
    
    return redirect(url_for('daily', date=date_str))
    if next_url:
        return redirect(next_url)
    return redirect(url_for('logs', date=date_str))

@app.route('/reports')
def reports():
    view_by = request.args.get('view_by', 'Monthly')
    year = int(request.args.get('year', datetime.date.today().year))
    month_name = request.args.get('month', datetime.date.today().strftime('%b'))
    
    # Calculate Range
    if view_by == 'Monthly':
        m_idx = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].index(month_name) + 1
        start_date = datetime.date(year, m_idx, 1)
        # End of month
        if m_idx == 12:
            end_date = datetime.date(year, 12, 31)
        else:
            end_date = datetime.date(year, m_idx + 1, 1) - datetime.timedelta(days=1)
        ratio = 1.0
        report_title = start_date.strftime("%B %Y")
        
    elif view_by == 'Weekly':
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=today.weekday())
        end_date = start_date + datetime.timedelta(days=6)
        ratio = 7/30.44
        report_title = f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"

    else: # Daily
        start_date = datetime.date.today()
        end_date = start_date
        ratio = 1/30.44
        report_title = start_date.strftime("%d %B %Y")

    df = get_budget_vs_actual(start_date, end_date, days_ratio=ratio)
    
    # Metrics
    out_mask = df['group_type'].isin(['Bill', 'Expense', 'Debt'])
    total_budget_out = df[out_mask]['budgeted'].sum()
    total_spent = df[out_mask]['actual'].sum()
    remaining_budget = total_budget_out - total_spent
    budget_used_pct = (total_spent / total_budget_out * 100) if total_budget_out > 0 else 0
    
    spending_pace = "Normal" # Placeholder logic
    if budget_used_pct > 100: spending_pace = "Critical"
    elif budget_used_pct > 80: spending_pace = "High"
    elif budget_used_pct < 20: spending_pace = "Low"

    # Charts Data
    # Top Expenses
    top_expenses_df = df[out_mask & (df['actual'] > 0)].sort_values('actual', ascending=False).head(5)
    top_expenses = []
    for _, row in top_expenses_df.iterrows():
        pct = (row['actual'] / total_budget_out * 100) if total_budget_out > 0 else 0
        top_expenses.append({'name': row['category'], 'amount': row['actual'], 'pct': pct})

    # Donut Composition
    grp_sum = df.groupby('group_type')['actual'].sum()
    total_flow = grp_sum.sum()
    
    def get_pct(grp):
        return (grp_sum.get(grp, 0) / total_flow * 100) if total_flow > 0 else 0

    income_pct = get_pct('Income')
    expense_pct = get_pct('Expense')
    bill_pct = get_pct('Bill')
    debt_pct = get_pct('Debt')
    saving_pct = get_pct('Saving')

    return render_template('reports.html',
                           view_by=view_by, year=year, month=month_name,
                           report_title=report_title,
                           total_budget_out=total_budget_out,
                           total_spent=total_spent,
                           remaining_budget=remaining_budget,
                           budget_used_pct=budget_used_pct,
                           spending_pace=spending_pace,
                           top_expenses=top_expenses,
                           total_flow=total_flow,
                           income_pct=income_pct,
                           expense_pct=expense_pct,
                           bill_pct=bill_pct,
                           debt_pct=debt_pct,
                           saving_pct=saving_pct)

@app.route('/budget')
def budget():
    conn = sqlite3.connect(DB_NAME)
    cats_df = pd.read_sql_query("SELECT name, group_type FROM categories", conn)
    budgets_df = pd.read_sql_query("SELECT category, amount FROM budgets WHERE month='DEFAULT'", conn)
    conn.close()
    
    df = pd.merge(cats_df, budgets_df, left_on='name', right_on='category', how='left').fillna(0.0)
    
    frequency = request.args.get('frequency', 'Monthly')
    ratio = 1.0
    if frequency == 'Daily': ratio = 1/30.44
    elif frequency == 'Weekly': ratio = 7/30.44
    
    df['amount'] = df['amount'] * ratio
    
    grouped_budgets = {}
    for grp in ['Income', 'Bill', 'Expense', 'Saving', 'Debt']:
        grouped_budgets[grp] = df[df['group_type'] == grp].sort_values('name').to_dict('records')
        # Standardize keys for template
        for item in grouped_budgets[grp]:
            item['category'] = item['name']

    return render_template('budget.html', frequency=frequency, grouped_budgets=grouped_budgets)

@app.route('/update_budget', methods=['POST'])
def update_budget():
    frequency = request.form.get('frequency', 'Monthly')
    ratio = 1.0
    if frequency == 'Daily': ratio = 1/30.44
    elif frequency == 'Weekly': ratio = 7/30.44
    
    # Iterate inputs
    for key, value in request.form.items():
        if key.startswith('budget_'):
            cat_name = key.replace('budget_', '')
            try:
                val = float(value)
                # Save as Monthly
                monthly_val = val / ratio
                set_budget_db(cat_name, monthly_val)
            except ValueError:
                pass
                
    return redirect(url_for('budget', frequency=frequency))

@app.route('/logs')
def logs():
    date_str = request.args.get('date')
    
    conn = sqlite3.connect(DB_NAME)
    
    if not date_str:
        # Get latest date with transactions
        cur = conn.cursor()
        cur.execute("SELECT MAX(date) FROM transactions")
        res = cur.fetchone()
        date_str = res[0] if res[0] else str(datetime.date.today())
    
    df = pd.read_sql_query("SELECT * FROM transactions WHERE date = ? ORDER BY id DESC", conn, params=(date_str,))
    conn.close()
    
    transactions = df.to_dict('records')
    total_flow_day = df[df['type']=='Income']['amount'].sum() + df[df['type']=='Expense']['amount'].sum()
    
    return render_template('logs.html', selected_date=date_str, transactions=transactions, total_flow_day=total_flow_day)

if __name__ == '__main__':
    # Initialize DB on start
    if not __import__("os").path.exists(DB_NAME):
        init_db()
    app.run(debug=True, port=5000)
