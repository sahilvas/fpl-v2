from datetime import datetime
from functools import wraps
import json
import os
import random
import time
import uuid
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
import jal_app
from flask import Flask, render_template, request, session, redirect, url_for, flash, make_response
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
import plotly.express as px
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, update, func, case, text
from sqlalchemy.orm import sessionmaker, declarative_base, aliased
import logging  
from datetime import datetime  
import update_scores_html as update_scores
from apscheduler.schedulers.background import BackgroundScheduler
import update_series_stats
import update_scores_from_scoreboard
from datetime import timedelta
from datetime import timedelta
from flask import flash


  
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


#model to store logs
class Log(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    message = db.Column(db.String)

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

class JALPlayer(db.Model):
    __tablename__ = 'jal_players'
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


class FantasyTeam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    emoji = db.Column(db.String(10), default=None)  # Store emoji
    emoji_expiry = db.Column(db.DateTime, default=None)  # Expiry time


class EmojiReaction(db.Model):
    __tablename__ = 'emoji_reactions_v1'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String, nullable=False)
    value = db.Column(db.String, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class PageView(db.Model):
    __tablename__ = 'page_views_v1'
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String)
    device_id = db.Column(db.String)
    views = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# create db model for Prediction table
class Prediction(db.Model):
    __tablename__ = 'prediction_v1'
    id = db.Column(db.Integer, primary_key=True)
    matchId = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    prediction_type = db.Column(db.String(100), default="match")
    prediction_value = db.Column(db.String(100), nullable=False)
    prediction_result = db.Column(db.String(100), default="pending")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# Add User model
class User(db.Model):
    __tablename__ = 'user_v1'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)


# Add model for actual result for prediction events
class ActualResult(db.Model):
    __tablename__ = 'actual_result_v1'
    id = db.Column(db.Integer, primary_key=True)
    matchId = db.Column(db.String(100), nullable=False)
    event_type = db.Column(db.String(100), default="match")
    event_result = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# method to store passed argument (text lines, variables, pandas df) to Log table
def log_to_db(message):
    try:
        timestamp = datetime.now()
        log_entry = Log(message=message, timestamp=timestamp)
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        logging.error(f"Error logging to database: {e}")
        db.session.rollback()

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
    
def player_of_the_day(league=""):

    logging.info(f"Getting player of the day for league {league}")

    # get today's date and yesterday's date 
    today = datetime.now().date()
    yesterday = today - pd.Timedelta(days=1)
    day_before_yesterday = today - pd.Timedelta(days=2)

    stmt = update(PlayerRankingPerDay).where(
        func.strftime('%Y-%m-%d', PlayerRankingPerDay.timestamp) == '2025-03-23',
        func.strftime('%H', PlayerRankingPerDay.timestamp) == '00'
        ).values(
            timestamp=func.datetime(func.strftime('%Y-%m-%d', PlayerRankingPerDay.timestamp, '-1 day'), 
                                  func.strftime('%H:%M:%S', PlayerRankingPerDay.timestamp))
        )
    
    # Execute the update statement
    db.session.execute(stmt)

    # Commit changes
    db.session.commit()

    # Aliases for the same table (to compare today vs yesterday)
    TodayPlayer = aliased(PlayerRanking)
    YesterdayPlayer = aliased(PlayerRankingPerDay)
    DayBeforeYesterdayPlayer = aliased(PlayerRankingPerDay)


    # Query today's players with the latest timestamp
    today_players_subquery = (
        db.session.query(
            TodayPlayer.PlayerId,
            TodayPlayer.PlayerName,
            TodayPlayer.TotalScore.label("today_score"),
            
        )
       
        .filter(TodayPlayer.TotalScore > 0)
        .group_by(TodayPlayer.PlayerId)
        .subquery()
    )

    # Query yesterday's players with the latest timestamp
    yesterday_players_subquery = (
        db.session.query(
            YesterdayPlayer.PlayerId,
            YesterdayPlayer.PlayerName,
            YesterdayPlayer.TotalScore.label("yesterday_score"),
            func.max(YesterdayPlayer.timestamp).label("latest_timestamp")
        )
        .filter(func.date(YesterdayPlayer.timestamp) == yesterday)
        .group_by(YesterdayPlayer.PlayerId)
        .subquery()
    )

    day_before_yesterday_players_subquery = (
        db.session.query(
            DayBeforeYesterdayPlayer.PlayerId,
            DayBeforeYesterdayPlayer.PlayerName,
            DayBeforeYesterdayPlayer.TotalScore.label("day_before_yesterday_score"),
            func.max(DayBeforeYesterdayPlayer.timestamp).label("latest_timestamp")
        )
        .filter(func.date(DayBeforeYesterdayPlayer.timestamp) == day_before_yesterday)
        .group_by(DayBeforeYesterdayPlayer.PlayerId)
        .subquery()
    )


    players_with_score_difference = (
        db.session.query(
            Player.id if league != "JAL" else JALPlayer.id,
            Player.name if league != "JAL" else JALPlayer.name,
            Player.team_name if league != "JAL" else JALPlayer.team_name,
            today_players_subquery.c.today_score,
            func.coalesce(yesterday_players_subquery.c.yesterday_score, 0).label("yesterday_score"),
            func.coalesce(day_before_yesterday_players_subquery.c.day_before_yesterday_score, 0).label("day_before_yesterday_score"),
        
                    (today_players_subquery.c.today_score - func.coalesce(yesterday_players_subquery.c.yesterday_score, 0)
                    ).label("score_difference"),
            case(
                (
                    (yesterday_players_subquery.c.yesterday_score - func.coalesce(day_before_yesterday_players_subquery.c.day_before_yesterday_score, 0)) < 0,
                    0
                ),
                else_=(
                    yesterday_players_subquery.c.yesterday_score - func.coalesce(day_before_yesterday_players_subquery.c.day_before_yesterday_score, 0)
                )
            ).label("day_before_yesterday_score_difference")
        )
        .outerjoin(today_players_subquery, (Player.name if league != "JAL" else JALPlayer.name) == today_players_subquery.c.PlayerName)
        .outerjoin(yesterday_players_subquery, (Player.name if league != "JAL" else JALPlayer.name) == yesterday_players_subquery.c.PlayerName)
        .outerjoin(day_before_yesterday_players_subquery, (Player.name if league != "JAL" else JALPlayer.name) == day_before_yesterday_players_subquery.c.PlayerName)
        .filter((Player.team_name if league != "JAL" else JALPlayer.team_name).isnot(None))
        .all()
        )

    # Sort players by col score_difference in descending order
    players_with_score_difference.sort(key=lambda x: x[6] if x[6] is not None else 0, reverse=True)

    # convert players_with_score_difference to df
    players_with_score_difference_df = pd.DataFrame(players_with_score_difference, columns=['id', 'name', 'team_name', 'today_score', 'yesterday_score', 'day_before_yesterday_score', 'score_difference', 'day_before_yesterday_score_difference'])

    # Get the player with the highest score_difference
    today_player = players_with_score_difference[0] if players_with_score_difference else None

    # Sort players by col day_before_yesterday_score_difference in descending order
    players_with_score_difference.sort(key=lambda x: x[7] if x[7] is not None else 0, reverse=True)

    # Get the player with the highest day_before_yesterday_score_difference
    yesterday_player = players_with_score_difference[0] if players_with_score_difference else None

    logging.info(f"Today's player: {today_player}, Yesterday's player: {yesterday_player}")

    team_of_the_day()

    return {
    'today': {
        'name': today_player.name if today_player else None,
        'team': today_player.team_name if today_player else None,
        'points': today_player.score_difference if today_player else 0
    },
    'yesterday': {
        'name': yesterday_player.name if yesterday_player else None, 
        'team': yesterday_player.team_name if yesterday_player else None,
        'points': yesterday_player.day_before_yesterday_score_difference if yesterday_player else 0
    },
    'players_with_score_difference_df': players_with_score_difference_df
}



