from datetime import datetime
import json
import os
import time
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
import plotly.express as px
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, update, func
from sqlalchemy.orm import sessionmaker, declarative_base
import logging  
from datetime import datetime  
import update_scores_html as update_scores
from apscheduler.schedulers.background import BackgroundScheduler
import update_series_stats
import update_scores_from_scoreboard
from datetime import timedelta


  
# Configure logging  
logging.basicConfig(  
    level=logging.INFO,  
    format='%(asctime)s - %(levelname)s - %(message)s',  
    datefmt='%Y-%m-%d %H:%M:%S'  
) 

# Configuration
DATA_REFRESH_INTERVAL = 3600  # Refresh every hour
EXCEL_FILE_PATH = 'player_mapping.xlsx'  # Static data

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}


# Check if running on Azure (persistent storage available at `/mnt/sqlite`)
if os.environ.get("WEBSITE_SITE_NAME"):  # This env var exists only in Azure App Service
    DB_PATH = "/mnt/sqlite/cricbattle.db"
    debug = False
else:
    # Local development (stores DB in the instance folder)
    DB_PATH = "cricbattle.db"
    debug = True

DATABASE_URL = f"sqlite:///{DB_PATH}"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'your_secret_key'

# Configure SQLite URI correctly
app.config['DATABASE_PATH'] = DB_PATH
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.jinja_env.add_extension('jinja2.ext.do')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True


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
    __tablename__ = 'player_v3'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    role = db.Column(db.String)
    category = db.Column(db.String) 
    ipl_team = db.Column(db.String)
    base_price = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    team_name = db.Column(db.String)
    is_sold = db.Column(db.Boolean)
    points_reduction = db.Column(db.Integer)
    first_match_id = db.Column(db.Integer)
    foreign_player = db.Column(db.Boolean)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    name_array = db.Column(db.String)
    traded = db.Column(db.Boolean)

# Define Match Model
class Match(db.Model):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True)
    matchId = Column(Integer)
    date = Column(String)
    match_info = Column(String)
    time = Column(String)

# Define player_rankings model
class PlayerRanking(db.Model):
    __tablename__ = 'player_ranking_v3'
    PlayerId = db.Column(db.Integer, primary_key=True)
    PRank = db.Column(db.Integer)
    Rank = db.Column(db.Integer)
    PlayerName = db.Column(db.String)
    PlayerTypeId = db.Column(db.Integer)
    PlayerFormId = db.Column(db.Integer)
    IsOut = db.Column(db.Integer)
    IsInjured = db.Column(db.Integer)
    Price = db.Column(db.Float)
    RealTeamName = db.Column(db.String)
    TotalScore = db.Column(db.Integer)
    IsShowTrophy = db.Column(db.Integer)

# Define player_rankings model
class PlayerRankingPerDay(db.Model):
    __tablename__ = 'player_ranking_daily_v3'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)    
    PlayerId = db.Column(db.Integer)
    PRank = db.Column(db.Integer)
    Rank = db.Column(db.Integer)
    PlayerName = db.Column(db.String)
    PlayerTypeId = db.Column(db.Integer)
    PlayerFormId = db.Column(db.Integer)
    IsOut = db.Column(db.Integer)
    IsInjured = db.Column(db.Integer)
    Price = db.Column(db.Float)
    RealTeamName = db.Column(db.String)
    TotalScore = db.Column(db.Integer)
    IsShowTrophy = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


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
    
    # Insert into Player model only if Player table is empty
    if Player.query.count() == 0:
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
            db.session.add(player_obj)
      
    #alter table player add COLUMN foreign_player 

        # Set foreign_player = 0 for uncapped players
        logging.info("Started Setting foreign_player status")
        Player.query.filter_by(category='Uncapped').update({Player.foreign_player: False})

        # Set foreign_player = 1 for specific player IDs
        foreign_player_ids = [4,6,7,9,10,15,17,20,24,29,31,32,33,35,38,40,41,42,45,47,48,52,55,57,64,69,72,74,75,77,78,79,80,81,82,83,87,88,91,94,95,96,97,98,99,100,101,102,103,104,105,107,108,109,111,112,114,115,116,118,119,120,125,121,126,127,128,130,133,192,191]
        Player.query.filter(Player.id.in_(foreign_player_ids)).update({Player.foreign_player: True}, synchronize_session=False)

        # Set foreign_player = 0 where it is null
        Player.query.filter(Player.foreign_player.is_(None)).update({Player.foreign_player: False})
        logging.info("Finished Setting foreign_player status")

    
    db.session.commit()

