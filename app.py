import streamlit as st
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import datetime

# --- Database Management ---
DB_NAME = 'finance.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Transactions: Actual money movement
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            type TEXT, -- 'Income' or 'Expense' (legacy) - we will use category_group for detailed tracking
            category TEXT,
            amount REAL,
            description TEXT
        )
    ''')

    # Categories: Predefined or User defined categories with a group (Income, Bill, Expense, Debt, Saving)
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            group_type TEXT -- 'Income', 'Bill', 'Expense', 'Debt', 'Saving'
        )
    ''')

    # Budgets: Monthly expected limits/targets per category
    c.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            amount REAL,
            month TEXT, -- YYYY-MM
            UNIQUE(category, month)
        )
    ''')

    conn.commit()
    conn.close()
    seed_categories()

def seed_categories():
    # Pre-populate with International Student suitable categories
    initial_categories = [
        # Income
        ('Part-time Job', 'Income'),
        ('Scholarship', 'Income'),
        ('Other Income', 'Income'),
        
        # Bills (Fixed)
        ('Rent', 'Bill'),
        ('Phone Plan', 'Bill'),
        ('Internet', 'Bill'),
        ('Utilities (Water/Elec)', 'Bill'),
        ('Health Cover (OSHC)', 'Bill'),
        ('Tuition Fees', 'Bill'),
        
        # Expenses (Variable)
        ('Groceries', 'Expense'),
        ('Transport (Myki)', 'Expense'),
        ('Eat Out', 'Expense'),
        ('Shopping', 'Expense'),
        ('Entertainment', 'Expense'),
        ('University Materials', 'Expense'),
        ('International Calls', 'Expense'),
        ('Remittance (Parents)', 'Expense'),
        
        # Savings
        ('Emergency Fund', 'Saving'),
        ('Travel Fund', 'Saving'),
        ('Return Ticket', 'Saving'),
        
        # Debt
        ('Student Loan', 'Debt'),
        ('Credit Card', 'Debt')
    ]
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for cat, grp in initial_categories:
        try:
            c.execute('INSERT INTO categories (name, group_type) VALUES (?, ?)', (cat, grp))
        except sqlite3.IntegrityError:
            pass # Already exists
    conn.commit()
    conn.close()

def add_transaction(date, type, category, amount, description):
    # Ensure date is string
    if isinstance(date, (datetime.date, datetime.datetime)):
        date_str = date.strftime("%Y-%m-%d")
    else:
        date_str = str(date)
        
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT INTO transactions (date, type, category, amount, description) VALUES (?, ?, ?, ?, ?)',
              (date_str, type, category, amount, description))
    conn.commit()
    conn.close()

def set_budget(category, amount, month):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO budgets (category, amount, month) VALUES (?, ?, ?)
        ON CONFLICT(category, month) DO UPDATE SET amount=excluded.amount
    ''', (category, amount, month))
    conn.commit()
    conn.close()

# Legacy function removed

def get_transactions():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date DESC", conn)
    conn.close()
    return df

def get_categories_by_group(group):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT name FROM categories WHERE group_type = ?", (group,))
    cats = [row[0] for row in c.fetchall()]
    conn.close()
    return cats

# --- UI Configuration & Styling ---
st.set_page_config(page_title="Student Money Manager", page_icon="💰", layout="wide")

# Custom CSS for Dark Mode & Premium Feel
st.markdown("""
    <style>
    /* Global Text Color Fix for Dark Mode */
    body {
        color: #E0E0E0;
    }
    
    /* Card Container */
    .kpi-card {
        background-color: #262730;
        border: 1px solid #3E404D;
        border-radius: 12px;
        padding: 20px;
        text-align: left;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        margin-bottom: 20px;
        transition: transform 0.2s;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.4);
    }
    
    /* KPI Text Styling */
    .kpi-label {
        font-size: 14px;
        color: #A0A0A0;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .kpi-value {
        font-size: 28px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 5px;
    }
    
    /* Delta Badges */
    .delta-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
    }
    .delta-pos { background-color: rgba(76, 175, 80, 0.2); color: #81C784; }
    .delta-neg { background-color: rgba(229, 57, 53, 0.2); color: #E57373; }
    .delta-neu { background-color: rgba(33, 150, 243, 0.2); color: #64B5F6; }

    /* Custom Progress Bar for Budgets */
    .progress-container {
        background-color: #3E404D;
        border-radius: 4px;
        height: 8px;
        width: 100%;
        margin-top: 5px;
    }
    .progress-fill {
        height: 100%;
        border-radius: 4px;
    }
    </style>
    """, unsafe_allow_html=True)