def team_of_the_day(league=""):
    logging.info(f"Getting team of the day for league {league}")

    # Get today's and yesterday's dates
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    day_before_yesterday = today - timedelta(days=2)

    # Aliases for the same table (to compare today vs yesterday)
    TodayPlayer = aliased(PlayerRanking)
    YesterdayPlayer = aliased(PlayerRankingPerDay)
    DayBeforeYesterdayPlayer = aliased(PlayerRankingPerDay)



    # Query today's players with the latest timestamp
    today_players_subquery = (
        db.session.query(
            TodayPlayer.PlayerId,
            TodayPlayer.PlayerName,
            TodayPlayer.TotalScore.label("today_score")
        )
        .filter(TodayPlayer.TotalScore > 0)
        .group_by(TodayPlayer.PlayerId)
        .subquery()
    )

    # Query yesterday's players with the latest timestamp
    yesterday_players_subquery = (
        db.session.query(
            YesterdayPlayer.PlayerId,
            YesterdayPlayer.PlayerName,
            YesterdayPlayer.TotalScore.label("yesterday_score"),
            func.max(YesterdayPlayer.timestamp).label("latest_timestamp")
        )
        .filter(func.date(YesterdayPlayer.timestamp) == yesterday)
        .group_by(YesterdayPlayer.PlayerId)
        .subquery()
    )

    day_before_yesterday_players_subquery = (
        db.session.query(
            DayBeforeYesterdayPlayer.PlayerId,
            DayBeforeYesterdayPlayer.PlayerName,
            DayBeforeYesterdayPlayer.TotalScore.label("day_before_yesterday_score"),
            func.max(DayBeforeYesterdayPlayer.timestamp).label("latest_timestamp")
        )
        .filter(func.date(DayBeforeYesterdayPlayer.timestamp) == day_before_yesterday)
        .group_by(DayBeforeYesterdayPlayer.PlayerId)
        .subquery()
    )


    players_with_score_difference = (
        db.session.query(
            Player.id if league != "JAL" else JALPlayer.id,
            Player.name if league != "JAL" else JALPlayer.name,
            Player.team_name if league != "JAL" else JALPlayer.team_name,
            today_players_subquery.c.today_score,
            func.coalesce(yesterday_players_subquery.c.yesterday_score, 0).label("yesterday_score"),
            func.coalesce(day_before_yesterday_players_subquery.c.day_before_yesterday_score, 0).label("day_before_yesterday_score"),
            case(
                (
                    (today_players_subquery.c.today_score - func.coalesce(yesterday_players_subquery.c.yesterday_score, 0)) < 0,
                    0
                ),
                else_=(
                    today_players_subquery.c.today_score - func.coalesce(yesterday_players_subquery.c.yesterday_score, 0)
                )
            ).label("score_difference"),
            case(
                (
                    (yesterday_players_subquery.c.yesterday_score - func.coalesce(day_before_yesterday_players_subquery.c.day_before_yesterday_score, 0)) < 0,
                    0
                ),
                else_=(
                    yesterday_players_subquery.c.yesterday_score - func.coalesce(day_before_yesterday_players_subquery.c.day_before_yesterday_score, 0)
                )
            ).label("day_before_yesterday_score_difference")
        )
        .outerjoin(today_players_subquery, (Player.name if league != "JAL" else JALPlayer.name) == today_players_subquery.c.PlayerName)
        .outerjoin(yesterday_players_subquery, (Player.name if league != "JAL" else JALPlayer.name) == yesterday_players_subquery.c.PlayerName)
        .outerjoin(day_before_yesterday_players_subquery, (Player.name if league != "JAL" else JALPlayer.name) == day_before_yesterday_players_subquery.c.PlayerName)
        .filter((Player.team_name if league != "JAL" else JALPlayer.team_name).isnot(None))
        .all()
        )

    # Dictionary to store today's and yesterday's team scores
    today_team_scores = {}
    yesterday_team_scores = {}


    #print(players_with_score_difference)

    # Loop through players with score differences
    for player in players_with_score_difference:
        if player.team_name:
            # Initialize team score if not present
            if player.team_name not in today_team_scores:
                today_team_scores[player.team_name] = 0
            if player.team_name not in yesterday_team_scores:
                yesterday_team_scores[player.team_name] = 0

            # Add score differences for today, ensuring None values are treated as 0
            today_team_scores[player.team_name] += player.score_difference if player.score_difference is not None else 0
            yesterday_team_scores[player.team_name] += player.day_before_yesterday_score_difference if player.day_before_yesterday_score_difference is not None else 0  # Same for yesterday's score


    # Log team scores for today
    for team, score in today_team_scores.items():
        logging.info(f"Team {team}: Score = {score}")

    # Find best team for today and yesterday
    today_best_team = max(today_team_scores.items(), key=lambda x: x[1]) if today_team_scores else (None, 0)
    yesterday_best_team = max(yesterday_team_scores.items(), key=lambda x: x[1]) if yesterday_team_scores else (None, 0)

    # Log the best teams
    logging.info(f"Best team today: {today_best_team[0]}, score: {today_best_team[1]}")
    logging.info(f"Best team yesterday: {yesterday_best_team[0]}, score: {yesterday_best_team[1]}")

    #exit()

    return {
        'today': {'team': today_best_team[0], 'score': today_best_team[1]},
        'yesterday': {'team': yesterday_best_team[0], 'score': yesterday_best_team[1]}
    }

