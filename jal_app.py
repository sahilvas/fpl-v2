import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
import os
import sqlite3
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# Define SQLite Table Model
class JALPlayer(Base):
    __tablename__ = 'jal_players'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    role = Column(String)  # Needs to be manually assigned
    category = Column(String)  # Needs to be manually assigned
    ipl_team = Column(String)  # Can be extracted if available
    base_price = Column(Float)
    selling_price = Column(Float)
    team_name = Column(String)
    is_sold = Column(Boolean)
    points_reduction = Column(Integer)
    first_match_id = Column(Integer)
    foreign_player = Column(Boolean)
    timestamp = Column(DateTime, default=datetime.utcnow)
    name_array = Column(String)
    traded = Column(Boolean)

def main():
    # Check if running on Azure (persistent storage available at `/mnt/sqlite`)
    if os.environ.get("WEBSITE_SITE_NAME"):  # This env var exists only in Azure App Service
        DB_PATH = "/mnt/sqlite/cricbattle.db"
        debug = False
    else:
        # Local development (stores DB in the instance folder)
        DB_PATH = "instance/cricbattle.db"
        debug = True

    DATABASE_URL = f"sqlite:///{DB_PATH}"

    # Create SQLite Database
    engine = create_engine(DATABASE_URL, echo=True)
    Base.metadata.create_all(engine)

    # Load the Excel File
    file_path = 'jal_players.xlsx'  # Change this to your actual file path
    df1 = pd.read_excel(file_path, skiprows=1)  # Skip merged header row
    df = pd.read_excel(file_path, skiprows=2)  # Skip first two rows

    # Extract Team Names from Header
    teams = []
    for i in range(0, len(df1.columns), 2):  # Every team has 2 columns: Player Name and Price
        teams.append(df1.columns[i])  # Team names are in even index columns

    # Convert DataFrame into Structured Data
    players_data = []

    for _, row in df.iterrows():
        for i, team_name in enumerate(teams):
            player_col = i * 2  # Player Name column index
            price_col = player_col + 1  # Price column index
            
            player_name = row.iloc[player_col]
            price = row.iloc[price_col] if pd.notna(row.iloc[price_col]) else None
            
            if pd.isna(player_name):
                continue  # Skip empty rows

            # skip rows with "Total" in player name
            if "Total" in player_name:
                continue
            
            player_entry = {
                "name": player_name.replace(" (T)", "").strip(),
                "role": None,  # Assign manually if required
                "category": None,  # Assign manually if required
                "ipl_team": None,  # Assign if available
                "base_price": None,  # Not provided in table
                "selling_price": price,
                "team_name": team_name,
                "is_sold": price is not None,
                "points_reduction": 0,  # Placeholder value
                "first_match_id": None,  # Placeholder
                "foreign_player": None,  # Assign manually if needed
                "name_array": None,  # Placeholder
                "traded": "(T)" in player_name,
                "timestamp": datetime.utcnow(),
            }
            
            players_data.append(player_entry)

    # Insert Data into Database
    Session = sessionmaker(bind=engine)
    session = Session()

    #cleanup player table first if it has data
    session.query(JALPlayer).delete()

    for player in players_data:
        session.add(JALPlayer(**player))

    session.commit()
    session.close()

    print("Data successfully inserted into SQLite database.")

    # Connect to cricbattle.db and players.db
    conn_cricbattle = sqlite3.connect('/mnt/sqlite/cricbattle.db' if os.environ.get("WEBSITE_SITE_NAME") else 'instance/cricbattle.db')    
    #conn_players = sqlite3.connect('players.db')

    # Get player info from cricbattle.db
    cricbattle_cursor = conn_cricbattle.cursor()
    #players_cursor = conn_players.cursor()

    # Get role and ipl_team for all players from cricbattle.db
    cricbattle_cursor.execute("SELECT name, role, ipl_team, foreign_player, name_array FROM player_v3")
    player_info = cricbattle_cursor.fetchall()

    # Update players.db with role and ipl_team info
    for name, role, ipl_team, foreign_player, name_array in player_info:
        cricbattle_cursor.execute("""
            UPDATE jal_players 
            SET role = ?, ipl_team = ?, foreign_player = ?, name_array = ?
            WHERE name = ?
        """, (role, ipl_team, foreign_player, name_array, name ))

    # update role, ipl_team manually for some players
    cricbattle_cursor.execute("""
        UPDATE jal_players
        SET role = 'Batsman', ipl_team = 'Mumbai Indians'
        WHERE name = 'Tilak Varma'
    """)
    cricbattle_cursor.execute("""
        UPDATE jal_players
        SET role = 'Batsman', ipl_team = 'Rajasthan Royals'
        WHERE name = 'Vaibhav Suryavanshi'
    """)
    cricbattle_cursor.execute("""
        UPDATE jal_players
        SET role = 'Batsman', ipl_team = 'Punjab Kings'
        WHERE name = 'Musheer khan'
    """)
    cricbattle_cursor.execute("""
        UPDATE jal_players
        SET role = 'Batsman', ipl_team = 'Delhi Capitals', foreign_player = 1
        WHERE name = 'Harry Brook'
    """)

    cricbattle_cursor.execute("""
        UPDATE jal_players
        SET foreign_player = 0
        WHERE foreign_player is null
    """)

    # Commit changes and close connections
    conn_cricbattle.commit()
    cricbattle_cursor.close()
    conn_cricbattle.close() 

   

if __name__ == "__main__":
    main()