# Function to make a POST request and get data    
def get_data_from_api(url, headers, data):    
    try:  
        response = requests.post(url, headers=headers, json=data)    
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx and 5xx)  
        return response.json()   
    except requests.exceptions.HTTPError as err:  
        print(f"HTTP error occurred: {err}")  
    except requests.exceptions.RequestException as err:  
        print(f"Error occurred: {err}")  
    return None    
    
# Function to save data to Excel    
def save_to_excel(data, filename):    
    try:  
        df = pd.DataFrame(data['Result'])  
        df.to_excel(filename, index=False)     
        logging.info(f"Data saved to {filename}") 
    except Exception as e:  
        print(f"Error saving data to Excel: {e}")  

# Function to save data to database in PlayerRanking model
def save_to_database(data):
    try:
        for player_data in data['Result']:
            player = PlayerRanking(
                PlayerId=player_data['PlayerId'],
                PlayerName=player_data['PlayerName'],
                PlayerTypeId=player_data['PlayerTypeId'],
                PlayerFormId=player_data['PlayerFormId'],
                IsOut=player_data['IsOut'],
                IsInjured=player_data['IsInjured'],
                Price=player_data['Price'],
                RealTeamName=player_data['RealTeamName'],
                TotalScore=player_data['TotalScore'],
                IsShowTrophy=player_data['IsShowTrophy'],
                PRank=player_data['PRank'],
                Rank=player_data['Rank']    
            )
            db.session.merge(player)

        db.session.commit()
        logging.info("Data saved to database")
    except Exception as e:
        print(f"Error saving data to database: {e}")
    
def player_of_the_day():

    logging.info("Getting player of the day")

    # get today's date and yesterday's date 
    today = datetime.now().date()
    yesterday = today - pd.Timedelta(days=1)

    stmt = update(PlayerRankingPerDay).where(
        func.strftime('%Y-%m-%d %H', PlayerRankingPerDay.timestamp) == '2025-03-23 00'
        ).values(
            timestamp=PlayerRankingPerDay.timestamp - timedelta(days=1)
        )

    # Commit changes
    db.session.commit()

    # get player of the day for today and yesterday
    today_player = PlayerRankingPerDay.query.filter(
        db.func.date(PlayerRankingPerDay.timestamp) == today,        
        PlayerRankingPerDay.TotalScore > 0  # Only consider players with positive score
    ).order_by(PlayerRankingPerDay.TotalScore.desc()).first()

    yesterday_player = PlayerRankingPerDay.query.filter(
        db.func.date(PlayerRankingPerDay.timestamp) == yesterday,  
        PlayerRankingPerDay.TotalScore > 0  # Only consider players with positive score
    ).order_by(PlayerRankingPerDay.TotalScore.desc()).first()

    # get corresponding Player records
    today_player_details = None
    yesterday_player_details = None

    print(today_player, yesterday_player)

    if today_player and today_player.TotalScore > 0:
        today_player_details = Player.query.filter_by(name=today_player.PlayerName).first()
    
    if yesterday_player and yesterday_player.TotalScore > 0:
        yesterday_player_details = Player.query.filter_by(name=yesterday_player.PlayerName).first()

    print(today_player_details, yesterday_player_details)

    team_of_the_day()

    return {
    'today': {
        'name': today_player_details.name if today_player_details else None,
        'team': today_player_details.team_name if today_player_details else None,
        'points': today_player.TotalScore if today_player else 0
    },
    'yesterday': {
        'name': yesterday_player_details.name if yesterday_player_details else None, 
        'team': yesterday_player_details.team_name if yesterday_player_details else None,
        'points': yesterday_player.TotalScore if yesterday_player else 0
    }
}