# method to get players in action using team info from matches table
# and player info from Player or JALPlayer model based on league
def get_players_in_action(league=""):
    if league == "JAL":
        players = JALPlayer.query.all()
    else:
        players = Player.query.all()

    #print(players)

    # get match ids from matches table
    #print(datetime.now().strftime('%b %d'))
    match_ids = [match.match_info for match in Match.query.filter(Match.date.like(f"{datetime.now().strftime('%b %d')}%")).all()]            
    #print(match_ids)

    players_in_action = []

    for match in match_ids:
        team1 = match.split(" vs ")[0].lower()
        team2 = match.split(" vs ")[1].split(",")[0].lower()
        #print(team1, team2)
        for player in players:
            if player.ipl_team.lower() in [team1, team2]:
                #print(player.name, player.team_name, player.ipl_team)
                players_in_action.append({
                    'name': player.name,
                    'ipl_team': player.ipl_team, 
                    'fpl_team': player.team_name
                })

    players_in_action = pd.DataFrame(players_in_action).sort_values('fpl_team')
    
    #print(players_in_action)
    #exit()

    return players_in_action  


EMOJI_LIST = ["🔥", "💀", "🤯", "🎯", "🤣", "👑", "🚀", "🏆", "💩", "⚡"]

def assign_daily_emoji():
    """Assign a new emoji to all teams, valid until midnight."""
    now = datetime.now()
    midnight = now.replace(hour=23, minute=59, second=59)  

    # insert all team names using the Player model
    teams_fpl = Player.query.with_entities(Player.team_name).distinct().all()
    #teams_jal = JALPlayer.query.with_entities(JALPlayer.team_name).distinct().all()

    # concat both the above teams
    teams = teams_fpl

    # remove duplicates
    teams = list(set(teams))

    # remove None values
    teams = [team for team in teams if team[0] is not None]

    # insert teams into FantasyTeam model 
    # insert teams into FantasyTeam model
    for team in teams:
        # Check if team already exists
        existing_team = FantasyTeam.query.filter_by(team_name=team[0]).first()
        if not existing_team:
            fantasy_team = FantasyTeam(team_name=team[0])
            db.session.add(fantasy_team)

    db.session.commit()    

    teams = FantasyTeam.query.all()
    for team in teams:
        team.emoji = random.choice(EMOJI_LIST)
        team.emoji_expiry = midnight
        team

    db.session.commit()
    

def reset_emojis():
    """Reset all emojis at midnight."""
    FantasyTeam.query.update({FantasyTeam.emoji: None, FantasyTeam.emoji_expiry: None})
    db.session.commit()



# Add this in the refresh_scores() function:
def refresh_scores():

    live_players_list = get_players_in_action()

    # call player of the day and team of the day methods in app.py
    # The variables are unbound because the function names are the same as the variable names
    # To fix this, rename the variables to be different from the function names:

    pod = player_of_the_day()
    totd = team_of_the_day()   

    pod_jal = player_of_the_day("JAL")
    totd_jal = team_of_the_day("JAL") 


    # filter pod.players_with_score_difference_df for name in live_players_list and print
    if not pod['players_with_score_difference_df'].empty:
        live_player_scores_df = pod['players_with_score_difference_df'][pod['players_with_score_difference_df']['name'].isin(live_players_list['name'])]
        live_player_scores_df = live_player_scores_df.sort_values(by='team_name')
        live_player_scores_df = live_player_scores_df[['team_name', 'name',  'score_difference']]
        # rename columns
        live_player_scores_df.columns = ['Team', 'Player', 'Score']
        # make score column integer - without any decimal value
        live_player_scores_df['Score'] = live_player_scores_df['Score'].fillna(0).astype(int)        

        # make team_name "LORDX1" where NaN
        live_player_scores_df['Team'] = live_player_scores_df['Team'].fillna("LORDX1")
        print(live_player_scores_df)

    # Update scores
    update_scores.main(Player, PlayerRanking,PlayerRankingPerDay, pod, totd, "", live_players_list, live_player_scores_df)    

    # update scores for JAL
    update_scores.main(JALPlayer, PlayerRanking, PlayerRankingPerDay, pod_jal, totd_jal, "JAL")  

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
        #jal_app.main()
        refresh_scores()
        #df_series = update_series_stats.main(Player)
        #df_scoreboard = update_scores_from_scoreboard.main(Match)

