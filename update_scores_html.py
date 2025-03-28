import traceback
import pandas as pd
import app
import plotly.express as px
import plotly.graph_objects as go
from openpyxl import load_workbook
import logging
from datetime import datetime
from openpyxl.styles import PatternFill, Font  
from openpyxl.utils import get_column_letter  
import shutil  
import os  
import sqlite3
from datetime import datetime
import pytz


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
    #logging.info("Calculating best 11 players for each team")  
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
            #logging.info(f"Processing player {player['Player Name']}")
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
  
        #logging.info(f"IPL Team count so far {ipl_team_counts} for team {player_ipl_team}") 
        #logging.info(f"Overseas count so far {overseas_counter} for team {player_ipl_team}")
  
        # Ensure at least 1 WK is selected  
        for _, player in players.iterrows():  
            player_is_overseas = player['foreign_player']  
            player_ipl_team = player['IPL Team']
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
                #logging.info(f"Adding player {player['Player Name']} for team {team}")
                if bat_count >= bat_needed:  
                    break  
  

  
        # Ensure we have exactly 11 players by filling any gaps with highest scorers  
        while len(selected) < 11:  
            for _, player in players.iterrows():  
                player_is_overseas = player['foreign_player']  
                player_ipl_team = player['IPL Team']
                if len(selected) >= 11:  
                    break 
                player_id = player['PlayerId']  
                #logging.info(f"Re-Processing player {player['Player Name']}")
                if player_id in selected_ids or  (player_is_overseas and overseas_counter >= max_overseas) or ipl_team_counts.get(player_ipl_team, 0) >= max_ipl_team:
                    #logging.info(f"Player ID: {player_id}, Selected IDs: {selected_ids}, Overseas Counter: {overseas_counter}, Max Overseas: {max_overseas}, IPL Team: {player_ipl_team}, IPL Team Count: {ipl_team_counts.get(player_ipl_team, 0)}, Max IPL Team: {max_ipl_team}, Is Overseas: {player_is_overseas}") 
                    #logging.info(f"Skipping player {player['Player Name']} due to foreign player or IPL team logic")
                    continue  
                #logging.info(f"Adding player {player['Player Name']} to best 11") 
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