def team_of_the_day():
    logging.info("Getting team of the day")

    # get today's date and yesterday's date
    today = datetime.now().date()
    yesterday = today - pd.Timedelta(days=1)

   

    # get all players for today and yesterday with latest timestamp
    today_players = (PlayerRankingPerDay.query
        .filter(db.func.date(PlayerRankingPerDay.timestamp) == today)
        .filter(PlayerRankingPerDay.TotalScore > 0)
        .group_by(PlayerRankingPerDay.PlayerId)
        .having(PlayerRankingPerDay.timestamp == db.func.max(PlayerRankingPerDay.timestamp))
        .all())

    yesterday_players = (PlayerRankingPerDay.query
        .filter(db.func.date(PlayerRankingPerDay.timestamp) == yesterday)
        .filter(PlayerRankingPerDay.TotalScore > 0)
        .group_by(PlayerRankingPerDay.PlayerId) 
        .having(PlayerRankingPerDay.timestamp == db.func.max(PlayerRankingPerDay.timestamp))
        .all())
    
    print(today_players)
    
    # calculate team scores for today
    today_team_scores = {}
    for player in today_players:
        player_details = Player.query.filter_by(name=player.PlayerName).first()
        if player_details and player_details.team_name:
            if player_details.team_name not in today_team_scores:
                today_team_scores[player_details.team_name] = 0
            today_team_scores[player_details.team_name] += player.TotalScore

    # calculate team scores for yesterday
    yesterday_team_scores = {}
    for player in yesterday_players:
        player_details = Player.query.filter_by(name=player.PlayerName).first()
        if player_details and player_details.team_name:
            if player_details.team_name not in yesterday_team_scores:
                yesterday_team_scores[player_details.team_name] = 0
            yesterday_team_scores[player_details.team_name] += player.TotalScore

    # find team with highest score for today and yesterday
    today_best_team = max(today_team_scores.items(), key=lambda x: x[1]) if today_team_scores else (None, 0)
    yesterday_best_team = max(yesterday_team_scores.items(), key=lambda x: x[1]) if yesterday_team_scores else (None, 0)

    print(today_team_scores, yesterday_team_scores)

    print(today_best_team, yesterday_best_team)

    return {
        'today': {'team': today_best_team[0], 'score': today_best_team[1]},
        'yesterday': {'team': yesterday_best_team[0], 'score': yesterday_best_team[1]}
    }


# Add this in the refresh_scores() function:
def refresh_scores():

    # call player of the day and team of the day methods in app.py
    # The variables are unbound because the function names are the same as the variable names
    # To fix this, rename the variables to be different from the function names:

    pod = player_of_the_day()
    totd = team_of_the_day()   

    # Update scores
    update_scores.main(Player, PlayerRanking, pod, totd)    

def get_cricbattle_data():
    # URL and headers extracted from HAR file    
    url = "https://m.cricbattle.com/PlayerRanking/GetTournamentPlayerRankingSummData"    
    
    # Define the headers    
    headers = {    
        "accept": "*/*",    
        "accept-encoding": "gzip, deflate, br, zstd",    
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",    
        "cache-control": "no-cache",    
        "content-type": "application/json; charset=UTF-8",    
        "cookie": "ASP.NET_SessionId=lsbsnq5gnmdyqloqojn5eejt; _ga=GA1.2.833922002.1739971081; _gid=GA1.2.1190173817.1739971081; _gat=1; _gat_cball=1; _ga_QMWJRKE48H=GS1.2.1739971081.1.1.1739972062.0.0.0; _ga_SS5VS26HPP=GS1.2.1739971081.1.1.1739972062.0.0.0",    
        "origin": "https://m.cricbattle.com",    
        "pragma": "no-cache",    
        "referer": "https://m.cricbattle.com/Player-Ranking??LeagueModel=Draft",    
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",    
        "x-requested-with": "XMLHttpRequest"    
    }    
  
    payload = {  
        "tid": 12746,  
        "ptype": "0",  
        "roundorday": "",  
        "phaseid": "0"  
    }  

    data = get_data_from_api(url, headers, payload)  
    #save_to_excel(data, "player_rankings.xlsx")  

    # set global variable with latest timestamp
    global latest_timestamp

    latest_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_to_database(data)