# Helper for KPI Card
def card_html(label, value_str, delta_str=None, delta_color="neu"):
    delta_html = ""
    if delta_str:
        delta_class = f"delta-{delta_color}"
        delta_html = f'<div class="delta-badge {delta_class}">{delta_str}</div>'
    
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value_str}</div>
        {delta_html}
    </div>
    """

# --- Initialization ---
init_db()

# --- Data Helpers ---
def get_budget_vs_actual_range(start, end, days_ratio=1.0):
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Categories
    categories_df = pd.read_sql_query("SELECT name as category, group_type FROM categories", conn)
    
    # 2. Default Budgets
    defaults_df = pd.read_sql_query("SELECT category, amount as full_budget FROM budgets WHERE month = 'DEFAULT'", conn)
    
    # 3. Actuals in Range
    actuals_query = """
        SELECT category, SUM(amount) as actual 
        FROM transactions 
        WHERE date >= ? AND date <= ?
        GROUP BY category
    """
    actuals_df = pd.read_sql_query(actuals_query, conn, params=(start, end))
    conn.close()
    
    # Merge
    df = pd.merge(categories_df, defaults_df, on='category', how='left')
    df = pd.merge(df, actuals_df, on='category', how='left')
    
    df['actual'] = pd.to_numeric(df['actual'], errors='coerce').fillna(0.0)
    df['full_budget'] = pd.to_numeric(df['full_budget'], errors='coerce').fillna(0.0)
    
    # Pro-rate Budget based on range duration vs month
    df['budgeted'] = df['full_budget'] * days_ratio
    
    # Calc Diffs
    df['diff'] = 0.0
    mask_pos = df['group_type'].isin(['Income', 'Saving'])
    df.loc[mask_pos, 'diff'] = df.loc[mask_pos, 'actual'] - df.loc[mask_pos, 'budgeted']
    mask_neg = df['group_type'].isin(['Bill', 'Expense', 'Debt'])
    df.loc[mask_neg, 'diff'] = df.loc[mask_neg, 'budgeted'] - df.loc[mask_neg, 'actual']
    
    return df

def get_transactions_range(start, end):
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT * FROM transactions WHERE date >= ? AND date <= ? ORDER BY date DESC"
    df = pd.read_sql_query(query, conn, params=(start, end))
    conn.close()
    return df

# --- Shared State & Sidebar ---
# --- Shared State (No Sidebar) ---
# Report params handled per tab or top level

# Initialize Default
if 'daily_date' not in st.session_state:
    st.session_state['daily_date'] = datetime.date.today()

# --- Main Layout ---
st.title(f"🎓 Student Money Manager")

# Tabs
tab_dash, tab_reports, tab_budget, tab_log = st.tabs([
    "📅 Daily Manager", 
    "📊 Reports & Metrics", 
    "🛠️ Budget Config", 
    "📓 Transaction Logs"
])

# ==========================================
# TAB 1: DAILY MANAGER
# ==========================================
with tab_dash:
    # Top Controls: Date Picker & Quick Add
    c_date, c_add = st.columns([1, 2])
    
    with c_date:
        selected_date = st.date_input("Select Date to Manage", value=st.session_state['daily_date'], key="daily_date_picker")
        st.session_state['daily_date'] = selected_date
    
    with c_add:
        # Mini Form for Quick Add (Hidden by default)
        with st.expander("➕ Add New Transaction"):
            with st.form("quick_add_tx", clear_on_submit=True):
                c_a1, c_a2, c_a3 = st.columns(3)
                with c_a1:
                    tx_grp = st.selectbox("Group", ["Income", "Bill", "Expense", "Saving", "Debt"])
                    tx_cats = get_categories_by_group(tx_grp)
                    tx_cat = st.selectbox("Category", tx_cats)
                with c_a2:
                    tx_amt = st.number_input("Amount ($)", min_value=0.01, format="%.2f")
                with c_a3:
                    tx_desc = st.text_input("Description (Opt)")
                    submitted = st.form_submit_button("Add", type="primary", use_container_width=True)
                
                if submitted:
                    s_type = "Income" if tx_grp == "Income" else "Expense"
                    add_transaction(selected_date, s_type, tx_cat, tx_amt, tx_desc)
                    st.success("Added!")
                    st.rerun()

    display_title = selected_date.strftime("%d %B %Y")
    st.caption(f"**Managing Daily: {display_title}**")
    
    # Define Context for Dashboard
    start_date = selected_date
    end_date = selected_date
    ratio = 1.0 / 30.44

    # --- 1. Persistent Draft (Daily) ---
    current_params = (start_date, end_date, ratio)
    if 'last_dash_params' not in st.session_state or st.session_state['last_dash_params'] != current_params:
        df_fresh = get_budget_vs_actual_range(start_date, end_date, ratio)
        st.session_state['master_draft'] = df_fresh
        st.session_state['last_dash_params'] = current_params
        for key in list(st.session_state.keys()):
            if key.startswith("track_"):
                del st.session_state[key]
    
    df_live = st.session_state['master_draft']

    # --- 2. Recalculate derived ---
    mask_pos = df_live['group_type'].isin(['Income', 'Saving'])
    df_live.loc[mask_pos, 'diff'] = df_live.loc[mask_pos, 'actual'] - df_live.loc[mask_pos, 'budgeted']
    mask_neg = df_live['group_type'].isin(['Bill', 'Expense', 'Debt'])
    df_live.loc[mask_neg, 'diff'] = df_live.loc[mask_neg, 'budgeted'] - df_live.loc[mask_neg, 'actual']
    df_live['Usage'] = df_live.apply(lambda x: (x['actual'] / x['budgeted'] * 100) if x['budgeted'] > 0 else (100 if x['actual'] > 0 else 0), axis=1)
    
    st.session_state['master_draft'] = df_live

    # --- 3. KPI Cards ---
    income_data = df_live[df_live['group_type'] == 'Income']
    total_actual_income = income_data['actual'].sum()
    
    outflow_mask = df_live['group_type'].isin(['Bill', 'Expense', 'Debt'])
    outflow_data = df_live[outflow_mask]
    total_actual_outflow = outflow_data['actual'].sum()
    
    saving_data = df_live[df_live['group_type'] == 'Saving']
    total_actual_saving = saving_data['actual'].sum()

    daily_expense_budget = df_live[outflow_mask]['budgeted'].sum()
    daily_expense_diff = daily_expense_budget - total_actual_outflow

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(card_html("Daily Income", f"${total_actual_income:,.2f}", "", "neu"), unsafe_allow_html=True)
    with c2: st.markdown(card_html("Daily Spend", f"${total_actual_outflow:,.2f}", f"${daily_expense_diff:+,.2f} Left", "pos" if daily_expense_diff >= 0 else "neg"), unsafe_allow_html=True)
    with c3: st.markdown(card_html("Daily Saved", f"${total_actual_saving:,.2f}", "", "neu"), unsafe_allow_html=True)
    
    # Net Balance (Today)
    net_bal = total_actual_income - total_actual_outflow - total_actual_saving
    with c4: st.markdown(card_html("Daily Balance", f"${net_bal:,.2f}", "Net Flow", "pos" if net_bal >= 0 else "neg"), unsafe_allow_html=True)

    # --- 4. Interactive Tables ---
    st.divider()
    st.caption("Manage your day. Values entered here are logged for **" + display_title + "**.")
    
    def render_tracking_table(group_name, icon):
        subset_live = df_live[df_live['group_type'] == group_name].copy().sort_values('category')
        subset_base = get_budget_vs_actual_range(start_date, end_date, ratio)[get_budget_vs_actual_range(start_date, end_date, ratio)['group_type'] == group_name].sort_values('category')
        
        if subset_live.empty: return

        st.markdown(f"**{icon} {group_name}**")
        
        display_df = pd.DataFrame(index=subset_live.index)
        display_df['category'] = subset_live['category']
        display_df['budgeted'] = subset_live['budgeted']
        display_df['actual'] = subset_live['actual']
        display_df['diff'] = subset_live['diff']
        display_df['Usage'] = subset_live['Usage']
        display_df = display_df.set_index('category')
        
        edited_subset = st.data_editor(
            display_df,
            key=f"track_{group_name}",
            column_config={
                 "budgeted": st.column_config.NumberColumn("Daily Budget", format="$%.2f", step=1.0, required=True),
                 "actual": st.column_config.NumberColumn("Today's Actual", format="$%.2f", step=1.0, required=True),
                 "diff": st.column_config.NumberColumn("Diff", format="$%.2f", disabled=True),
                 "Usage": st.column_config.ProgressColumn("Usage", format="%.0f%%", min_value=0, max_value=100),
            },
            use_container_width=True,
            disabled=["diff", "Usage", "category"]
        )
        
        # Detect Changes
        has_changes = False
        for idx in edited_subset.index:
            old_b = subset_live.loc[subset_live['category'] == idx, 'budgeted'].values[0]
            old_a = subset_live.loc[subset_live['category'] == idx, 'actual'].values[0]
            new_b = edited_subset.loc[idx, 'budgeted']
            new_a = edited_subset.loc[idx, 'actual']
            
            if abs(new_b - old_b) > 0.001 or abs(new_a - old_a) > 0.001:
                mask = st.session_state['master_draft']['category'] == idx
                st.session_state['master_draft'].loc[mask, 'budgeted'] = new_b
                st.session_state['master_draft'].loc[mask, 'actual'] = new_a
                has_changes = True
        
        if has_changes:
            st.rerun()

    d1, d2 = st.columns(2)
    with d1:
        render_tracking_table("Expense", "🛒")
        render_tracking_table("Bill", "🧾")
    with d2:
        render_tracking_table("Income", "💰")
        render_tracking_table("Saving", "🐷")
        render_tracking_table("Debt", "💳")

    # --- 5. Save Button ---
    df_baseline = get_budget_vs_actual_range(start_date, end_date, ratio)
    df_active = st.session_state['master_draft'].set_index('category').sort_index()
    df_base = df_baseline.set_index('category').sort_index()
    
    diff_act = (df_active['actual'] - df_base['actual']).abs().sum()
    diff_bud = (df_active['budgeted'] - df_base['budgeted']).abs().sum()
    
    st.divider()
    st.divider()
    
    # Always show the save button to ensure user knows where to click
    if st.button("💾 Save to Daily Log", type="primary", use_container_width=True, key="btn_save_daily"):
        # Recalculate diffs inside the button action to capture the very latest state (including the edit that just triggered this)
        diff_act = (df_active['actual'] - df_base['actual']).abs().sum()
        diff_bud = (df_active['budgeted'] - df_base['budgeted']).abs().sum()
        
        if diff_act > 0.001 or diff_bud > 0.001:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            
            # Save Actuals
            # Ensure consistent date string for DB
            date_str = start_date.strftime("%Y-%m-%d")
            
            ch_a = df_active[abs(df_active['actual'] - df_base['actual']) > 0.001].index
            for cat in ch_a:
                target_val = df_active.loc[cat, 'actual']
                
                # Check existing transactions
                c.execute("SELECT id, amount, description FROM transactions WHERE date=? AND category=?", (date_str, cat))
                existings = c.fetchall()
                
                if len(existings) == 1:
                    # Strategy A: Update single existing
                    tid = existings[0][0]
                    c.execute("UPDATE transactions SET amount=? WHERE id=?", (target_val, tid))
                    
                elif len(existings) > 1:
                    # Strategy B: Multiple exists. Update 'Daily Manager Entry' or create delta.
                    adj_row = next((r for r in existings if r[2] == "Daily Manager Entry"), None)
                    
                    if adj_row:
                        current_total = sum(r[1] for r in existings)
                        sum_others = current_total - adj_row[1]
                        new_adj = target_val - sum_others
                        c.execute("UPDATE transactions SET amount=? WHERE id=?", (new_adj, adj_row[0]))
                    else:
                        current_total = sum(r[1] for r in existings)
                        delta = target_val - current_total
                        grp = df_active.loc[cat, 'group_type']
                        tx_type = "Income" if grp == "Income" else "Expense"
                        c.execute('INSERT INTO transactions (date, type, category, amount, description) VALUES (?, ?, ?, ?, ?)',
                                  (date_str, tx_type, cat, delta, "Daily Manager Entry"))
                                  
                else:
                    # Strategy C: Insert New
                    grp = df_active.loc[cat, 'group_type']
                    tx_type = "Income" if grp == "Income" else "Expense"
                    c.execute('INSERT INTO transactions (date, type, category, amount, description) VALUES (?, ?, ?, ?, ?)',
                              (date_str, tx_type, cat, target_val, "Daily Manager Entry"))
            
            # Save Budgets (Normalized to Monthly)
            ch_b = df_active[abs(df_active['budgeted'] - df_base['budgeted']) > 0.001].index
            for cat in ch_b:
                m_val = df_active.loc[cat, 'budgeted'] * 30.44 
                c.execute('''INSERT INTO budgets (category, amount, month) VALUES (?, ?, 'DEFAULT')
                             ON CONFLICT(category, month) DO UPDATE SET amount=excluded.amount''', (cat, m_val))
            
            conn.commit()
            conn.close()
            
            # Clear caches to ensure other tabs update
            if 'last_dash_params' in st.session_state: del st.session_state['last_dash_params']
            
            st.toast("✅ Saved! Reports & Logs have been updated.")
            st.rerun()
        else:
            st.info("No changes detected to save. Try editing a value first.")

# ==========================================
# ==========================================
# TAB 2: REPORTS (New)
# ==========================================
with tab_reports:
    st.subheader("📊 Performance Reports")
    
    today = datetime.date.today()
    
    # 1. Selection
    rpt_col1, rpt_col2 = st.columns([1, 2])
    with rpt_col1:
        report_typ = st.radio("View By:", ["Monthly", "Weekly", "Daily"], horizontal=True, key="report_view_selector")
        
    with rpt_col2:
        if report_typ == "Monthly":
            c_y, c_m = st.columns(2)
            with c_y:
                curr_y = today.year
                yr = st.selectbox("Year", range(curr_y-2, curr_y+3), index=2)
            with c_m:
                mon_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                curr_m = today.month - 1
                mon = st.selectbox("Month", mon_names, index=curr_m)
            
            # Range Calc
            r_start = datetime.date(yr, mon_names.index(mon)+1, 1)
            next_mo_start = (r_start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
            r_end = next_mo_start - datetime.timedelta(days=1)
            r_ratio = 1.0
            r_title = r_start.strftime("%B %Y")
            
        elif report_typ == "Weekly":
            # Weekly
            # Valid range logic to highlight the week:
            # We use session state to persist the "Week Range"
            if 'report_week_range' not in st.session_state:
                t = datetime.date.today()
                s = t - datetime.timedelta(days=t.weekday())
                e = s + datetime.timedelta(days=6)
                st.session_state['report_week_range'] = (s, e)

            # Callback to snap to week
            def snap_week():
                val = st.session_state.wk_picker
                if not val: return
                # If user picks a range or single date, we base it on the START date
                if isinstance(val, (list, tuple)):
                    base = val[0]
                else:
                    base = val
                
                # Calculate Mon-Sun
                start = base - datetime.timedelta(days=base.weekday())
                end = start + datetime.timedelta(days=6)
                st.session_state['report_week_range'] = (start, end)

            sel_dates = st.date_input(
                "Select Week", 
                value=st.session_state['report_week_range'], 
                key="wk_picker",
                on_change=snap_week,
                format="YYYY-MM-DD"
            )
            
            # Use the computed range
            if isinstance(st.session_state['report_week_range'], (list, tuple)) and len(st.session_state['report_week_range']) == 2:
                r_start, r_end = st.session_state['report_week_range']
            else:
                # Fallback
                r_start = datetime.date.today()
                r_end = r_start

            r_ratio = 7 / 30.44
            r_title = f"Week: {r_start.strftime('%d %b')} - {r_end.strftime('%d %b')}"
            st.caption(f"🗓️ Selected: **Mon {r_start.day}** - **Sun {r_end.day}**")
            
        else:
            # Daily Mode
            sel_d = st.date_input("Select Date", today, key="rpt_daily_picker")
            r_start = sel_d
            r_end = sel_d
            r_ratio = 1 / 30.44
            r_title = sel_d.strftime("%A, %d %B %Y")

    st.divider()
    
    # 2. Check Data
    # Fetch actuals to verify if "managed"
    raw_tx = get_transactions_range(r_start, r_end)
    
    if raw_tx.empty:
        st.info(f"ℹ️ No transactions found for **{r_title}**. This period is not yet managed or logged.")
    else:
        # 3. Display Data
        st.markdown(f"### Performance: {r_title}")
        
        df_perf = get_budget_vs_actual_range(r_start, r_end, days_ratio=r_ratio)
        
        # A. High Level Metrics
        # We consider 'Outflow' as Expense + Bill + Debt
        out_mask = df_perf['group_type'].isin(['Expense', 'Bill', 'Debt'])
        
        limit = df_perf[out_mask]['budgeted'].sum()
        spent = df_perf[out_mask]['actual'].sum()
        rem = limit - spent
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Budget (Out)", f"${limit:,.0f}", help="Sum of budgets for Bills, Expenses, and Debt. Does not include Savings.")
        k2.metric("Total Spent", f"${spent:,.0f}", f"{rem:+,.0f} Remaining")
        
        # B. Progress Bar
        if limit > 0:
            pct = min(spent / limit, 1.0)
            st.progress(pct, text=f"{pct*100:.1f}% of Budget Used")
            
        st.divider()
        
        # C. Detailed Charts
        g1, g2 = st.columns(2)
        with g1:
            st.caption("Detailed Breakdown")
            # Show all Outflow categories with spending
            df_plot = df_perf[out_mask & (df_perf['actual'] > 0)].copy()
            if not df_plot.empty:
                fig = px.bar(df_plot.sort_values('actual'), x='actual', y='category', 
                            color='group_type', orientation='h', text_auto='.2s',
                            labels={'actual': 'Amount ($)', 'category': '', 'group_type': 'Type'})
                fig.update_layout(height=300, margin=dict(l=0,r=0,t=0,b=0))
                fig.update_traces(hovertemplate='<b>%{y}</b><br>Amount: $%{x:,.2f}<br>Type: %{legendgroup}<extra></extra>')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("No spending recorded.")
                
        with g2:
            st.caption("Financial Composition")
            # Aggregate by Group
            grp_sum = df_perf.groupby('group_type')['actual'].sum().reset_index()
            # Filter out zero values for cleaner chart
            grp_sum = grp_sum[grp_sum['actual'] > 0]
            
            if not grp_sum.empty:
                # Custom colors
                color_map = {
                    'Income': '#66BB6A', 
                    'Saving': '#42A5F5',
                    'Bill': '#FFA726',
                    'Expense': '#EF5350',
                    'Debt': '#AB47BC'
                }
                fig2 = px.pie(grp_sum, values='actual', names='group_type', hole=0.4, 
                             color='group_type', color_discrete_map=color_map,
                             labels={'actual': 'Amount ($)', 'group_type': 'Group'})
                fig2.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>Amount: $%{value:,.2f}<extra></extra>')
                fig2.update_layout(height=300, margin=dict(l=0,r=0,t=0,b=0), showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No data to display.")


# TAB 3: BUDGET CONFIG
# ==========================================
with tab_budget:
    st.subheader("🛠️ Standard Budget Configuration")
    st.markdown("Define your **Standard Budgets** here. These baseline values are used to auto-fill your dashboards.")
    st.info("💡 **Tip:** You can enter your budget in Daily, Weekly, or Monthly terms. The app will automatically convert and save it as your Standard Monthly Budget.")

    # 1. Frequency Selector
    plan_mode = st.radio("Input Frequency", ["Daily", "Weekly", "Monthly"], horizontal=True, key="plan_freq_selector")
    
    # 2. Determine Ratio for this specific TAB (Independent of the main report_mode)
    if plan_mode == "Daily":
        plan_ratio = 1 / 30.44
        plan_days = 1
    elif plan_mode == "Weekly":
        plan_ratio = 7 / 30.44
        plan_days = 7
    else:
        plan_ratio = 1.0
        plan_days = 30

    # 3. Fetch Data
    conn = sqlite3.connect(DB_NAME)
    cats_df = pd.read_sql_query("SELECT name as category, group_type FROM categories", conn)
    defaults_df = pd.read_sql_query("SELECT category, amount as full_monthly_budget FROM budgets WHERE month = 'DEFAULT'", conn)
    conn.close()
    
    plan_df = pd.merge(cats_df, defaults_df, on='category', how='left').fillna(0.0)
    
    # 4. Scale to Selected Frequency
    plan_df['budgeted'] = plan_df['full_monthly_budget'] * plan_ratio

    def render_plan_table(group_name, icon):
        subset = plan_df[plan_df['group_type'] == group_name].copy().sort_values('category')
        if subset.empty: return
        
        st.markdown(f"**{icon} {group_name}**")
        display_df = subset[['category', 'budgeted']].set_index('category')
        
        col_title = f"{plan_mode} Budget"
        
        edited_df = st.data_editor(
            display_df,
            key=f"plan_{group_name}_{plan_mode}", # Unique key per mode to prevent conflict
            column_config={
                "budgeted": st.column_config.NumberColumn(col_title, format="$%.2f", min_value=0.0, step=1.0, required=True)
            },
            use_container_width=True,
            disabled=["category"]
        )
        
        # Save Budget Changes
        # We compare the EDITED value against the SCALED original.
        orig_b = subset.set_index('category')['budgeted']
        new_b = edited_df['budgeted']
        
        if not orig_b.equals(new_b):
            diff_cats = orig_b[orig_b != new_b].index.tolist()
            for cat in diff_cats:
                new_val_freq = new_b[cat]
                
                # Convert BACK to Monthly for storage
                # If plan_ratio is 1/30.44, we DIVIDE by it (multiply by 30.44) to get monthly
                val_to_save = new_val_freq / plan_ratio if plan_ratio > 0 else new_val_freq
                
                set_budget(cat, val_to_save, 'DEFAULT')
            
            # Force Refresh of Daily Manager
            if 'last_dash_params' in st.session_state:
                del st.session_state['last_dash_params']
            
            # Rerun to refresh all views
            st.rerun()

    b_col1, b_col2 = st.columns(2)
    with b_col1:
        render_plan_table("Income", "💰")
        render_plan_table("Saving", "🐷")
    with b_col2:
        render_plan_table("Bill", "🧾")
        render_plan_table("Expense", "🛒")
        render_plan_table("Debt", "💳")

# ==========================================
# TAB 4: LOGS & HISTORY
# ==========================================
with tab_log:
    st.subheader("📓 Transaction History")
    
    # 1. Fetch Summary of Dates
    conn = sqlite3.connect(DB_NAME)
    summary_query = """
        SELECT 
            date, 
            COUNT(*) as tx_count, 
            SUM(CASE WHEN type='Income' THEN amount ELSE 0 END) as total_in,
            SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END) as total_out
        FROM transactions 
        GROUP BY date 
        ORDER BY date DESC
    """
    history_df = pd.read_sql_query(summary_query, conn)
    conn.close()
    
    if history_df.empty:
        st.info("No transaction history found.")
    else:
        # 2. Display Date List (Summary)
        st.caption("Select a date to view or edit details.")
        
        # Simplify display
        history_df['Net Change'] = history_df['total_in'] - history_df['total_out']
        
        # Selection Mechanism
        # We can use a dataframe with selection, or a selectbox. Selectbox is reliable.
        # Format dates for dropdown
        date_options = history_df['date'].tolist()
        
        # By default, try to select the current 'daily' date if it exists in history, else top
        default_ix = 0
        current_str = start_date.strftime("%Y-%m-%d")
        if current_str in date_options:
            default_ix = date_options.index(current_str)
            
        selected_history_date_str = st.selectbox(
            "📅 Open Date Log:", 
            date_options, 
            index=default_ix,
            format_func=lambda x: f"{x} ({history_df[history_df['date']==x]['tx_count'].values[0]} items)"
        )
        
        st.divider()
        
        # 3. Drill Down: Detailed Editor for Selected Date
        if selected_history_date_str:
            c_head, c_btn = st.columns([3, 2])
            with c_head:
                st.markdown(f"**Editing Log: {selected_history_date_str}**")
            with c_btn:
                if st.button(f"🗑️ Delete Entire Date Log", type="secondary", use_container_width=True, help="Permanently delete ALL transactions for this specific date."):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("DELETE FROM transactions WHERE date = ?", (selected_history_date_str,))
                    conn.commit()
                    conn.close()
                    st.toast(f"Deleted all logs for {selected_history_date_str}", icon="🗑️")
                    st.rerun()
            
            # Fetch details
            conn = sqlite3.connect(DB_NAME)
            detail_query = "SELECT * FROM transactions WHERE date = ?"
            detail_df = pd.read_sql_query(detail_query, conn, params=(selected_history_date_str,))
            conn.close()
            
            if not detail_df.empty:
                # Configure Editor
                # Enabled num_rows="dynamic" to allow DELETING rows
                edited_history = st.data_editor(
                    detail_df,
                    key="history_editor",
                    column_config={
                        "id": st.column_config.NumberColumn(disabled=True, width="small"),
                        "date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", disabled=True), # Lock date to keep it in this view
                        "amount": st.column_config.NumberColumn("Amount ($)", format="$%.2f", min_value=0.0, required=True),
                        "category": st.column_config.SelectboxColumn("Category", options=get_categories_by_group("Income") + get_categories_by_group("Bill") + get_categories_by_group("Expense") + get_categories_by_group("Saving") + get_categories_by_group("Debt"), required=True),
                        "type": st.column_config.TextColumn(disabled=True),
                        "description": st.column_config.TextColumn("Description"),
                    },
                    hide_index=True,
                    use_container_width=True,
                    num_rows="dynamic" # Allows Add/Delete
                )
                
                # SAVE LOGIC (Handle Updates & Deletes)
                # We compare state. ID is the key.
                # 'edited_history' contains the new state of the table.
                
                # Check for Differences
                if not detail_df.equals(edited_history):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    
                    # A. Identify DELETED rows
                    # IDs present in DB (detail_df) but MISSING in Editor (edited_history)
                    input_ids = edited_history['id'].dropna().tolist() # Existing IDs in editor
                    db_ids = detail_df['id'].tolist()
                    deleted_ids = [i for i in db_ids if i not in input_ids]
                    
                    if deleted_ids:
                        c.execute(f"DELETE FROM transactions WHERE id IN ({','.join(['?']*len(deleted_ids))})", deleted_ids)
                    
                    # B. Identify UPDATED rows
                    # Rows where ID exists in both, but content differs
                    for i, row in edited_history.iterrows():
                        if pd.notna(row['id']) and row['id'] in db_ids:
                            # Compare with DB
                            orig = detail_df[detail_df['id'] == row['id']].iloc[0]
                            if (orig['amount'] != row['amount']) or (orig['category'] != row['category']) or (orig['description'] != row['description']):
                                c.execute('''
                                    UPDATE transactions 
                                    SET amount=?, category=?, description=? 
                                    WHERE id=?
                                ''', (row['amount'], row['category'], row['description'], row['id']))
                    
                    # C. Identify ADDED rows (Optional, if user adds row via UI)
                    # Rows with NaN ID or new rows (Streamlit assigns new IDs usually? No, it leaves them blank or handled by config)
                    # With num_rows=dynamic, added rows don't have an ID yet.
                    # We can iterate rows with null IDs.
                    new_rows = edited_history[edited_history['id'].isna()]
                    for i, row in new_rows.iterrows():
                        # Infer Type from Category
                        cat_grp = "Expense" # Default
                        # Lookup group (inefficient but safe)
                        # Actually we can just leave type blank or infer. Code expects 'type'.
                        # Let's try to fetch it.
                        c.execute("SELECT group_type FROM categories WHERE name=?", (row['category'],))
                        res = c.fetchone()
                        if res:
                            g_type = res[0]
                            t_type = "Income" if g_type == "Income" else "Expense"
                        else:
                            t_type = "Expense"

                        # Date is locked to the selected view date
                        c.execute('''
                            INSERT INTO transactions (date, type, category, amount, description) 
                            VALUES (?, ?, ?, ?, ?)
                        ''', (selected_history_date_str, t_type, row['category'], row['amount'], row['description']))

                    conn.commit()
                    conn.close()
                    st.success("Changes saved!")
                    st.rerun()
            else:
                st.info("No transactions remaining for this date.")