def generate_html_report(team_points_df, player_team_points_df, series_stats_df, scoreboard_stats_df, best_11_df, player_of_the_day, team_of_the_day, league, live_players_list, all_team_points_df):
    
    team_chart = create_team_points_chart(team_points_df)
    player_chart = create_player_performance_chart(player_team_points_df)
    role_chart = create_role_distribution_chart(player_team_points_df)
    race_to_finish_chart = create_race_to_finish_chart(all_team_points_df)

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
        elif key == "MOST_SIXES":
            key = "Most Sixes"
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
        elif key == "POTM":
            key = "Most POTMs"
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
    
   

    timestamp = datetime.now(pytz.timezone('Europe/Paris')).strftime("%Y-%m-%d %H:%M:%S %Z")     

    # extract player of the day and team of the day info for today
    """     'today': {'team': today_best_team[0], 'score': today_best_team[1]},
        'yesterday': {'team': yesterday_best_team[0], 'score': yesterday_best_team[1]}
    }
    and player of the day has
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
    } """

    print(player_of_the_day['today']['name'], player_of_the_day['today']['team'], player_of_the_day['today']['points'])
    print(team_of_the_day['today']['team'], team_of_the_day['today']['score'])
    print(live_players_list)

    if player_of_the_day['today']['points'] is  None or player_of_the_day['today']['points'] < 100:
        player_of_the_day_points = player_of_the_day['yesterday']['points']
        player_of_the_day_team = player_of_the_day['yesterday']['team']
        player_of_the_day_name = player_of_the_day['yesterday']['name']

    else:
        player_of_the_day_points = player_of_the_day['today']['points']
        player_of_the_day_team = player_of_the_day['today']['team']
        player_of_the_day_name = player_of_the_day['today']['name']

    if team_of_the_day['today']['score'] is  None  or team_of_the_day['today']['score'] < 100  :
        team_of_the_day_score = team_of_the_day['yesterday']['score']
        team_of_the_day_name = team_of_the_day['yesterday']['team']

    else:
        team_of_the_day_score = team_of_the_day['today']['score']
        team_of_the_day_name = team_of_the_day['today']['team']

    if league == "JAL":
        leaderboard_title = "JAL IPL 2025"
        template_filename = "JAL-IPL2025-Points.html"
    else:
        leaderboard_title = "FPL IPL 2025"
        template_filename = "FPL-IPL2025-Points.html"

    html_content = f"""
    <!DOCTYPE html>
    <html data-theme="light">
    <head>
        <title>{leaderboard_title} Leaderboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
       <style>
    :root[data-theme="light"] {{
        --bg-color: #f5f5f5;
        --text-color: #333;
        --card-bg: white;
        --table-header-bg: #f8f9fa;
        --table-border: #dee2e6;
        --highlight-text: #1e3c72;
        --table-text: #333;
    }}

    :root[data-theme="dark"] {{
        --bg-color: #1a1a1a;
        --text-color: #e0e0e0;
        --card-bg: #2d2d2d;
        --table-header-bg: #333;
        --table-border: #404040;
        --highlight-text: #7aa2e8;
        --table-text: #e0e0e0;
    }}

    .chart-container {{ 
        margin: 20px 0; 
    }}
    .table-container {{ 
        margin: 20px 0; 
    }}
    .timestamp {{ 
        color: var(--text-color); 
        font-style: italic; 
        margin: 20px 0; 
    }}
    .table {{ 
        width: 100%; 
        border-collapse: collapse; 
        margin-bottom: 1rem;
        color: var(--table-text) !important;
    }}
    .table th {{ 
        background-color: var(--table-header-bg);
        padding: 12px 8px;
        text-align: left;
        font-weight: bold;
        border-bottom: 2px solid var(--table-border);
        color: var(--table-text) !important;
    }}
    .table td {{ 
        padding: 8px;
        vertical-align: middle;
        border-bottom: 1px solid var(--table-border);
        color: var(--table-text) !important;
    }}
    .table tbody tr:hover {{ 
        background-color: rgba(0,0,0,.075); 
    }}

    /* Background color for the top 3 rows in light mode */
    [data-theme="light"] #team-table tbody tr:nth-child(1) {{ 
        background-color: gold !important; 
        color: #000 !important;
        font-weight: bold;
    }}
    [data-theme="light"] #team-table tbody tr:nth-child(2) {{ 
        background-color: silver !important; 
        color: #000 !important;
        font-weight: bold;
    }}
    [data-theme="light"] #team-table tbody tr:nth-child(3) {{
        background-color: #cd7f32 !important; /* Bronze */
        color: #000 !important;
        font-weight: bold;
    }}

    /* Background color for the top 3 rows in dark mode */
    [data-theme="dark"] #team-table tbody tr:nth-child(1) {{
        background-color: #FFD700 !important; /* Bright gold */
        font-weight: bold;
        color: var(--text-color);
    }}
    [data-theme="dark"] #team-table tbody tr:nth-child(2) {{
        background-color: #A9A9A9 !important; /* Darker silver for contrast */
        font-weight: bold;
        color: var(--text-color);
    }}
    [data-theme="dark"] #team-table tbody tr:nth-child(3) {{ 
        background-color: #DAA520 !important; /* Goldenrod (better than burlywood) */
        font-weight: bold;
        color: var(--text-color);
        
    }}



    body {{
        margin: 0;
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background-color: var(--bg-color);
        color: var(--text-color);
        line-height: 1.6;
        padding: 20px;
        transition: background-color 0.3s, color 0.3s;
    }}

    .header-menu {{
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 10px 0;
        margin-bottom: 20px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 20px;
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

    .theme-switch {{
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    .theme-switch-button {{
        background: none;
        border: none;
        color: white;
        cursor: pointer;
        padding: 5px;
        font-size: 20px;
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
        background: var(--card-bg);
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

    .highlight-card {{
        background: var(--card-bg);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        transition: transform 0.3s ease;
    }}

    .highlight-card:hover {{
        transform: translateY(-5px);
    }}

    .highlight-card h3 {{
        color: var(--highlight-text);
        margin-bottom: 15px;
        font-size: 1.5rem;
    }}

    .highlight-card .score {{
        font-size: 2rem;
        font-weight: bold;
        color: var(--highlight-text);
    }}

    .highlight-card .label {{
        color: var(--text-color);
        font-size: 0.9rem;
        margin-bottom: 5px;
    }}

    .highlights-container {{
        display: flex;
        gap: 20px;
        margin-bottom: 30px;
    }}

    .refresh-button {{
        background: #2a5298;
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        margin-left: auto;
        z-index: 999;
        position: relative;
        opacity: 1;
        visibility: visible;
    }}

    .refresh-button:hover {{
        background: #1e3c72;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }}

    .refresh-button i {{
        transition: transform 0.5s ease;
    }}

    .refresh-button:hover i {{
        transform: rotate(180deg);
    }}

    .header-content {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
    }}

    /* Add styles for links in dark mode */
    [data-theme="dark"] .table a {{
        color: #7aa2e8;
    }}

    [data-theme="dark"] .table a:hover {{
        color: #a8c4f3;
    }}

        /* New ticker styles */
            .ticker-wrap {{
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                padding: 10px 0;
                overflow: hidden;
                z-index: 9999;
                box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                white-space: nowrap;
            }}

            .ticker {{
                display: flex;
                width: max-content;
                animation: ticker-scroll 60s linear infinite;
            }}

            .ticker-item {{
                display: inline-flex;
                align-items: center;
                padding: 0 30px;
                color: white;
                font-weight: 500;
            }}

            .ticker-item .player-name {{
                margin-right: 10px;
                font-weight: bold;
            }}

            .ticker-item .score {{
                color: #7fff00;
            }}

            @keyframes ticker-scroll {{
                from {{
                    transform: translateX(0);
                }}
                to {{
                    transform: translateX(-50%);
                }}
            }}


            /* Adjust body padding to account for ticker */
            body {{
                padding-top: 60px;
            }}

            @media (max-width: 768px) {{
                .ticker-item {{
                    padding: 0 15px;
                    font-size: 14px;
                }}
            }}
        </style>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    </head>
    <body>
        <div class="ticker-wrap">
            <div class="ticker">
                {
                    ''.join([
                        f'<div class="ticker-item"><span class="player-name">{row["name"]}</span> <span class="score">{row["fpl_team"]}</span></div>'
                        for _ in range(2) for _, row in live_players_list.iterrows()  # Repeat the list 3 times
                    ])
                }
            </div>
        </div>


        <header>
            <div class="header-menu">
                <nav style="display: flex; align-items: center;">
                    <a href="/" style="font-size: 14px; padding: 8px 15px;">Home</a>
                </nav>
                <div class="theme-switch">
                    <button class="theme-switch-button" onclick="toggleTheme()">
                        <i class="fas fa-moon"></i>
                    </button>
                </div>
            </div>
        </header>

        <div class="container">
            <div class="header-content">
                <h1 class="mt-4 mb-4">{leaderboard_title} Leaderboard</h1>
                <button class="refresh-button" onclick="window.location.reload()">
                    <i class="fas fa-sync-alt"></i>
                    Refresh
                </button>
            </div>
            <p class="timestamp"> {timestamp} </p>

            <div class="highlights-container">
                <div class="highlight-card">
                    <h3><i class="fas fa-trophy"></i> Team of the Day</h3>
                    <div class="label">Team Name</div>
                    <div class="score">{team_of_the_day_name}</div>
                    <div class="label">Score</div>
                    <div class="score">{team_of_the_day_score}</div>
                </div>

                <div class="highlight-card">
                    <h3><i class="fas fa-star"></i> Player of the Day</h3>
                    <div class="label">Player Name</div>
                    <div class="score">{player_of_the_day_name}</div>
                    <div class="label">Team</div>
                    <div class="score">{player_of_the_day_team}</div>
                    <div class="label">Score</div>
                    <div class="score">{player_of_the_day_points}</div>
                </div>            
                </div>
            
            <h2>Points Table</h2>
            
            <div id="team-table" class="table-container">{team_table}</div>
            <div class="chart-container">{team_chart}</div>
            <div class="chart-container">{race_to_finish_chart}</div>

            <div class="table-container">{sb_tables}</div>
            <div class="table-container">{series_tables}</div>
            
            <h2>MVPs</h2>
            <div class="chart-container">{player_chart}</div>
            <div class="chart-container">{role_chart}</div>
            <div class="table-container">{player_table}</div>
        </div>

        <script>
            function toggleTheme() {{
                const html = document.documentElement;
                const currentTheme = html.getAttribute('data-theme');
                const newTheme = currentTheme === 'light' ? 'dark' : 'light';
                html.setAttribute('data-theme', newTheme);
                
                const themeIcon = document.querySelector('.theme-switch-button i');
                themeIcon.className = newTheme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
                
                // Store theme preference
                localStorage.setItem('theme', newTheme);
            }}

            // Set initial theme based on stored preference
            const storedTheme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', storedTheme);
            const themeIcon = document.querySelector('.theme-switch-button i');
            themeIcon.className = storedTheme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        </script>
    </body>
    </html>
    """
    
    with open(f"templates/{template_filename}", "w", encoding='utf-8') as f:        
        f.write(html_content)
    
    logging.info(f"HTML report generated successfully for league: {league}")
    