# method to copy data from playerranking model to playerrankingperday model
def copy_data_from_player_ranking_to_player_ranking_per_day():
    logging.info("Copying data from player_ranking to player_ranking_per_day")
    with app.app_context():
        # Get all data from PlayerRanking model
        players = PlayerRanking.query.all()

        # Iterate over each player
        for player in players:
            # Create a new PlayerRankingPerDay object
            player_ranking_per_day = PlayerRankingPerDay(
                PlayerId=player.PlayerId,
                PRank=player.PRank,
                Rank=player.Rank,
                PlayerName=player.PlayerName,
                PlayerTypeId=player.PlayerTypeId,
                PlayerFormId=player.PlayerFormId,
                IsOut=player.IsOut,
                IsInjured=player.IsInjured,
                Price=player.Price,
                RealTeamName=player.RealTeamName,
                TotalScore=player.TotalScore,
                IsShowTrophy=player.IsShowTrophy,
                #timestamp=datetime.now() # Add timestamp when creating record
            )

            # Add the new object to the session
            db.session.add(player_ranking_per_day)

        # Commit the changes to the database
        db.session.commit()




# Schedule get_cricbattle_data to run every 5 minutes with app context
def scheduled_task():
    with app.app_context():
        logging.info("Running scheduled task")
        get_cricbattle_data()
        refresh_scores()
        df_series = update_series_stats.main(Player)
        df_scoreboard = update_scores_from_scoreboard.main(Match)

INIT_FILE = "app_initialized.lock"

# The code is likely being called multiple times due to Flask's development server behavior
# Add a check to prevent multiple initializations
with app.app_context():
    # Only run initialization if not already done
    if not os.path.exists(INIT_FILE):
        logging.info("Starting app initialization")
        db.create_all()
        import_player_data()
        get_cricbattle_data()
        df_series = update_series_stats.main(Player)
        df_scoreboard = update_scores_from_scoreboard.main(Match)
        copy_data_from_player_ranking_to_player_ranking_per_day()
        player_of_the_day()

        # Initialize scheduler only if not already started
        if not app.config.get("SCHEDULER_STARTED", False):
            app.scheduler = BackgroundScheduler()
            app.scheduler.add_job(func=scheduled_task, trigger="cron", minute="*/2", hour="0-23")        
            app.scheduler.add_job(func=copy_data_from_player_ranking_to_player_ranking_per_day, trigger="cron", hour=20)        
            app.scheduler.start()
            app.config["SCHEDULER_STARTED"] = True

        # Mark initialization as complete
        with open(INIT_FILE, "w") as f:
            f.write("initialized")
        logging.info("App initialization complete")


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
        
        if username == 'admin' and password == 'admin13$':
            session['admin'] = True
            flash('Successfully logged in as admin', 'success')
            return redirect(url_for('admin_review'))
        else:
            flash('Invalid credentials', 'danger')
            
    return render_template('login.html')

@app.route('/admin/review', methods=['GET', 'POST'])
def admin_review():
    if session.get('admin') != True:
        return redirect(url_for('login'))

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
def welcome():
    return render_template('welcome.html')

@app.route('/home')
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

    #refresh_scores()

    latest_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return render_template('FPL-IPL2025-Points.html', timestamp=latest_timestamp)


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







# Function to extract match details from HTML
def extract_match_details(html_file):
    with open(html_file, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "lxml")

    # Further refining the extraction logic based on observed HTML structure

    match_data = []

    # Finding all match entries
    match_entries = soup.find_all("div", class_="cb-col-75 cb-col")

    for entry in match_entries:
        # Extract matchId (from the nearest schedule-date class)
        match_id_div = entry.find_next("div", class_="cb-col-60 cb-col cb-srs-mtchs-tm")
        match_id_tag = match_id_div.find_next("a", class_="text-hvr-underline")
        matchId_href = match_id_tag.get("href") if match_id_tag else "Unknown"
        #extract matchid from /live-cricket-scores/114960/kkr-vs-rcb-1st-match-ipl-2025
        matchId = matchId_href.split("/")[2] if matchId_href != "Unknown" else 999999

        # Extract date (from the nearest schedule-date class)
        date_tag = entry.find_previous("div", class_="schedule-date")
        date = date_tag.text.strip() if date_tag else "Unknown"

        # Extract match details
        match_info_tag = entry.find("a", class_="text-hvr-underline")
        match_info = match_info_tag.text.strip() if match_info_tag else "Unknown"

        if match_info == "Unknown":
            quali_match_info_tag = entry.find("div", class_="cb-col-60 cb-col cb-srs-mtchs-tm")
            quali_match_info = quali_match_info_tag.find("span")
            match_info = quali_match_info.text.strip() if quali_match_info else "Unknown"


        # Extract time (from schedule-date class within the same entry)
        time_tag = entry.find_next("div", class_="cb-font-12 text-gray")
        time = time_tag.text.strip() if time_tag else "Unknown"

        match_data.append({"matchId":matchId, "date": date, "match_info": match_info, "time": time})

    # Convert to JSON
    match_data_json = json.dumps(match_data, indent=4)
    

    return match_data_json

