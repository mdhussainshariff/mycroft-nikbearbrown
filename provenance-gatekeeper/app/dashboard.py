from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import sqlite3

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def view_dashboard():
    # Connect to the persistent tracker
    conn = sqlite3.connect("gatekeeper_logs.db")
    cursor = conn.cursor()
    
    # Query matching the EXACT columns defined in main.py's init_db()
    cursor.execute("""
        SELECT id, timestamp, claim_id, generated_claim, variance_type, verdict 
        FROM evaluation_logs 
        ORDER BY id DESC LIMIT 50
    """)
    logs = cursor.fetchall()
    conn.close()

    # Generate HTML rows dynamically
    rows = "".join([
        f"""<tr>
            <td>{row[0]}</td>
            <td>{row[1]}</td>
            <td>{row[2]}</td>
            <td>{row[3]}</td>
            <td>{row[4]}</td>
            <td style="color: {'red' if row[5] == 'FAIL' else 'green'}">{row[5]}</td>
        </tr>""" 
        for row in logs
    ])

    html_content = f"""
    <html>
        <head>
            <title>Gatekeeper Audit Ledger</title>
            <style>
                body {{ font-family: monospace; background-color: #121212; color: #e0e0e0; padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #444; padding: 10px; text-align: left; }}
                th {{ background-color: #222; }}
            </style>
        </head>
        <body>
            <h1>Provenance Gatekeeper: Live Evaluation Ledger</h1>
            <table>
                <tr>
                    <th>ID</th><th>Timestamp</th><th>Claim ID</th><th>Generated Claim</th><th>Variance Type</th><th>Verdict</th>
                </tr>
                {rows}
            </table>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)