# Schedule get_cricbattle_data to run every 5 minutes with app context
def scheduled_task_cricbuzz():
    with app.app_context():
        logging.info("Running scheduled_task_cricbuzz")
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
        #jal_app.main()
        #refresh_scores()
        get_players_in_action()
        #exit()
        df_series = update_series_stats.main(Player)
        df_scoreboard = update_scores_from_scoreboard.main(Match)
        #copy_data_from_player_ranking_to_player_ranking_per_day()
        player_of_the_day()
        assign_daily_emoji()

        # Initialize scheduler only if not already started
        if not app.config.get("SCHEDULER_STARTED", False):
            app.scheduler = BackgroundScheduler()
            app.scheduler.add_job(func=scheduled_task, trigger="cron", minute="*/1", hour="9-22")    
            app.scheduler.add_job(func=scheduled_task_cricbuzz, trigger="cron", minute="*/5", hour="9-22")                  
            app.scheduler.add_job(func=copy_data_from_player_ranking_to_player_ranking_per_day, trigger="cron", hour="17,18,19")               
            #app.scheduler.add_job(func=lambda: update_series_stats.main(Player), trigger="cron", minute="45", hour="12-22")                
            #app.scheduler.add_job(func=lambda: update_scores_from_scoreboard.main(Match), trigger="cron", minute="43", hour="12-22")                     
            app.scheduler.start()
            app.config["SCHEDULER_STARTED"] = True

        # Mark initialization as complete
        with open(INIT_FILE, "w") as f:
            f.write("initialized")
        logging.info("App initialization complete")


def get_device_id():
    user_agent = request.headers.get('User-Agent', '')
    logging.info(f"User-Agent: {user_agent}")
    ip = request.remote_addr
    logging.info(f"IP Address: {ip}")
    
    return hashlib.sha256(f"{user_agent}{ip}".encode()).hexdigest()


# method that uses existing device_id as input 
# split device_id with delimitter --
# check if any values exists in payment table with 2nd part 
# if not then update the payment table with 2nd part
def update_device_id(old_device_id):
    try:
        split_device_ids = old_device_id.split("--")
        new_device_id = split_device_ids[1]
        check_device_id = Payment.query.filter_by(deleted=0, device_id=new_device_id).first()
        if check_device_id is None:
            payment = Payment.query.filter_by(device_id=old_device_id, deleted=0).update({Payment.device_id: new_device_id})
            db.session.commit()
    except Exception as e:
        logging.error(f"Error updating device ID: {e}")        
    return True


def is_approved(device_id):
    logging.info(f"Checking if payment is approved for device {device_id}")

    if "--" in device_id:
        update_device_id(device_id)
        device_id = device_id.split("--")[1]
        logging.info(f"Updated device ID: {device_id}")
        payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    else:
        payment = Payment.query.filter(Payment.device_id.like(f"%{device_id}%"), Payment.deleted==0).first()            
        if payment is not None and payment.approved == 1:
            logging.info(f"Payment found approved for device {device_id}")
            log_to_db(f"Payment found approved for device {device_id}")
            return True
    logging.info(f"Payment not approved for device {device_id}")
    log_to_db(f"Payment not approved for device {device_id}")
    return False


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/pay', methods=['GET', 'POST'])
def pay():
    device_id = get_device_id()
    print(device_id)

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

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

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('confirm_payment')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    
    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

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
    if "--" in device_id:
        device_id = device_id.split("--")[1]
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    if payment is None:
        payment = Payment.query.filter(Payment.device_id.like(f"%{device_id}%"), Payment.deleted==0).first()  
    return payment is not None and payment.approved == 0

def is_rejected(device_id):
    if "--" in device_id:
        device_id = device_id.split("--")[1]
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    if payment is None:
        payment = Payment.query.filter(Payment.device_id.like(f"%{device_id}%"), Payment.deleted==0).first()  
    return payment is not None and payment.approved == 2

# method to check if trial expired for device
def is_trial_expired(device_id):
    payment = Payment.query.filter_by(device_id=device_id).first()
    approved_payment = Payment.query.filter_by(device_id=device_id, approved=1).first()
    if payment:
        print(device_id, payment.trial_expiry, payment.deleted, payment.approved)
    if payment is None:
        return False
    if payment.trial_expiry is None:
        return False
    if datetime.utcnow() > payment.trial_expiry:
        logging.info(f"Trial expired for device {device_id} and marking the payment object rejected")
        payment.approved = 2
        db.session.commit()
        return True
    if payment.approved == 2 and approved_payment is None:
        logging.info(f"Trial expired for device {device_id}")
        return True
    return False



@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == 'admin' and password == 'admin13$':
            session['admin'] = True
            flash('Successfully logged in as admin', 'success')
            return redirect(url_for('admin_review'))
        else:
            flash('Invalid credentials', 'danger')
            
    return render_template('admin_login.html')

@app.route('/admin/review', methods=['GET', 'POST'])
def admin_review():
    if session.get('admin') != True:
        return redirect(url_for('admin_login'))

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
            elif action == 'delete':
                # delete the payment record completely and not just mark it deleted
                db.session.delete(payment)
                flash(f"Payment for device {device_id} deleted", "danger")

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


@app.route('/admin/logs')
def logs():
    if session.get('admin') != True:
        return redirect(url_for('admin_login'))
    
    # delete logs from timestamp older than 1 week
    one_week_ago = datetime.now() - timedelta(days=2)
    Log.query.filter(Log.timestamp < one_week_ago).delete()
    db.session.commit()

    # Run VACUUM in a separate connection outside transaction
    engine = db.engine
    connection = engine.raw_connection()
    try:
        connection.execute('VACUUM')
    finally:
        connection.close()
    
    logging.info("Deleted logs older than 1 week")


    logs = Log.query.order_by(Log.timestamp.desc()).all()    
    return render_template('logs.html', logs=logs)


@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/home')
def display_leaderboard():
    device_id = get_device_id()
    print(device_id)

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

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

@app.route('/admin/delete/<device_id>', methods=['POST']) 
def delete_device(device_id):
    if session.get('admin') != True:
        return {'error': 'Unauthorized'}, 401
        
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    if payment:
        db.session.delete(payment)
        flash(f"Payment for device {device_id} deleted", "danger")
        db.session.commit()
    
    return {'message': f'Payment for device {device_id} deleted'}, 200
         
@app.route('/reset-payment', methods=['POST'])
def reset_payment():
    device_id = get_device_id()
    print(device_id)

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

    if not is_rejected(device_id):
        flash("Your payment is not rejected. Please check back later.", "info")
        return redirect(url_for('pay'))
    
    logging.info(f"Resetting payment for device {device_id}")
        
    payment = Payment.query.filter_by(deleted=0, device_id=device_id).first()
    if payment:
        payment.deleted = 1
        db.session.commit()

    return redirect(url_for('display_leaderboard'))

