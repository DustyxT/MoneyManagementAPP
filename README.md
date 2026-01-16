# Student Money Manager

A Streamlit-based finance tracker designed for international students in Australia.

## Features
- **Transaction Entry**: Easy sidebar form to log Income and Expenses.
- **Australian Context**: Pre-filled categories like Myki, Aldi/Coles, etc.
- **Real-time Dashboard**: "Safe to Spend" balance, expense breakdown, and trend charts.
- **Data Persistence**: Uses a local SQLite database (`finance.db`) so your data is saved.

## Prerequisites

**Python Required**: It seems Python might not be installed or configured in your PATH.
1.  Download and install Python from [python.org](https://www.python.org/downloads/).
2.  **Important**: When installing, check the box **"Add Python to PATH"**.

## Setup & Run

1.  **Install Dependencies**:
    Open a terminal in this folder and run:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run the App**:
    ```bash
    streamlit run app.py
    ```

3.  **Usage**:
    - The app will open in your default browser (usually http://localhost:8501).
    - Use the sidebar to add transactions.
    - View your financial health on the main dashboard.
