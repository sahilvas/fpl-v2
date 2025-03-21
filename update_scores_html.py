import traceback
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from openpyxl import load_workbook
import logging
from datetime import datetime
from openpyxl.styles import PatternFill, Font  
from openpyxl.utils import get_column_letter  
import shutil  
import os  
import update_series_stats
import sqlite3


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

 

def adjust_column_widths(sheet):  
    logging.info("Adjusting column widths")  
    for column in sheet.columns:  
        max_length = 0  
        column = [cell for cell in column]  
        for cell in column:  
            try:  
                if len(str(cell.value)) > max_length:  
                    max_length = len(str(cell.value))  
            except:  
                pass  
        adjusted_width = (max_length + 2)  
        sheet.column_dimensions[get_column_letter(column[0].column)].width = adjusted_width  

  


def read_excel_file(filename):
    try:
        return pd.read_excel(filename)
    except FileNotFoundError:
        print(f"Error: The file '{filename}' was not found.")
    except Exception as e:
        print(f"An error occurred while reading '{filename}': {e}")
    return None

def calculate_best_11(df):  
    logging.info("Calculating best 11 players for each team")  
    best_11 = []  
      
    for team, group in df.groupby('Team Name'):  
        players = group.copy()  
        players.sort_values(by='TotalScore', ascending=False, inplace=True)  
        logging.info(f"Calculating best 11 players for team {team}") 
          
        # Initialize constraints  
        wk_needed = 1  # At least 1 WK required
        bat_needed = 4  # At least 4 batters, including WK  
        all_needed = 1  
        bowl_needed = 3  
        max_overseas = 4
        max_ipl_team = 3  # Max 4 players per IPL team
          
        # Create best 11 list  
        selected = []  
        selected_ids = set()  # To track selected player IDs or names  
        overseas_counter = 0  # Counter for overseas players
        ipl_team_counts = {}  # Track number of players from each IPL team
  
        # Role-specific selections with adjusted logic  
        wk_count = 0  # Track selected WK count  
        bat_count = 0  # Track selected batters (including WKs)  
        
        for _, player in players.iterrows():  
            logging.info(f"Processing player {player['Player Name']}")
            if len(selected) >= 11:  
                break  
            
            player_role = player['Role']  
            player_is_overseas = player['foreign_player']  
            player_ipl_team = player['IPL Team']
            player_id = player['PlayerId']  
            
            if player_id in selected_ids or overseas_counter >= max_overseas or ipl_team_counts.get(player_ipl_team, 0) >= max_ipl_team:
                continue
            
            if player_role == 'Wicket Keeper Batter':  
                if wk_count < 1:  # Allow multiple WKs up to 4  
                    selected.append(player)  
                    selected_ids.add(player_id)  
                    wk_count += 1  
                    bat_count += 1  # WK is also counted as a batter  
                    ipl_team_counts[player_ipl_team] = ipl_team_counts.get(player_ipl_team, 0) + 1  
                    if player_is_overseas:
                        overseas_counter = overseas_counter + 1
            
            elif player_role == 'Allrounder' and all_needed > 0:  
                selected.append(player)  
                selected_ids.add(player_id)  
                all_needed -= 1   
                ipl_team_counts[player_ipl_team] = ipl_team_counts.get(player_ipl_team, 0) + 1  
                if player_is_overseas:
                        overseas_counter = overseas_counter + 1
                
            elif player_role == 'Bowler' and bowl_needed > 0:  
                selected.append(player)  
                selected_ids.add(player_id)  
                bowl_needed -= 1  
                ipl_team_counts[player_ipl_team] = ipl_team_counts.get(player_ipl_team, 0) + 1  
                if player_is_overseas:
                        overseas_counter = overseas_counter + 1
  
        logging.info(f"IPL Team count so far {ipl_team_counts} for team {player_ipl_team}") 
        logging.info(f"Overseas count so far {overseas_counter} for team {player_ipl_team}")
  
        # Ensure at least 1 WK is selected  
        for _, player in players.iterrows():  
            if len(selected) >= 11:  
                break 
            if player['Role'] in ['Batter', 'Wicket Keeper Batter'] and player['PlayerId'] not in selected_ids and len(selected) < 11:  
                selected.append(player)  
                selected_ids.add(player['PlayerId'])  
                wk_count += 1  
                bat_count += 1  
                ipl_team_counts[player_ipl_team] = ipl_team_counts.get(player_ipl_team, 0) + 1  
                if player_is_overseas:
                        overseas_counter = overseas_counter + 1
                logging.info(f"Adding player {player['Player Name']} for team {team}")
                if bat_count >= bat_needed:  
                    break  
  

  
        # Ensure we have exactly 11 players by filling any gaps with highest scorers  
        if len(selected) < 11:  
            for _, player in players.iterrows():  
                if len(selected) >= 11:  
                    break 
                player_id = player['PlayerId']  
                logging.info(f"Re-Processing player {player['Player Name']}")
                if player_id in selected_ids or  overseas_counter >= max_overseas or ipl_team_counts.get(player_ipl_team, 0) >= max_ipl_team:
                    logging.info(f"Skipping player {player['Player Name']} due to foreign player or IPL team logic")
                    continue  
                logging.info(f"Adding player {player['Player Name']} to best 11") 
                selected.append(player)  
                selected_ids.add(player_id)  
                ipl_team_counts[player_ipl_team] = ipl_team_counts.get(player_ipl_team, 0) + 1  
                if player_is_overseas:
                        overseas_counter = overseas_counter + 1
  
        logging.info(f"Finished best 11 players for team {team} - {len(selected)}")  
  
        # Sum the total score of best 11  
        best_11_points = sum(player['TotalScore'] for player in selected)  
        best_11.append((team, best_11_points, selected))  

    
    #exit()  
    return best_11