@app.route('/insights')
def show_insights():
    device_id = get_device_id()

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

    if not is_approved(device_id):
        return redirect(url_for('pay'))

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
    print(device_id)
    logging.info(f"Activating free trial for device {device_id} not allowed")
    return redirect(url_for('display_leaderboard'))
    # Check if device already has active paid subscription
    if is_approved(device_id):
        flash("You already have an active subscription", "info")
        return redirect(url_for('display_leaderboard'))
    
    """ if is_trial_expired(device_id):
        flash("Your trial period has expired. Please pay to continue.", "info")
        return render_template('trial_expired.html', table=None) """
        
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

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

    if not is_approved(device_id):
        return redirect(url_for('pay'))
    
    

    #refresh_scores()

    latest_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return render_template('FPL-IPL2025-Points.html', timestamp=latest_timestamp)

@app.route('/jal/live-scoring')
def show_jal_live_scoring():
    # check if user is paid and approved
    device_id = get_device_id()

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

    if not is_approved(device_id):
        return redirect(url_for('pay'))
    

    latest_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return render_template('JAL-IPL2025-Points.html', timestamp=latest_timestamp)



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
        if match["date"]:
            last_match_date = match["date"]
            logging.info(f"Last match date: {last_match_date}")
        #session.add(Match(date=match["date"], match_info=match["match_info"], time=match["time"]))
        new_match = Match(matchId=match["matchId"], date=match["date"], match_info=match["match_info"], time=match["time"])
        if not match["date"] and match["match_info"] in "Chennai Super Kings vs Mumbai Indians, 3rd Match":
            match["date"] = "Mar 23, Sun"
            new_match = Match(matchId=match["matchId"], date=match["date"], match_info=match["match_info"], time=match["time"])
        elif not match["date"]:
            match["date"] = last_match_date
            new_match = Match(matchId=match["matchId"], date=match["date"], match_info=match["match_info"], time=match["time"])
            logging.info(f"Last match date set up to : {last_match_date} for match : {match["match_info"]}")
        elif match["match_info"] in "Kolkata Knight Riders vs Lucknow Super Giants, 19th Match":
            match["date"] = "Apr 08, Tue"
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
        return redirect(url_for('admin_login'))

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
            'name_array': ','.join(request.form.getlist('names[]')),            
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
        return redirect(url_for('admin_login'))

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

            # do the same for JALPlayer too
            jal_player = JALPlayer.query.filter_by(name=player.name).first()
            if jal_player:
                jal_player.points_reduction = data.get('points_reduction', jal_player.points_reduction)
                jal_player.first_match_id = data.get('first_match_id', jal_player.first_match_id)
                jal_player.name_array = data.get('name_array', jal_player.name_array)
                db.session.merge(jal_player)
               
            db.session.commit()
            return {'message': 'Player updated successfully'}, 200
    return render_template('edit_player.html', player=player)


@app.route('/admin/jal/players', methods=['GET', 'POST'])
def admin_jal_players():
    if session.get('admin') != True:
        return redirect(url_for('admin_login'))

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
            'name_array': ','.join(request.form.getlist('names[]')),
            'traded': bool(request.form.get('traded'))
        }

        if player_id:
            # Edit existing player
            JALPlayer.query.filter_by(id=player_id).update(player_data)
            flash('JAL Player updated successfully', 'success')
        else:
            # Add new player
            new_player = JALPlayer(**player_data)
            db.session.add(new_player)
            flash('JAL Player added successfully', 'success')

        db.session.commit()
        return redirect(url_for('admin_jal_players'))

    # GET request - show all players
    players = JALPlayer.query.all()
    return render_template('admin_jal_players.html', players=players)

@app.route('/admin/jal/players/delete/<int:id>', methods=['POST'])
def delete_jal_player(id):
    if session.get('admin') != True:
        return {'error': 'Unauthorized'}, 401

    player = JALPlayer.query.get_or_404(id)
    db.session.delete(player)
    db.session.commit()
    flash('JAL Player deleted successfully', 'success')
    return redirect(url_for('admin_jal_players'))

@app.route('/admin/jal/players/edit/<int:id>', methods=['GET', 'POST'])
def edit_jal_player(id):
    if session.get('admin') != True:
        return redirect(url_for('admin_login'))

    player = JALPlayer.query.get_or_404(id)    
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

            # do the same for Player too
            fpl_player = Player.query.filter_by(name=player.name).first()
            if fpl_player:
                fpl_player.points_reduction = data.get('points_reduction', fpl_player.points_reduction)
                fpl_player.first_match_id = data.get('first_match_id', fpl_player.first_match_id)
                fpl_player.name_array = data.get('name_array', fpl_player.name_array)
                db.session.merge(fpl_player)

            db.session.commit()
            return {'message': 'JAL Player updated successfully'}, 200
    return render_template('edit_jal_player.html', player=player)


@app.route('/emoji-reactions/<key>', methods=['POST'])
def add_emoji_reaction(key):
    if not key:
        return {'error': 'key is required'}, 400
    
    # Save to localStorage
    # const key = `reaction_${{teamName}}_${{emoji}}`;
    # localStorage.setItem(key, count);

    value = request.json.get('value')
        
    # Get existing reactions for team
    team_reactions = EmojiReaction.query.filter_by(key=key).first()
    
    if team_reactions:
        # Update existing reaction count
        current_reactions = team_reactions.value
        if int(current_reactions) < 100:
            team_reactions.value = int(current_reactions) + 1    
    else:
        # Create new reaction entry
        team_reactions = EmojiReaction(
            key=key,
            value=value
        )
        
    db.session.merge(team_reactions)
    db.session.commit()
    
    return {'message': 'Reaction added successfully'}, 200

@app.route('/emoji-reactions/<key>', methods=['GET']) 
def get_emoji_reactions(key):
    team_reactions = EmojiReaction.query.filter_by(key=key).first()
    
    if not team_reactions:
        return {'reactions': 0}
        
    reactions = team_reactions.value
    return {'reactions': reactions}


