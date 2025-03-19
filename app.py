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
from flask_sqlalchemy import SQLAlchemy

# Configuration
DATA_REFRESH_INTERVAL = 3600  # Refresh every hour
EXCEL_FILE_PATH = 'player_mapping.xlsx'  # Static data

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}


# Check if running on Azure (persistent storage available at `/mnt/sqlite`)
if os.environ.get("WEBSITE_SITE_NAME"):  # This env var exists only in Azure App Service
    DB_PATH = "/mnt/sqlite/cricbattle.db"
else:
    # Local development (stores DB in the instance folder)
    DB_PATH = "cricbattle.db"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your_secret_key'

# Configure SQLite URI correctly
app.config['DATABASE_PATH'] = DB_PATH
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.jinja_env.add_extension('jinja2.ext.do')

db = SQLAlchemy(app)

# Define models
class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String)
    txn_ref = db.Column(db.String)
    txn_proof = db.Column(db.LargeBinary)
    email = db.Column(db.String)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    paid = db.Column(db.Integer, default=0)
    trial_expiry = db.Column(db.DateTime)
    deleted = db.Column(db.Integer, default=0)
    approved = db.Column(db.Integer, default=0)

class Player(db.Model):
    __tablename__ = 'player'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    role = db.Column(db.String)
    category = db.Column(db.String) 
    ipl_team = db.Column(db.String)
    base_price = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    team_name = db.Column(db.String)
    is_sold = db.Column(db.Boolean)

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Import player data from mydatabase.db
def import_player_data():
    # Connect to source database
    src_conn = sqlite3.connect('mydatabase.db')
    src_cursor = src_conn.cursor()
    
    # Get player data
    src_cursor.execute('SELECT * FROM player')
    players = src_cursor.fetchall()
    
    # Close source connection
    src_conn.close()
    
    # Insert into Player model
    for player in players:
        player_obj = Player(
            id=player[0],
            name=player[1], 
            role=player[2],
            category=player[3],
            ipl_team=player[4],
            base_price=player[5],
            selling_price=player[6],
            team_name=player[7],
            is_sold=player[8]
        )
        db.session.merge(player_obj)
    
    db.session.commit()

# Call import function when app starts
with app.app_context():
    db.create_all()
    import_player_data()

def get_device_id():
    user_agent = request.headers.get('User-Agent', '')
    ip = request.remote_addr
    return hashlib.sha256(f"{user_agent}{ip}".encode()).hexdigest()

def is_approved(device_id):
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    return payment is not None and payment.approved == 1

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/pay', methods=['GET', 'POST'])
def pay():
    device_id = get_device_id()
    print(device_id)

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
            
            flash("Your payment confirmation has been submitted. Please wait for admin approval.", "success")
    
    return render_template('pay.html', qr_code="static/paypal_qr.jpeg")