def create_team_points_chart(team_points_df):
    fig = px.bar(
        team_points_df,
        x='Team Name',
        y=['TotalPoints', 'Best11Points'],
        title='Team Performance Comparison',
        barmode='group',
        labels={'value': 'Points', 'variable': 'Category'},
        color_discrete_sequence=['#1f77b4', '#ff7f0e']
    )
    return fig.to_html(full_html=False)

def create_player_performance_chart(player_team_points_df):
    top_players = player_team_points_df.nlargest(10, 'PlayerPoints')
    fig = px.bar(
        top_players,
        x='Player Name',
        y='PlayerPoints',
        color='Team Name',
        title='Top 10 MVPs',
        labels={'PlayerPoints': 'Points'},
        text='PlayerPoints'
    )
    fig.update_traces(textposition='outside')
    return fig.to_html(full_html=False)

def create_role_distribution_chart(player_team_points_df):
    role_points = player_team_points_df.groupby('Role')['PlayerPoints'].sum().reset_index()
    fig = px.pie(
        role_points,
        values='PlayerPoints',
        names='Role',
        title='Points Distribution by Role',
        hole=0.3
    )
    return fig.to_html(full_html=False)

# Add row styling based on best 11 membership
def style_row(row, best_11_set):
    if (row['Team Name'], row['Player Name']) in best_11_set:
        return 'background-color: #e6ffe6'  # Light green background
    return ''