def edit_dataframe_values(df, search_str, replace_str):
    # Replace values in all string columns of the dataframe only when exact match
    for column in df.select_dtypes(include=['object']).columns:
        df[column] = df[column].apply(lambda x: replace_str if x == search_str else x)
    return df

# function to check if player has name_array values and use that for replacement
# for example - if df has player name Jaddu and that exists as name_array value for a player
# then replace Jaddu with player name found in Player model
def replace_player_name(df, Player):
    # if not found then replace with player name found in Player
    #print(df)
    # first find all player rows where name_array is not null not none not blank
    players_with_aliases = Player.query.filter(
        Player.name_array.isnot(None)
    ).all()            

    for index, row in df.iterrows():
        #print(row)
        print("replace_player_name using", row[0])
        player_name = row[0]
        player = Player.query.filter_by(name=player_name).first()
        if player is None:
            # check if player name is in name_array of any player
            # first find all player rows where name_array is not null not none not blank
            # check if player name is in name_array of any player

            for player in players_with_aliases:
                if player_name in player.name_array:
                    
                    # check if column name in df is bowler and replace that too
                    if 'Bowler' in df.columns:                                      
                        df.at[index, 'Bowler'] = player.name
                    else:
                        df.at[index, 'Player'] = player.name
                    print("Player name replaced from %s to %s", player_name, player.name)
                    player_name = player.name
                    break     

        player = Player.query.filter_by(name=player_name).first()
        if player is None :
            logging.error("Player name alias not found for %s", player_name)                       

    return df