@app.route('/page-views/<page>', methods=['POST'])
def increment_page_views(page):
    if not page or ("live-scoring" not in page and "points-table" not in page):
        return {'error': 'page is required'}, 400

    device_id = request.cookies.get('device_id')  # Check if cookie exists

     # Get existing page views
    page_views = PageView.query.filter_by(page=page, device_id=device_id).first()
    
    if page_views:
        # Increment existing view count
        views =  page_views.views + 1
        page_views.views = views
    else:
        # Create new page view entry
        views = 100
        page_views = PageView(
            page=page,
            device_id=device_id,
            views=views
        )
        
    db.session.merge(page_views)
    db.session.commit()

    page_views = db.session.query(db.func.sum(PageView.views)).filter_by(page=page).scalar()  or 100
    count_of_devices = db.session.query(PageView.device_id).filter_by(page=page).distinct().count()

    actual_views =  page_views - count_of_devices * 100
    
    return {'views': actual_views}, 200

@app.route('/page-views/<page>', methods=['GET']) 
def get_page_views(page):
    if not page or ("live-scoring" not in page and "points-table" not in page):
        return {'error': 'page is required'}, 400
    
    page_views = db.session.query(db.func.sum(PageView.views)).filter_by(page=page).scalar()  or 100
    count_of_devices = db.session.query(PageView.device_id).filter_by(page=page).distinct().count()

    actual_views =  page_views - count_of_devices * 100

    if not page_views:
        return {'views': 0}
        
    return {'views': actual_views}



@app.route("/points-table")
def points_table():

    device_id = get_device_id()

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")

    if not is_approved(device_id):
        return redirect(url_for('pay'))
    

    teams_df, player_team_points_df = update_scores.create_points_table(Player, PlayerRanking)
    teams_df.rename(columns={
            'Team Name': 'TeamName',
        }, inplace=True)
    teams_df.reset_index(inplace=True)
    
    #print(teams_df)

    #print(player_team_points_df)
    # extract first row from player_team_points_df
    #mvp = player_team_points_df.iloc[0]['Player Name']
    #print(mvp)
    player_awards = {}
    player_awards["MVP"] = {
            'name': "MVP",
            'player': player_team_points_df.iloc[0]['Player Name'],
            'team': player_team_points_df.iloc[0]['Team Name'],
            'points': player_team_points_df.iloc[0]['PlayerPoints']
        }

    series_df = update_scores.get_series_stats(Player, PlayerRanking)

    #print(series_df)
    
    for key, df in series_df.items():
        if key == "MOST_RUNS":
            key = "Best Batter"
            key_col = "Runs"
        elif key == "MOST_WICKETS":
            key = "Best Bowler"
            key_col = "Wkts"
        elif key == "MOST_SIXES":
            key = "Most Sixes"
            key_col = "6s"
            df.rename(columns={
                'Batter': 'Player',
            }, inplace=True)
        else:
            logging.error(f"Unknown key {key}")

        #print(df)

        if df.empty:
            logging.error(f"Empty DataFrame for {key}")
            continue

        df['Team Name'] = df['Team Name'].fillna(value="LORDX1")
        del df['Player Name']
        cols = df.columns.tolist()
        #print(cols)
        cols = cols[1:2] + cols[:1] + cols[2:]        
        #print(cols)
        df = df[cols]
        #print(df)
        #extract first row of each df and save to player_awards
        player_awards[key] = {
            'name': key,
            'player': df.iloc[0]['Player'],
            'team': df.iloc[0]['Team Name'],
            'points': df.iloc[0][key_col]
        }
        

    #print(player_awards)

    scoreboard_df = update_scores.get_scoreboard_stats(Player, PlayerRanking)
    #print(scoreboard_df)

    team_awards = {}
    for key, df in scoreboard_df.items():
        if key == "Bat":
            key = "Most 50s"
        elif key == "Bowl":
            key = "Most 3fers"
        elif key == "Field":
            key = "Best Fielder"
        elif key == "POTM":
            key = "Most POTMs"
        else:
            logging.error(f"Unknown key {key}")

        #print(df)

        if df.empty:
            logging.error(f"Empty DataFrame for {key}")
            continue

        #del df['Player Name']
        cols = df.columns.tolist()
        #print(cols)
        cols = cols[1:2] + cols[:1] + cols[2:]
        #print(cols)
        df = df[cols]
        #print(df)
        #extract first row of each df and save to player_awards
       
        if key == "Best Fielder":
            player_awards[key] = {
            'name': key,
            'player': df.iloc[0]['Player'],
            'team': df.iloc[0]['Team Name'],
            'points': df.iloc[0]['Player Count']
        } 
        else :
             team_awards[key] = {
            'name': key,
            #'player': df.iloc[0]['Player'],
            'team': df.iloc[0]['Team Name'],
            'points': df.iloc[0]['Player Count']
        }

    #print(team_awards)
    
    return render_template("points_table.html", teams=teams_df, player_awards=player_awards, team_awards=team_awards)

# Hash password
from werkzeug.security import generate_password_hash, check_password_hash   