def generate_html_report(team_points_df, player_team_points_df, series_stats_df, scoreboard_stats_df, best_11_df):
    
    team_chart = create_team_points_chart(team_points_df)
    player_chart = create_player_performance_chart(player_team_points_df)
    role_chart = create_role_distribution_chart(player_team_points_df)

    # Create clickable player names with URLs and add background color for best 11 players
    player_team_points_df = player_team_points_df.sort_values(['Team Name', 'PlayerPoints'])
    
    # Create a set of (team, player) tuples from best_11_df for faster lookup
    best_11_set = set(zip(best_11_df['Team Name'], best_11_df['Player Name']))
    

    styled_df = player_team_points_df.copy()
    styled_df['Playing11'] = styled_df.apply(lambda x: 'Yes' if (x['Team Name'], x['Player Name']) in best_11_set else '', axis=1)    

    # Convert to HTML with styling
    styled_df['Player Name'] = styled_df.apply(
        lambda x: f'<a href="{x.PlayerId}" target="_blank">{x["Player Name"]}</a>', axis=1)
    
    # Drop PlayerId column
    styled_df = styled_df.drop('PlayerId', axis=1)

    # Convert DataFrames to HTML tables with Bootstrap styling

    team_table = team_points_df.to_html(classes=['table', 'table-striped', 'table-hover'], 
                                      index=False, 
                                      float_format=lambda x: '{:.2f}'.format(x) if pd.notnull(x) else '')
    player_table = styled_df.to_html(classes=['table', 'table-striped', 'table-hover'],
                                   index=False,
                                   float_format=lambda x: '{:.2f}'.format(x) if pd.notnull(x) else '',
                                   escape=False)         
    
    
    # Convert series stats DataFrames to HTML tables
    series_tables = ""
    for key, df in series_stats_df.items():
        if key == "MOST_RUNS":
            key = "Best Batter"
        elif key == "MOST_WICKETS":
            key = "Best Bowler"
        else:
            logging.error(f"Unknown key {key}")

        df['Team Name'] = df['Team Name'].fillna(value="LORDX1")
        del df['Player Name']
        cols = df.columns.tolist()
        #print(cols)
        cols = cols[1:2] + cols[:1] + cols[2:]        
        #print(cols)
        df = df[cols]
        series_tables += f"""
            <h2>{key}</h2>
            <div class="table-container">
                {df.head().to_html(classes=['table', 'table-striped', 'table-hover'], 
                           index=False,
                           float_format=lambda x: '{:.2f}'.format(x) if pd.notnull(x) else '')}
            </div>
        """

    # Convert series stats DataFrames to HTML tables
    sb_tables = ""
    for key, df in scoreboard_stats_df.items():
        
        if key == "Bat":
            key = "Most 50s Per Team"
        elif key == "Bowl":
            key = "Most 3fers Per Team"
        elif key == "Field":
            key = "Best Fielder"
        else:
            logging.error(f"Unknown key {key}")

        #del df['Player Name']
        cols = df.columns.tolist()
        print(cols)
        sb_tables += f"""
            <h2>{key}</h2>
            <div class="table-container">
                {df.head().to_html(classes=['table', 'table-striped', 'table-hover'], 
                           index=True,
                           float_format=lambda x: '{:.2f}'.format(x) if pd.notnull(x) else '')}
            </div>
        """
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FPL IPL 2025 Leaderboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
       <style>
    .chart-container {{ 
        margin: 20px 0; 
    }}
    .table-container {{ 
        margin: 20px 0; 
    }}
    .timestamp {{ 
        color: #666; 
        font-style: italic; 
        margin: 20px 0; 
    }}
    .table {{ 
        width: 100%; 
        border-collapse: collapse; 
        margin-bottom: 1rem; 
    }}
    .table th {{ 
        background-color: #f8f9fa;
        padding: 12px 8px;
        text-align: left;
        font-weight: bold;
        border-bottom: 2px solid #dee2e6;
    }}
    .table td {{ 
        padding: 8px;
        vertical-align: middle;
        border-bottom: 1px solid #dee2e6;
    }}
    .table tbody tr:hover {{ 
        background-color: rgba(0,0,0,.075); 
    }}

    /* Background color for the top 3 rows */
    #team-table tbody tr:nth-child(1) {{ 
        background-color: gold !important; 
    }}
    #team-table tbody tr:nth-child(2) {{ 
        background-color: silver !important; 
    }}
    #team-table tbody tr:nth-child(3) {{ 
        background-color: #cd7f32 !important; 
    }}

    body {{
        margin: 0;
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background-color: #f5f5f5;
        color: #333;
        line-height: 1.6;
        padding: 20px;
    }}

    .header-menu {{
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 10px 0;
        margin-bottom: 20px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }}

    .header-menu a {{
        color: white;
        text-decoration: none;
        padding: 10px 20px;
        font-size: 16px;
    }}

    .header-menu a:hover {{
        background-color: #34495e;
    }}

    .content {{
        flex: 1;
        display: flex;
        justify-content: center;
        align-items: center;
        width: 100%;
        overflow: auto;
        padding: 20px;
        box-sizing: border-box;
    }}

    #pdf-container {{
        width: 100%;
        height: 100%;
        background: white;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }}

    nav a {{
        color: white;
        text-decoration: none;
        padding: 5px 10px;
        border-radius: 4px;
        transition: background-color 0.3s;
    }}

    nav a:hover {{
        background-color: rgba(255,255,255,0.1);
    }}