@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    device_id = get_device_id()
    email = request.form.get('email')
    txn_ref = request.form.get('txn_ref')
    txn_proof = request.files.get('txn_proof')

    if email and txn_ref and txn_proof and allowed_file(txn_proof.filename):
        filename = secure_filename(txn_proof.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        txn_proof.save(file_path)
        
        with open(file_path, 'rb') as f:
            proof_blob = f.read()

        payment = Payment(
            device_id=device_id,
            email=email,
            txn_ref=txn_ref,
            txn_proof=proof_blob,
            paid=1
        )
        db.session.merge(payment)
        db.session.commit()

        return redirect(url_for('display_leaderboard'))

    elif email and txn_ref:
        payment = Payment(
            device_id=device_id,
            email=email,
            txn_ref=txn_ref,
            paid=1
        )
        db.session.merge(payment)
        db.session.commit()

        return redirect(url_for('display_leaderboard'))
    else:
        print("Invalid payment proof")
        flash("Invalid payment proof file", "danger")
    
def is_paid_but_not_approved(device_id):
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    return payment is not None and payment.paid == 1 and payment.approved == 0

def is_rejected(device_id):
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    return payment is not None and payment.paid == 1 and payment.approved == 2

@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == 'admin' and password == 'admin123':
            session['admin'] = True
            flash('Successfully logged in as admin', 'success')
            return redirect(url_for('admin_review'))
        else:
            flash('Invalid credentials', 'danger')
            
    return render_template('login.html')

@app.route('/admin/review', methods=['GET', 'POST'])
def admin_review():
    if session.get('admin') != True:
        return redirect(url_for('/admin/login'))

    if request.method == 'POST':
        device_id = request.form.get('device_id')
        action = request.form.get('action')

        payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
        if payment:
            if action == 'approve':
                payment.approved = 1
                flash(f"Payment for device {device_id} approved", "success")
            elif action == 'reject':
                payment.approved = 0
                flash(f"Payment for device {device_id} rejected", "danger")
            db.session.commit()

    pending_payments = Payment.query.all()
    
    for payment in pending_payments:
        if payment.txn_proof:
            with open(f"static/uploads/{payment.device_id}.png", "wb") as f:
                f.write(payment.txn_proof)
                payment.txn_proof = url_for('static', filename=f"uploads/{payment.device_id}.png")

    print(pending_payments)
    
    return render_template('paid_not_approved.html', payments=[{
    'device_id': payment.device_id,
    'txn_ref': payment.txn_ref, 
    'email': payment.email,
    'timestamp': payment.timestamp,
    'paid': payment.paid,
    'approved': payment.approved,
    'txn_proof': payment.txn_proof,
    'trial_expiry': payment.trial_expiry.strftime('%Y-%m-%d %H:%M:%S') if payment.trial_expiry else None,
    'deleted': payment.deleted
} for payment in pending_payments])

@app.route('/')
def display_leaderboard():
    device_id = get_device_id()
    print(device_id)

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
        
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    if payment:
        payment.approved = 1
        db.session.commit()
    
    return {'message': f'Payment for device {device_id} approved'}, 200

@app.route('/admin/reject/<device_id>', methods=['POST']) 
def reject_payment(device_id):
    if session.get('admin') != True:
        return {'error': 'Unauthorized'}, 401
        
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    if payment:
        payment.approved = 2
        db.session.commit()
    
    return {'message': f'Payment for device {device_id} rejected'}, 200
         
@app.route('/reset-payment', methods=['POST'])
def reset_payment():
    device_id = get_device_id()
    print(device_id)
        
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    if payment:
        payment.deleted = 1
        db.session.commit()

    return redirect(url_for('display_leaderboard'))

@app.route('/insights')
def show_insights():
    device_id = get_device_id()
    if not is_approved(device_id):
        return redirect(url_for('pay'))

    players = Player.query.all()
    df = pd.DataFrame([{
        'name': p.name,
        'role': p.role,
        'category': p.category,
        'ipl_team': p.ipl_team,
        'base_price': p.base_price,
        'selling_price': p.selling_price,
        'team_name': p.team_name,
        'is_sold': p.is_sold
    } for p in players])

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
                        labels={'team_name': '', 'ipl_team': 'IPL Team'},
                        barmode='group')
    fig_ipl_team.update_layout(legend_title_text='IPL Team')
    #fig_ipl_team.update_xaxes(title_text='Team Name', tickangle=45)
    fig_ipl_team.update_yaxes(title_text='Count')
    fig_ipl_team.update_traces(marker_line_width=0)
    fig_ipl_team.update_layout(legend=dict(
        orientation="h", 
        yanchor="top",
        y=-0.2,
        xanchor="center",
        x=0.5
    ),
    margin=dict(b=150))    
    figures.append(fig_ipl_team)

    
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




@app.route('/free-trial')
def activate_trial():
    device_id = get_device_id()
    expiry_date = datetime.now() + pd.Timedelta(days=5)     
    print(expiry_date)   
    # Check if device already has active paid subscription
    if is_approved(device_id):
        flash("You already have an active subscription", "info")
        return redirect(url_for('display_leaderboard'))
        
    payment = Payment(
        device_id=device_id,
        paid=1,
        approved=1,
        trial_expiry=expiry_date
    )
    db.session.merge(payment)
    db.session.commit()

    flash(f"Free trial activated until {expiry_date}", "success")
    return redirect(url_for('display_leaderboard'))

@app.route('/live-scoring')
def show_live_scoring():
    # check if user is paid and approved
    device_id = get_device_id()
    if not is_approved(device_id):
        return redirect(url_for('pay'))



    return render_template('live_scoring.html', scores=None)

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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