def generate_player_profile_url(player_id):
    """
    Generates a player profile URL using a fixed base URL and player ID
    """
    base_url = "https://m.cricbattle.com/Player-Profile?TournamentId=12746&PlayerId="
    return f"{base_url}{player_id}" 


def create_race_to_finish_chart(all_team_points_df):
     # Create line chart
    fig = px.line(all_team_points_df, 
                x='date', 
                y='Best11Points',
                color='Team Name',
                title='Race to Finish',
                labels={'Best11Points': 'Best11Points', 'date': 'Date'},
                line_shape='linear', markers=True)

    fig.update_layout(xaxis_title='Date', 
                    yaxis_title='Points',
                    legend_title='Team Name')

    return fig.to_html(full_html=False)  

def main(Player, PlayerRanking, PlayerRankingPerDay, player_of_the_day, team_of_the_day, league="", live_players_list=pd.DataFrame()):
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
    
    player_rankings_per_day_df = pd.DataFrame([{
        'PlayerId': pr.PlayerId,
        'PlayerName': pr.PlayerName,
        'TotalScore': pr.TotalScore,
        'timestamp': pr.timestamp
        } for pr in PlayerRankingPerDay.query.all()])
    
    #print(player_rankings_per_day_df.head())
    if not players_df.empty and not player_rankings_per_day_df.empty:
        try:

            # keep only max timestamp entries per day in player_rankings_per_day_df
            # Convert timestamp to datetime if not already

            # Extract date from timestamp 
            player_rankings_per_day_df['date'] = player_rankings_per_day_df['timestamp'].dt.date
            #print(player_rankings_per_day_df)  

            # Sort by timestamp descending and keep first row per date per playername
            
            player_rankings_per_day_df = player_rankings_per_day_df.sort_values('timestamp', ascending=False).groupby(['date', 'PlayerName']).first().reset_index() 
            #print(player_rankings_per_day_df)  

            del player_rankings_per_day_df['timestamp']

            #print(player_rankings_per_day_df)         
            
            # Sort by date
            player_rankings_per_day_df = player_rankings_per_day_df.sort_values('date')

            # Get unique dates
            dates = player_rankings_per_day_df['date'].unique()

            #print(dates)

            # Initialize empty list to store daily team points
            daily_team_points = []

            # Loop through each date
            for date in dates:
                # Get data for current date
                #print("processing for date : ", date)
                daily_df = player_rankings_per_day_df[player_rankings_per_day_df['date'] == date]

                #print(daily_df)
                

                merged_df_perday = pd.merge(players_df, daily_df, left_on="Player Name", right_on="PlayerName")

                #print(merged_df_perday)

                # Add Best 11 Points  
                best_11_data_per_day = calculate_best_11(merged_df_perday)  

                #print(best_11_data_per_day)
                team_points_df_per_day = merged_df_perday.groupby('Team Name')['TotalScore'].sum().reset_index()  
                team_points_df_per_day.rename(columns={'TotalScore': 'TotalPoints'}, inplace=True) 

                #print(team_points_df_per_day)

                # Add Best 11 Points  
                best_11_dict_per_day = {team: points for team, points, _ in best_11_data_per_day}  
                team_points_df_per_day['Best11Points'] = team_points_df_per_day['Team Name'].map(best_11_dict_per_day)    

                team_points_df_per_day['date'] = date          
                
                
                daily_team_points.append(team_points_df_per_day)
                #print(daily_team_points)


        except Exception as e:
            logging.error(f"An error occurred during race to finish processing: {str(e)}")
            traceback.print_exception(type(e), e, e.__traceback__)

        # Combine all daily points
        all_team_points = pd.concat(daily_team_points)
        #print(all_team_points)
        #exit()

    
  
    #print(player_rankings_df.head())
    if not players_df.empty and not player_rankings_df.empty:        
        try:
            
            # Merge the dataframes
            merged_df = pd.merge(players_df, player_rankings_df, left_on="Player Name", right_on="PlayerName")

                        
            # Apply point reduction if applicable
            if 'point_reduction' in merged_df.columns:
                merged_df['TotalScore'] = merged_df.apply(lambda row: int(row['TotalScore'] - row['point_reduction']) if pd.notna(row['point_reduction']) else int(row['TotalScore']), axis=1)    


            #print(merged_df[merged_df['Player Name'].str.contains('Ben Dwarshuis', case=False)])    

                  
              
            # Add Best 11 Points  
            best_11_data = calculate_best_11(merged_df)  
            team_points_df = merged_df.groupby('Team Name')['TotalScore'].sum().reset_index()  
            team_points_df.rename(columns={'TotalScore': 'TotalPoints'}, inplace=True)  
              
            # Add Best 11 Points  
            best_11_dict = {team: points for team, points, _ in best_11_data}  
            team_points_df['Best11Points'] = team_points_df['Team Name'].map(best_11_dict)  

            #print(best_11_data)
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
            #print(best_11_df)                
            
  
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

            # Create SQLite connection
            conn = sqlite3.connect('/mnt/sqlite/cricket_stats.db' if os.environ.get("WEBSITE_SITE_NAME") else 'instance/cricket_stats.db') 

            # Query data from scoreboard tables
            df_series = {}

            # Query batting stats
            try:
                df_series["MOST_RUNS"] = pd.read_sql_query("""
                    SELECT * from cricket_most_runs
                """, conn)
            except:
                df_series["MOST_RUNS"] = pd.DataFrame()

            # Query bowling stats  
            try:
                df_series["MOST_WICKETS"] = pd.read_sql_query("""
                    SELECT * from cricket_most_wickets
                """, conn)
            except:
                df_series["MOST_WICKETS"] = pd.DataFrame()

            # Query bowling stats  
            try:
                df_series["MOST_SIXES"] = pd.read_sql_query("""
                    SELECT * from cricket_most_sixes
                """, conn)
            except:
                df_series["MOST_SIXES"] = pd.DataFrame()
     

            # Print first few extracted tables
            for key, df in df_series.items():
                #print(f"\n=== {key} ===")
                #print(df.head())

                # Merge the dataframes
                # Get the column name in df based on position (assuming the column to merge on is always in position 0)
                #print(df)

                # break if df is empty
                if df.empty:
                    break

                
                merge_column = df.columns[0] if len(df.columns) > 0 else None    
                print("merge_column :", merge_column)            

                
                merged_df = pd.merge(players_df[['Team Name', 'Player Name']], df, left_on="Player Name", right_on=merge_column, how='right')  
                #print(merged_df.head())
                df_series[key] = merged_df

            # Get individual series stats
            


            # Query data from scoreboard tables
            df_scoreboard = {}

            # Query batting stats
            df_scoreboard["Bat"] = pd.read_sql_query("""
                SELECT * from cricket_bat where Runs > 50
            """, conn)

            # Query bowling stats  
            df_scoreboard["Bowl"] = pd.read_sql_query("""
                SELECT * from cricket_bowl
            """, conn)

            # Query fielding stats
            df_scoreboard["Field"] = pd.read_sql_query("""
                SELECT * from cricket_field
            """, conn)

             # Query potm stats
            df_scoreboard["POTM"] = pd.read_sql_query("""
                SELECT * from cricket_potm
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

                #edit_dataframe_values(df, "Philip Salt", "Phil Salt")

                edit_dataframe_values(df, "Ajinkya Rahane (c)", "Ajinkya Rahane")

                edit_dataframe_values(df, "Rasikh Dar Salam", "Rasikh Salam")

                replace_player_name(df, Player)

                merged_df = pd.merge(players_df[['Team Name', 'Player Name', 'first_match_id']], df, left_on="Player Name", right_on=merge_column, how='right')  
            
                # Filter out players who joined after the match
                print(merged_df)

                #check if mattchId col exists in merged_df
                if 'matchId' in merged_df.columns:

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
                    #print(merged_df)
                    team_counts = merged_df.groupby('Team Name').size().reset_index(name='Player Count')
                    team_counts = team_counts.sort_values('Player Count', ascending=False)
                    team_counts.index = range(1, len(team_counts) + 1)     
                    df_scoreboard[key] = team_counts           
                
                print(df_scoreboard[key])                               
                
                                            
            # Generate HTML report
            generate_html_report(team_points_df, player_team_points_df, df_series, df_scoreboard, best_11_df, player_of_the_day, team_of_the_day, league, live_players_list, all_team_points)
            
            logging.info("Data transformation and HTML generation complete.")
            
        except Exception as e:
            logging.error(f"An error occurred during data processing: {str(e)}")
            traceback.print_exception(type(e), e, e.__traceback__)
    else:
        logging.error("Data processing aborted due to previous errors.")

if __name__ == "__main__":
    main()