# Add signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('signup'))
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return redirect(url_for('signup'))
            
        # Hash password
        hashed_password = generate_password_hash(password)
        
        # Create new user
        user = User(username=username, password=hashed_password, email=email)
        db.session.add(user)
        db.session.commit()
        
        flash('Successfully registered! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        user = User.query.filter_by(username=username).first()

        user_email = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['admin'] = user.is_admin
            session.permanent = True
            app.permanent_session_lifetime = timedelta(hours=1)
            flash('Successfully logged in!', 'success')
            return redirect(url_for('predictor'))        
        elif user_email and check_password_hash(user_email.password, password):
            session['user_id'] = user_email.id
            session['admin'] = user_email.is_admin
            session.permanent = True
            app.permanent_session_lifetime = timedelta(hours=1)
            flash('Successfully logged in!', 'success')
            return redirect(url_for('predictor'))      
        else:
            flash('Invalid credentials', 'danger')
            
    return render_template('login.html')

# Add logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out', 'info')
    return redirect(url_for('login'))


# add /me route
@app.route('/me')
def me():
    print(session)
    if 'user_id' not in session:
        logging.info("User not logged in") 
        flash('Please login first', 'warning')
        return redirect(url_for('login'))
    user = db.session.get(User, session['user_id'])    
    logging.info(f"User: {user.username}")
    if user:
        return {'username' : user.username}, 200
    return redirect(url_for('login'))


# add reset password route
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form.get('username')
        new_password = request.form.get('new_password')

        user = User.query.filter_by(username=username).first()

        if user:
            # Hash new password
            hashed_password = generate_password_hash(new_password)

            # Update user's password
            user.password = hashed_password
            db.session.commit()

            flash('Password reset successfully!', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid username', 'danger')

    return render_template('reset_password.html')


# Add login_required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Add admin_required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            flash('Admin access required', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function



@app.route("/predictor")
@login_required 
def predictor():

    device_id = get_device_id()

    new_device_id = request.cookies.get('device_id')  # Check if cookie exists

    logging.info(f"Received device_id from cookies: {new_device_id}")

    if not new_device_id:
        new_device_id = str(uuid.uuid4())  # Generate new device ID
        response = make_response(redirect(url_for('show_live_scoring')))
        response.set_cookie(
            'device_id', new_device_id, 
            max_age=60*60*24*365*5,  # 5 years
            samesite='Lax',
            secure=False,  # Set True for HTTPS
            httponly=True
        )
        logging.info(f"Setting new device_id: {new_device_id}")
        return response  # Send response with new cookie
    

    #device_id = device_id + "--" + new_device_id
    device_id = new_device_id
    logging.info(f"Setting new super device_id: {device_id}")


    # get matches from /matches endpoint
    matches = db.session.query(Match.matchId, Match.date, Match.match_info, Match.time).all()  
    upcoming_matches = {}
    index = 0
  

    # extract team1 and team2 from match_info and add to each match
    for match in matches:        
        match_info = match[2] # Access match_info from tuple using index
        match_split = match_info.split(',')[0].split(' vs ')
        team1 = match_split[0]
        team2 = match_split[1]

        match_date = match[1].split(",")[0]
        today = pd.Timestamp('today').strftime('%b %d')  

        # Convert dates to datetime for comparison
        match_datetime = pd.to_datetime(match[1].split(",")[0], format='%b %d')
        today_datetime = pd.to_datetime(today, format='%b %d')

        if match_datetime < today_datetime:
            continue

        
        # Convert tuple to dict to add new fields
        match = {
            'matchId': match[0],
            'date': match[1], 
            'match_info': match[2],
            'time': match[3],
            'team1': team1,
            'team2': team2
        }
      
        
        upcoming_matches[index] = match  
        index += 1

    for match in upcoming_matches:
        logging.info(f"Match: {upcoming_matches[match]['team1']}")

    
    past_predictions = get_user_predictions()
    logging.info(f"Past predictions: {past_predictions}")
    all_predictions = get_predictions(upcoming_matches)
    logging.info(f"All predictions: {all_predictions}")
    leaderboard = get_prediction_leaderboard()
    logging.info(f"Leaderboard: {leaderboard}")
    match_results = get_match_results()
    logging.info(f"Match results: {match_results}")

    return render_template("predictor.html", upcoming_matches=upcoming_matches, past_predictions=past_predictions, all_predictions=all_predictions, leaderboard=leaderboard, match_results=match_results)        


# method to extract all match_results from actual_results table
def get_match_results():
    match_results = db.session.query(ActualResult).all()

    # get match_info for matchId and add that to match_results
    for match in match_results:
        match_info = db.session.query(Match).filter(Match.matchId==match.matchId).first()

        match.team1 = match_info.match_info.split(', ')[0].split(' vs ')[0]
        match.team2 = match_info.match_info.split(', ')[0].split(' vs ')[1]
        match.match_info = match_info.match_info


    return match_results


# method to extract all predictions from given matches
# filter matches for todays date only
def get_predictions(matches):

    all_predictions = []
    today = pd.Timestamp('today').strftime('%b %d')
    
    for match in matches:
        matchId = matches[match]['matchId']
        match_date = matches[match]['date'].split(", ")[0]
        
        # Convert dates to datetime for comparison
        match_datetime = pd.to_datetime(match_date, format='%b %d')
        today_datetime = pd.to_datetime(today, format='%b %d')
        
        # Skip if not today's match
        if match_datetime != today_datetime:
            continue
            
        # Get predictions for this match
        match_predictions = db.session.query(Prediction).filter(Prediction.matchId==matchId).all()
        
        # Filter out predictions with null usernames
        match_predictions = [p for p in match_predictions if p.username]
        
        # Get match info and add team names
        for prediction in match_predictions:
            match_info = db.session.query(Match).filter(Match.matchId==prediction.matchId).first()
            if match_info:
                prediction.team1 = match_info.match_info.split(', ')[0].split(' vs ')[0]
                prediction.team2 = match_info.match_info.split(', ')[0].split(' vs ')[1]
                prediction.match_info = match_info.match_info
                
        all_predictions.extend(match_predictions)
            
    return all_predictions


# method to extract all past predictions for a user
def get_user_predictions():
    try:
        if 'user_id' not in session:
            return []
            
        user = db.session.get(User, session['user_id'])
        if user:
            username = user.username
            logging.info(f"Username: {username}")
            predictions = db.session.query(Prediction).filter_by(username=username).all()

            # Include all predictions
            filtered_predictions = []
            today = pd.Timestamp('today').strftime('%b %d')

            for match in predictions:
                match_info = db.session.query(Match).filter(Match.matchId==match.matchId).first()
                if not match_info:
                    continue

                match.team1 = match_info.match_info.split(', ')[0].split(' vs ')[0] 
                match.team2 = match_info.match_info.split(', ')[0].split(' vs ')[1]
                match.match_info = match_info.match_info

                # check if result available for the match
                result = db.session.query(ActualResult).filter_by(matchId=match.matchId).first()
                if result:
                    match.result = result.event_result
                    match.event_type = result.event_type

                    # calculate points won/lost for the match
                    # +50 for correct toss, -50 for wrong toss
                    # +100 for correct match, -100 for wrong match
                    if match.prediction_type == 'toss':
                        if match.prediction_value == result.event_result:
                            match.points = 50
                        else:
                            match.points = -50
                    if match.prediction_type == 'match':
                        if match.prediction_value == result.event_result:
                            match.points = 100
                        else:
                            match.points = -100
                else:
                    match.result = None
                    match.event_type = None
                    match.points = 0


                filtered_predictions.append(match)

            return filtered_predictions        
    except Exception as e:
        logging.error(f"Error getting predictions: {e}")
        return []
              
    return []    


# method to create leaderboard based on prediction results 
def get_prediction_leaderboard():
    # get all predictions
    predictions = db.session.query(Prediction).all()
    # create a dataframe
    df = pd.DataFrame([{
        'matchId': p.matchId,
        'username': p.username,
        'prediction_type': p.prediction_type,
        'prediction_value': p.prediction_value
        } for p in predictions if p.username])

    # get actual results
    results = db.session.query(ActualResult).all()
    results_df = pd.DataFrame([{
        'matchId': r.matchId,
        'event_type': r.event_type, 
        'event_value': r.event_result
    } for r in results])

    if results_df.empty:
        return []

    # merge predictions with results
    merged_df = pd.merge(df, results_df,
                        left_on=['matchId', 'prediction_type'],
                        right_on=['matchId', 'event_type'])

    # calculate points
    merged_df['points'] = 0
    # +50 for correct toss, -50 for wrong toss
    merged_df.loc[(merged_df['prediction_type'] == 'toss') & 
                 (merged_df['prediction_value'] == merged_df['event_value']), 'points'] = 50
    merged_df.loc[(merged_df['prediction_type'] == 'toss') & 
                 (merged_df['prediction_value'] != merged_df['event_value']), 'points'] = -50
    # +100 for correct match, -100 for wrong match
    merged_df.loc[(merged_df['prediction_type'] == 'match') & 
                 (merged_df['prediction_value'] == merged_df['event_value']), 'points'] = 100
    merged_df.loc[(merged_df['prediction_type'] == 'match') & 
                 (merged_df['prediction_value'] != merged_df['event_value']), 'points'] = -100

    # create leaderboard
    leaderboard = merged_df.groupby('username').agg({
        'points': 'sum',
        'prediction_type': 'count'
    }).reset_index()

    leaderboard.rename(columns={'prediction_type': 'total_predictions'}, inplace=True)
    leaderboard['points'] = leaderboard['points'].astype(int)
    leaderboard = leaderboard.sort_values('points', ascending=False)

    # add rank
    leaderboard['rank'] = leaderboard['points'].rank(method='min', ascending=False).astype(int)

    # convert to list of dicts
    leaderboard = leaderboard.to_dict('records')

    # add rank to each dict
    for i, user in enumerate(leaderboard):
        user['rank'] = i + 1

    return leaderboard


@app.route('/admin/predictions', methods=['GET', 'POST'])
@admin_required
def manage_predictions():
    if request.method == 'POST':
        logging.info("Received POST request")
        # Handle adding/updating actual results
        matchId = request.form.get('matchId')

        match_winner = request.form.get('match_winner')
        toss_winner = request.form.get('toss_winner')

        if match_winner:
            # save to database
            result = ActualResult(
                matchId=matchId,
                event_type="match",
                event_result=match_winner
            )
            db.session.merge(result)
            

        if toss_winner:
            # save to database
            result = ActualResult(
                matchId=matchId,
                event_type="toss",
                event_result=toss_winner
            )
            db.session.merge(result)
            

        flash('Match & Toss Result updated successfully', 'success')
        db.session.commit()
        
        return redirect(url_for('manage_predictions'))

    # Get all matches
    matches = db.session.query(Match.matchId, Match.date, Match.match_info, Match.time).all()
    
    # Get all results
    results = db.session.query(ActualResult).all()
    
    return render_template('manage_predictions.html', matches=matches, results=results)



# route to /submit-prediction endpoint
@app.route("/submit-prediction", methods=["POST"])
@login_required 
def submit_prediction():
    # get form data
    matchId = request.form.get("matchId")
    prediction_value = request.form.get("prediction_value")
    username = request.form.get("username")
    match_winner = request.form.get("match_winner")
    toss_winner = request.form.get("toss_winner")
    logging.info(f"Match: {matchId}, {prediction_value} {username}")


    # check if user has already submitted a prediction for this match
    existing_prediction = Prediction.query.filter_by(matchId=matchId, username=username).first()
    # if existing prediction then return error
    if existing_prediction:
        return {'message': 'Prediction already exists'}, 200
    
    # check if cut off passed for prediction
    # cut off is 11 am CET everyday for today's match
    # allow anytime for future dated matches
    match_date = db.session.query(Match.date).filter(Match.matchId==matchId).first()[0]
    match_date = match_date.split(", ")[0]

    # Convert dates to datetime for comparison
    match_datetime = pd.to_datetime(match_date, format='%b %d')
    today_datetime = pd.to_datetime(pd.Timestamp('today').strftime('%b %d'), format='%b %d')

    # Only check cutoff time for today's matches
    if match_datetime == today_datetime and pd.Timestamp('today').strftime('%H:%M') > '11:00':
        return {'message': 'Prediction cutoff was 11 am. Try again tomorrow.'}, 200

    """  
    if existing_prediction:
        # update existing prediction
        existing_prediction.prediction_value = prediction_value
        db.session.commit()
        return {'message': 'Prediction updated successfully'}, 200 """

    if match_winner:
        # save to database
        prediction = Prediction(
            matchId=matchId,
            username=username,
            prediction_type="match",
            prediction_value=match_winner
        )
        db.session.add(prediction)

    if toss_winner:
        # save to database
        prediction = Prediction(
            matchId=matchId,
            username=username,
            prediction_type="toss",
            prediction_value=toss_winner
        )
        db.session.add(prediction)

    
    db.session.commit()


    # return success message
    #flash('Prediction submitted successfully', 'success')
    return {'message': 'Prediction submitted successfully'}, 200







@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=debug)