# Insert extracted data into SQLite
def save_to_db(matches):
    json_matches = json.loads(matches)
    for match in json_matches:
        #session.add(Match(date=match["date"], match_info=match["match_info"], time=match["time"]))
        new_match = Match(matchId=match["matchId"], date=match["date"], match_info=match["match_info"], time=match["time"])
        if not match["date"] and match["match_info"] in "Chennai Super Kings vs Mumbai Indians, 3rd Match":
            match["date"] = "Mar 23, Sun"
            new_match = Match(matchId=match["matchId"], date=match["date"], match_info=match["match_info"], time=match["time"])
        db.session.merge(new_match)


    db.session.commit()


# Flask Route to display matches
@app.route("/matches")
@app.route("/matches/refresh")
def show_matches():
    refresh = 'refresh' in request.path    
    if refresh:
        db.session.query(Match).delete()
        print("Extracting matches")
        matches = extract_match_details("static/matches.html")  
        save_to_db(matches)
        
    matches = db.session.query(Match.date, Match.match_info, Match.time).all()    
    return render_template("matches.html", matches=matches)


@app.route('/admin/players', methods=['GET', 'POST'])
def admin_players():
    if session.get('admin') != True:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Handle add/edit player
        player_id = request.form.get('id')
        player_data = {
            'name': request.form.get('name'),
            'role': request.form.get('role'),
            'category': request.form.get('category'),
            'ipl_team': request.form.get('ipl_team'),
            'base_price': float(request.form.get('base_price')),
            'selling_price': float(request.form.get('selling_price')),
            'team_name': request.form.get('team_name'),
            'is_sold': bool(request.form.get('is_sold')),
            'points_reduction': int(request.form.get('points_reduction') or 0),
            'first_match_id': int(request.form.get('first_match_id') or 0),
            'foreign_player': bool(request.form.get('foreign_player')),
            'name_array': request.form.getlist('names[]'),
            'traded': bool(request.form.get('traded'))
        }

        if player_id:
            # Edit existing player
            Player.query.filter_by(id=player_id).update(player_data)
            flash('Player updated successfully', 'success')
        else:
            # Add new player
            new_player = Player(**player_data)
            db.session.add(new_player)
            flash('Player added successfully', 'success')

        db.session.commit()
        return redirect(url_for('admin_players'))

    # GET request - show all players
    players = Player.query.all()
    return render_template('admin_players.html', players=players)

@app.route('/admin/players/delete/<int:id>', methods=['POST'])
def delete_player(id):
    if session.get('admin') != True:
        return {'error': 'Unauthorized'}, 401

    player = Player.query.get_or_404(id)
    db.session.delete(player)
    db.session.commit()
    flash('Player deleted successfully', 'success')
    return redirect(url_for('admin_players'))

@app.route('/admin/players/edit/<int:id>', methods=['GET', 'POST'])
def edit_player(id):
    if session.get('admin') != True:
        return redirect(url_for('login'))

    player = Player.query.get_or_404(id)    
    if request.method == 'POST':
        data = request.get_json()

        if player:
            player.name = data.get('name', player.name)
            player.role = data.get('role', player.role)
            player.category = data.get('category', player.category)
            player.ipl_team = data.get('ipl_team', player.ipl_team)
            player.base_price = data.get('base_price', player.base_price)
            player.selling_price = data.get('selling_price', player.selling_price)
            player.team_name = data.get('team_name', player.team_name)
            player.is_sold = data.get('is_sold', player.is_sold)  
            player.points_reduction = data.get('points_reduction', player.points_reduction) 
            player.first_match_id = data.get('first_match_id', player.first_match_id)
            player.foreign_player = data.get('foreign_player', player.foreign_player)  
            player.name_array = data.get('name_array', player.name_array)
            player.traded = data.get('traded', player.traded) 
            db.session.merge(player)        
            db.session.commit()
            return {'message': 'Player updated successfully'}, 200
    return render_template('edit_player.html', player=player)

  

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=debug)