</style>
        <!-- FontAwesome (Include this in your HTML) -->
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    </head>
    <body>
     <header>
        <div class="header-menu">
            <nav style="display: flex; justify-content: center; align-items: center;">
                <a href="/" style="font-size: 14px; padding: 8px 15px;">Home</a>
            </nav>
        </div>
    </header>  
        <div class="container">
            <h1 class="mt-4 mb-4">FPL IPL 2025 Leaderboard</h1>
            <p class="timestamp">Last updated: {timestamp}</p>
            
            <h2>Points Table</h2>
            
            <div id="team-table" class="table-container">{team_table}</div>
            <div class="chart-container">{team_chart}</div>

            <div class="table-container">{sb_tables}</div>
            <div class="table-container">{series_tables}</div>
            
            <h2>MVPs</h2>
            <div class="chart-container">{player_chart}</div>
            <div class="chart-container">{role_chart}</div>
            <div class="table-container">{player_table}</div>

            
        </div>
    </body>
    </html>
    """
    
    with open("templates/FPL-IPL2025-Points.html", "w", encoding='utf-8') as f:
        f.write(html_content)
    
    logging.info("HTML report generated successfully")

def edit_dataframe_values(df, search_str, replace_str):
    # Replace values in all string columns of the dataframe only when exact match
    for column in df.select_dtypes(include=['object']).columns:
        df[column] = df[column].apply(lambda x: replace_str if x == search_str else x)
    return df

# function to check if player has name_array values and use that for replacement
# for example - if df has player name Jaddu and that exists as name_array value for a player
# then replace Jaddu with player name found in Player model
def replace_player_name(df, Player):
    # first check if any player name value from df not found in player name in Player 
    # if not found then replace with player name found in Player
    for index, row in df.iterrows():
        player_name = row['Player Name']
        player = Player.query.filter_by(name=player_name).first()
        if player is None:
            # check if player name is in name_array of any player
            player = Player.query.filter(Player.name_array.any(player_name)).first()
            if player is not None:
                df.at[index, 'Player Name'] = player.name    
    return df



def generate_player_profile_url(player_id):
    """
    Generates a player profile URL using a fixed base URL and player ID
    """
    base_url = "https://m.cricbattle.com/Player-Profile?TournamentId=12659&PlayerId="
    return f"{base_url}{player_id}" 


def main(Player, PlayerRanking):
    #players_df = read_excel_file("players.xlsx")
    #write code to extract players table from cricbattle.db sqllite database and save as dataframe
    # Connect to SQLite database
    #conn = sqlite3.connect('/mnt/sqlite/cricbattle.db')
    
    # Query players table and save as dataframe
    players_df = pd.DataFrame([{
        'name': p.name,
        'team_name': p.team_name, 
        'role': p.role,
        'ipl_team': p.ipl_team,
        'foreign_player': p.foreign_player,
        'first_match_id': p.first_match_id,
        'selling_price': p.selling_price,
        'category': p.category,
        'points_reduction': p.points_reduction

        } for p in Player.query.all()])
    # Close database connection
    #conn.close()    

    players_df = players_df.rename(columns={'name': 'Player Name'})
    players_df = players_df.rename(columns={'team_name': 'Team Name'})
    players_df = players_df.rename(columns={'role': 'Role'})
    players_df = players_df.rename(columns={'ipl_team': 'IPL Team'})

    #player_rankings_df = read_excel_file("player_rankings.xlsx")
    # create player_rankings_df from PlayerRanking model

    player_rankings_df = pd.DataFrame([{
        'PlayerId': pr.PlayerId,
        'PlayerName': pr.PlayerName,
        'PlayerTypeId': pr.PlayerTypeId,
        'PlayerFormId': pr.PlayerFormId,
        'IsOut': pr.IsOut,
        'IsInjured': pr.IsInjured,
        'Price': pr.Price,
        'RealTeamName': pr.RealTeamName,
        'TotalScore': pr.TotalScore,
        'IsShowTrophy': pr.IsShowTrophy,
        'Rank': pr.Rank,
        'PRank': pr.PRank
        
        } for pr in PlayerRanking.query.all()])
    
  
    print(player_rankings_df.head())
    if not players_df.empty and not player_rankings_df.empty:        
        try:
            
            # Merge the dataframes
            merged_df = pd.merge(players_df, player_rankings_df, left_on="Player Name", right_on="PlayerName")

                        
            # Apply point reduction if applicable
            if 'point_reduction' in merged_df.columns:
                merged_df['TotalScore'] = merged_df.apply(lambda row: int(row['TotalScore'] - row['point_reduction']) if pd.notna(row['point_reduction']) else int(row['TotalScore']), axis=1)    


            print(merged_df[merged_df['Player Name'].str.contains('Ben Dwarshuis', case=False)])    

                  
              
            # Add Best 11 Points  
            best_11_data = calculate_best_11(merged_df)  
            team_points_df = merged_df.groupby('Team Name')['TotalScore'].sum().reset_index()  
            team_points_df.rename(columns={'TotalScore': 'TotalPoints'}, inplace=True)  
              
            # Add Best 11 Points  
            best_11_dict = {team: points for team, points, _ in best_11_data}  
            team_points_df['Best11Points'] = team_points_df['Team Name'].map(best_11_dict)  

            print(best_11_data)
            # Create list of team and player names from best_11_data
            team_players = []
            for team, _, players in best_11_data:
                for player in players:
                    team_players.append({
                        'Team Name': team,
                        'Player Name': player['Player Name']
                    })

            # Convert to DataFrame
            best_11_df = pd.DataFrame(team_players)        
            print(best_11_df)                
            
  
            # Sort by Best11Points  
            team_points_df.sort_values(by='Best11Points', ascending=False, inplace=True)
              
            # Second table: Points per player per team, grouped by team using team name from players_df  
            player_team_points_df = merged_df.groupby(['PlayerId', 'Team Name', 'Player Name', 'Role', 'IPL Team'])['TotalScore'].sum().reset_index() 
            player_team_points_df.rename(columns={'TotalScore': 'PlayerPoints'}, inplace=True) 
            print(player_team_points_df.head())
            # Add player profile URLs to the DataFrame
            player_team_points_df['PlayerId'] = player_team_points_df['PlayerId'].apply(generate_player_profile_url) 
            print(player_team_points_df.head())    
           
            # Get individual series stats
            #df_series = update_series_stats.main()

            # Connect to SQLite database
            conn = sqlite3.connect('cricket_stats.db')

            # Query data from scoreboard tables
            df_series = {}

            # Query batting stats
            df_series["MOST_RUNS"] = pd.read_sql_query("""
                SELECT * from cricket_most_runs
            """, conn)

            # Query bowling stats  
            df_series["MOST_WICKETS"] = pd.read_sql_query("""
                SELECT * from cricket_most_wickets
            """, conn)

            # Query bowling stats  
            df_series["MOST_SIXES"] = pd.read_sql_query("""
                SELECT * from cricket_most_sixes
            """, conn)

            conn.close()

            # Print first few extracted tables
            for key, df in df_series.items():
                #print(f"\n=== {key} ===")
                #print(df.head())

                # Merge the dataframes
                # Get the column name in df based on position (assuming the column to merge on is always in position 0)
                merge_column = df.columns[1]  # Get the first column in each DataFrame (e.g., 'Batter', 'Player', 'Bowler')
                #print(merge_column)
                
                merged_df = pd.merge(players_df[['Team Name', 'Player Name']], df, left_on="Player Name", right_on=merge_column, how='right')  
                #print(merged_df.head())
                df_series[key] = merged_df

            # Get individual series stats
            

            # Connect to SQLite database
            conn = sqlite3.connect('cricket_stats.db')

            # Query data from scoreboard tables
            df_scoreboard = {}

            # Query batting stats
            df_scoreboard["Bat"] = pd.read_sql_query("""
                SELECT * from cricket_bat
            """, conn)

            # Query bowling stats  
            df_scoreboard["Bowl"] = pd.read_sql_query("""
                SELECT * from cricket_bowl
            """, conn)

            # Query fielding stats
            df_scoreboard["Field"] = pd.read_sql_query("""
                SELECT * from cricket_field
            """, conn)

            conn.close()

            # Print first few extracted tables
            for key, df in df_scoreboard.items():
                #print(f"\n=== {key} ===")
                #print(df.head())

                # Merge the dataframes
                # Get the column name in df based on position (assuming the column to merge on is always in position 0)
                merge_column = df.columns[0]  # Get the first column in each DataFrame (e.g., 'Batter', 'Player', 'Bowler')
                #print(merge_column)

                # check if df has no rows
                if df.empty:
                    continue


                edit_dataframe_values(df, "Kohli", "Virat Kohli")
                edit_dataframe_values(df, "Mitchell Santner (c)", "Mitchell Santner")
                edit_dataframe_values(df, "William ORourke", "William O’Rourke")
                edit_dataframe_values(df, "Salman Agha", "Agha Salman")
                edit_dataframe_values(df, "Shaheen Afridi", "Shaheen Shah Afridi")
                edit_dataframe_values(df, "Latham", "Tom Latham")
                edit_dataframe_values(df, "Tom Latham (wk)", "Tom Latham")
                edit_dataframe_values(df, "Latham (wk)", "Tom Latham")
                edit_dataframe_values(df, "Rahul", "KL Rahul")
                edit_dataframe_values(df, "Rizwan", "Mohammad Rizwan")
                edit_dataframe_values(df, "Shami", "Mohammed Shami")
                edit_dataframe_values(df, "Shanto", "Najmul Hossain Shanto")
                edit_dataframe_values(df, "Shanto (c)", "Najmul Hossain Shanto")
                edit_dataframe_values(df, "Williamson", "Kane Williamson")
                edit_dataframe_values(df, "Azmatullah", "Azmatullah Omarzai")
                edit_dataframe_values(df, "Bavuma", "Temba Bavuma")
                edit_dataframe_values(df, "Temba Bavuma (c)", "Temba Bavuma")
                edit_dataframe_values(df, "Bavuma (c)", "Temba Bavuma")
                edit_dataframe_values(df, "Maharaj", "Keshav Maharaj")
                edit_dataframe_values(df, "Shahidi", "Hashmatullah Shahidi")
                edit_dataframe_values(df, "Rickelton (wk)", "Ryan Rickelton")
                edit_dataframe_values(df, "Rickelton", "Ryan Rickelton")
                edit_dataframe_values(df, "van der Dussen", "Rassie van der Dussen")
                edit_dataframe_values(df, "Markram", "Aiden Markram")
                edit_dataframe_values(df, "Duckett", "Ben Duckett")
                edit_dataframe_values(df, "Josh Inglis (wk)", "Josh Inglis")
                edit_dataframe_values(df, "Labuschagne", "Marnus Labuschagne")
                edit_dataframe_values(df, "Zampa", "Adam Zampa")
                edit_dataframe_values(df, "Maxwell", "Glen Maxwell")
                edit_dataframe_values(df, "Livingstone", "Liam Livingstone")
                edit_dataframe_values(df, "Rabada", "Kagiso Rabada")
                edit_dataframe_values(df, "Rahmat", "Rahmat Shah")
                edit_dataframe_values(df, "Axar", "Axar Patel")
                edit_dataframe_values(df, "Conway", "Devon Conway")
                edit_dataframe_values(df, "Santner (c)", "Mitchell Santner")
                edit_dataframe_values(df, "Santner", "Mitchell Santner")
                edit_dataframe_values(df, "Root", "Joe Root")
                edit_dataframe_values(df, "Dwarshuis", "Ben Dwarshuis")
                edit_dataframe_values(df, "Nabi", "Mohammad Nabi")
                edit_dataframe_values(df, "Gurbaz", "Rahmanullah Gurbaz")
                edit_dataframe_values(df, "Glen Maxwell", "Glenn Maxwell")
                edit_dataframe_values(df, "Gulbadin", "Gulbadin Naib")
                edit_dataframe_values(df, "Klaasen", "Heinrich Klaasen")
                edit_dataframe_values(df, "Mulder", "Wiaan Mulder")
                edit_dataframe_values(df, "Rohit Sharma (c)", "Rohit Sharma")
                edit_dataframe_values(df, "Steven Smith (c)", "Steven Smith")
                edit_dataframe_values(df, "Heinrich Klaasen (wk)", "Heinrich Klaasen")

                replace_player_name(df, Player)

                merged_df = pd.merge(players_df[['Team Name', 'Player Name', 'first_match_id']], df, left_on="Player Name", right_on=merge_column, how='right')  
            
                # Filter out players who joined after the match
                merged_df = merged_df[~((pd.notna(merged_df['first_match_id'])) & (merged_df['first_match_id'].astype(float) > merged_df['matchId'].astype(float)))]   

                del merged_df['first_match_id']
                del merged_df["matchId"]

                logging.info(f"Removed entries for replaced players for {key}")         
                
                if "Field" in key:
                    #print(merged_df)
                    # For fielding stats, aggregate by player name first
                    player_catches = merged_df.groupby(['Team Name', 'Player'])['Catches'].sum().reset_index(name='Player Count')                    
                    player_catches = player_catches.sort_values('Player Count', ascending=False)
                    player_catches.index = range(1, len(player_catches) + 1)
                    df_scoreboard[key] = player_catches     
                    #print(player_catches)
                else:
                    #df_scoreboard[key] = merged_df
                    print(merged_df)
                    team_counts = merged_df.groupby('Team Name').size().reset_index(name='Player Count')
                    team_counts = team_counts.sort_values('Player Count', ascending=False)
                    team_counts.index = range(1, len(team_counts) + 1)     
                    df_scoreboard[key] = team_counts           
                
                print(df_scoreboard[key])                               
                
                                            
            # Generate HTML report
            generate_html_report(team_points_df, player_team_points_df, df_series, df_scoreboard, best_11_df)
            
            logging.info("Data transformation and HTML generation complete.")
            
        except Exception as e:
            logging.error(f"An error occurred during data processing: {str(e)}")
            traceback.print_exception(type(e), e, e.__traceback__)
    else:
        logging.error("Data processing aborted due to previous errors.")

if __name__ == "__main__":
    main()