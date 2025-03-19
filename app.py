from datetime import datetime
import os
import time
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, session, redirect, url_for, flash
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
import plotly.express as px

# Configuration
DATA_REFRESH_INTERVAL = 3600  # Refresh every hour
EXCEL_FILE_PATH = 'player_mapping.xlsx'  # Static data
DB_PATH = 'cricbattle_8.db'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
ADMIN_EMAIL = 'admin@example.com'
EMAIL_HOST = 'smtp.example.com'
EMAIL_PORT = 587
EMAIL_USER = 'your_email@example.com'
EMAIL_PASSWORD = 'your_email_password'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your_secret_key'

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Function to get device ID
def get_device_id():
    user_agent = request.headers.get('User-Agent', '')
    ip = request.remote_addr
    return hashlib.sha256(f"{user_agent}{ip}".encode()).hexdigest()

# Function to check if the device has been approved
def is_approved(device_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT approved FROM payments WHERE deleted=0 and device_id = ?", (device_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None and result[0] == 1



# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Route for payment confirmation form
@app.route('/pay', methods=['GET', 'POST'])
def pay():
    device_id = get_device_id()
    print(device_id)
    # check if device is paid and pending approval

    if is_paid_but_not_approved(device_id):
        flash("Your payment is under review. Please check back later.", "info")
        print("Your payment is under review.")
        return render_template('paid.html', table=None)
    
    if is_rejected(device_id):
        print("Your payment is rejected")
        return render_template('rejected.html', table=None)
    
    if is_approved(device_id):
        return redirect(url_for('display_leaderboard'))
    
    if request.method == 'POST':
        txn_ref = request.form.get('txn_ref')
        file = request.files.get('txn_proof')
        email = request.files.get('email')
        
        if not txn_ref:
            flash("Transaction reference is required.", "danger")
        elif not file or not allowed_file(file.filename):
            flash("Valid payment proof (PNG, JPG, JPEG, PDF) is required.", "danger")
        else:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            #send_email_notification(device_id, txn_ref, file_path)
            flash("Your payment confirmation has been submitted. Please wait for admin approval.", "success")
    
    return render_template('pay.html', qr_code="static/paypal_qr.jpeg")

# Route to confirm payment manually (or via PayPal IPN)
@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    device_id = get_device_id()
    email = request.form.get('email')
    txn_ref = request.form.get('txn_ref')
    txn_proof = request.files.get('txn_proof')
    print(txn_proof, allowed_file(txn_proof.filename))

    if email and txn_ref and txn_proof and allowed_file(txn_proof.filename):
        filename = secure_filename(txn_proof.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        txn_proof.save(file_path)
        
        with open(file_path, 'rb') as f:
            proof_blob = f.read()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # This SQL statement looks correct for inserting/updating payment records
        # It uses INSERT OR REPLACE to handle both new inserts and updates
        # The columns match the table schema defined elsewhere in the code
        # All parameters are properly bound using ? placeholders
        # The values tuple matches the number and order of columns

        print("inserting data with proof")
        cursor.execute("INSERT OR REPLACE INTO payments (device_id, email, txn_ref, txn_proof, paid) VALUES (?, ?, ?, ?, 1)", 
                            (device_id, email, txn_ref, proof_blob))        
        conn.commit()
        print("committed data ")
        conn.close()
        return redirect(url_for('display_leaderboard'))

    elif email and txn_ref:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # This SQL statement looks correct for inserting/updating payment records
        # It uses INSERT OR REPLACE to handle both new inserts and updates
        # The columns match the table schema defined elsewhere in the code
        # All parameters are properly bound using ? placeholders
        # The values tuple matches the number and order of columns

        print("inserting data without proof")
        cursor.execute("INSERT OR REPLACE INTO payments (device_id, email, txn_ref, paid) VALUES (?, ?, ?, 1)", 
                            (device_id, email, txn_ref))        
        conn.commit()
        print("committed data ")
        conn.close()

        return redirect(url_for('display_leaderboard'))
    else:
        print("Invalid payment proof")
        flash("Invalid payment proof file", "danger")
    
def is_paid_but_not_approved(device_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS payments ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "device_id TEXT,"
        "txn_ref TEXT, "
        "txn_proof BLOB, "
        "email TEXT,"
        "timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "paid INTEGER DEFAULT 0, "
        "trial_expiry DATETIME DEFAULT NULL,"
        "deleted INTEGER DEFAULT 0,"    
        "approved INTEGER DEFAULT 0)")
    cursor.execute("SELECT paid, approved FROM payments WHERE deleted=0 and device_id = ?", (device_id,))
    result = cursor.fetchone()
    print(result)
    conn.close()
    if result is None:
        return False
    return result is not None and result[0] == 1 and result[1] == 0

def is_rejected(device_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT paid, approved FROM payments WHERE deleted=0 and device_id = ?", (device_id,))
    result = cursor.fetchone()
    conn.close()
    if result is None:
        return False
    return result is not None and result[0] == 1 and result[1] == 2

@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # For demo purposes using hardcoded admin credentials
        # In production, use proper password hashing and database storage
        if username == 'admin' and password == 'admin123':
            session['admin'] = True
            flash('Successfully logged in as admin', 'success')
            return redirect(url_for('admin_review'))
        else:
            flash('Invalid credentials', 'danger')
            
    return render_template('login.html')

@app.route('/admin/review', methods=['GET', 'POST'])
def admin_review():
    # Check if user is admin (you may want to add proper admin authentication)
    if session.get('admin') != True:
        return redirect(url_for('/admin/login'))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == 'POST':
        device_id = request.form.get('device_id')
        action = request.form.get('action')

        if action == 'approve':
            cursor.execute("UPDATE payments SET approved = 1 WHERE deleted=0 and device_id = ?", (device_id,))
            flash(f"Payment for device {device_id} approved", "success")
        elif action == 'reject':
            cursor.execute("UPDATE payments SET approved = 0 WHERE deleted=0 and device_id = ?", (device_id,))
            flash(f"Payment for device {device_id} rejected", "danger")

        conn.commit()

    # Get all paid but not approved payments
    cursor.execute("""
        SELECT p.device_id, p.email, p.txn_ref, p.txn_proof, p.timestamp, p.approved , p.deleted, p.trial_expiry
        FROM payments p 
    """)
    pending_payments = cursor.fetchall()
    #convert pendind_payments to json including file blob
    #file blob should be converted to downloadable link using uploads dir location
    for i in range(len(pending_payments)):
        if pending_payments[i][3] is not None:
            with open(f"static/uploads/{pending_payments[i][0]}.png", "wb") as f:
                f.write(pending_payments[i][3])
                pending_payments[i] = list(pending_payments[i])
                pending_payments[i][3] = url_for('static', filename=f"uploads/{pending_payments[i][0]}.png")  
                pending_payments[i] = tuple(pending_payments[i])
                print(pending_payments[i])
                print(pending_payments[i][3])

    
    
    conn.close()

    return render_template('paid_not_approved.html', payments=pending_payments)

# Route for Leaderboard
@app.route('/')
def display_leaderboard():
    device_id = get_device_id()
    print(device_id)
    # check if device is paid and pending approval

    if is_paid_but_not_approved(device_id):
        flash("Your payment is under review. Please check back later.", "info")
        print("Your payment is under review")
        return render_template('paid.html', table=None)
    
    if is_rejected(device_id):
        print("Your payment is rejected")
        return render_template('rejected.html', table=None)
    
    if not is_approved(device_id):
        print("Your payment is not found")
        return redirect(url_for('pay'))
    
    return redirect(url_for('show_insights')) 

@app.route('/admin/approve/<device_id>', methods=['POST'])
def approve_payment(device_id):
    if session.get('admin') != True:
        return {'error': 'Unauthorized'}, 401
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE payments SET approved = 1 WHERE deleted = 0  and device_id = ?", (device_id,))
    conn.commit()
    conn.close()
    
    return {'message': f'Payment for device {device_id} approved'}, 200

@app.route('/admin/reject/<device_id>', methods=['POST']) 
def reject_payment(device_id):
    if session.get('admin') != True:
        return {'error': 'Unauthorized'}, 401
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE payments SET approved = 2 WHERE deleted = 0 and device_id = ?", (device_id,))
    conn.commit()
    conn.close()
    
    return {'message': f'Payment for device {device_id} rejected'}, 200
         
@app.route('/reset-payment', methods=['POST'])
def reset_payment():
    device_id = get_device_id()
    print(device_id)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE payments SET deleted = 1 WHERE deleted = 0 and device_id = ?", (device_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('display_leaderboard')) 

@app.route('/insights')
def show_insights():
    # check if user is paid and approved
    device_id = get_device_id()
    if not is_approved(device_id):
        return redirect(url_for('pay'))

    # Connect to database and load data
    conn = sqlite3.connect('mydatabase.db')
    
    # Fetch player data
    df = pd.read_sql_query("SELECT name, role, category, ipl_team, base_price, selling_price, team_name, is_sold FROM player", conn)
    conn.close()

    # Clean the data
    df_clean = df.dropna(subset=['base_price', 'selling_price', 'team_name', 'role'])
    df_clean['base_price'] = pd.to_numeric(df_clean['base_price'], errors='coerce')
    df_clean['selling_price'] = pd.to_numeric(df_clean['selling_price'], errors='coerce')
    df_clean = df_clean.dropna(subset=['base_price', 'selling_price'])

    # Create figures
    figures = []

    # 1. Player Distribution by Role per fpl team
    fig_role = px.bar(df_clean.groupby('team_name')['role'].value_counts().reset_index(name='count'),
                    x='team_name', y='count', color='role',
                    title="Player Distribution by Role per fpl team",
                    labels={'team_name': 'Team Name', 'count': 'Count', 'role': 'Role'})
    
 
    figures.append(fig_role)

    # 2. Selling Price vs Base Price
    fig_price = px.scatter(df_clean, x="base_price", y="selling_price",
                        hover_data=['name', 'team_name'],
                        title="Selling Price vs Base Price",
                        labels={'base_price': 'Base Price', 'selling_price': 'Selling Price'},
                        color="team_name")
    figures.append(fig_price)

    # 3. Team-wise Player Distribution
    fig_team = px.pie(df_clean, names='team_name', title="Team-wise Player Distribution")
    figures.append(fig_team)

    # 4. Distribution of Players by Category
    fig_category = px.pie(df_clean, names='category', title="Distribution of Players by Category")
    figures.append(fig_category)

    # 5. Composite bar chart showing Distribution of Players by IPL Team within the fpl teams
    fig_ipl_team = px.bar(df_clean, x='team_name', color='ipl_team',
                        title="Distribution of Players by IPL Team within the fpl teams",
                        labels={'team_name': 'Team Name', 'ipl_team': 'IPL Team'},
                        barmode='group')
    # color_discrete_sequence=px.colors.qualitative.Pastel)
    fig_ipl_team.update_layout(legend_title_text='IPL Team')
    fig_ipl_team.update_xaxes(title_text='Team Name')
    fig_ipl_team.update_yaxes(title_text='Count')
    fig_ipl_team.update_traces(marker_line_width=0)
    fig_ipl_team.update_layout(legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1
    ))
    figures.append(fig_ipl_team)

    

    # 6. Average Selling Price by Role
    avg_price_by_role = df_clean.groupby('role')['selling_price'].mean().reset_index()
    fig_avg_role = px.bar(avg_price_by_role, x='role', y='selling_price',
                         title="Average Selling Price by Role")
    figures.append(fig_avg_role)

    # Create HTML for all visualizations
    plots_html = ""
    for fig in figures:
        plots_html += fig.to_html(full_html=False)

    # Add tables data
    top_players = df_clean[['name', 'selling_price', 'team_name']].sort_values(by="selling_price", ascending=False).head(10)
    avg_price_by_team = df_clean.groupby('team_name')['selling_price'].mean().reset_index()
    top_teams = avg_price_by_team.sort_values(by="selling_price", ascending=False).head(10)
    
    return render_template('insights.html', 
                         plots=plots_html,
                         top_players=top_players.to_dict('records'),
                         top_teams=top_teams.to_dict('records'))


@app.route('/fixtures')
def show_fixtures():
    # check if user is paid and approved
    device_id = get_device_id()
   

    return render_template('fixtures.html', fixtures=None)

@app.route('/fpl-ct-2025')
def show_previous_results():
    # check if user is paid and approved
    device_id = get_device_id()
   

    return render_template('FPL-CT2025-Points.html', results=None)


@app.route('/free-trial')
def activate_trial():
    device_id = get_device_id()
    expiry_date = datetime.now() + pd.Timedelta(days=5)     
    print(expiry_date)   
    # Check if device already has active paid subscription
    if is_approved(device_id):
        flash("You already have an active subscription", "info")
        return redirect(url_for('display_leaderboard'))
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Insert trial record with approval and expiry date

    cursor.execute("INSERT OR REPLACE INTO payments  (device_id, paid, approved, trial_expiry) VALUES (?, 1, 1, ?)", 
                            (device_id, expiry_date)) 
    
    conn.commit()
    conn.close()
    
    flash(f"Free trial activated until {expiry_date}", "success")
    return redirect(url_for('display_leaderboard'))

@app.route('/live-scoring')
def show_live_scoring():
    # check if user is paid and approved
    device_id = get_device_id()
    if not is_approved(device_id):
        return redirect(url_for('pay'))



    return render_template('live_scoring.html', scores=None)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
