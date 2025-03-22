import requests
import pandas as pd
from bs4 import BeautifulSoup
from time import sleep
import re
import logging
from collections import Counter
import sqlite3


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

#create array of cricbuzz_urls using matchId from table matches
def create_cricbuzz_urls(matches):
    cricbuzz_urls = []
    for _, match in matches.iterrows():
        # check if match date is todays date
        match_date = match['date'].split(",")[0]
        today = pd.Timestamp('today').strftime('%b %d')  
        #tomorrow = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime('%b %d')                
        logging.info(f"Match date: {match_date} and todays date: {today}")
        if match_date == today:
            cricbuzz_urls.append(f"https://www.cricbuzz.com/api/html/cricket-scorecard/{match.matchId}")
            logging.info(f"Fetching: {match.matchId}")
        
        elif match_date.split(" ")[0] == today.split(" ")[0] and match_date.split(" ")[1] <= today.split(" ")[1]:
            cricbuzz_urls.append(f"https://www.cricbuzz.com/api/html/cricket-scorecard/{match.matchId}")
            logging.info(f"Fetching: {match.matchId}")
            
        else:
            logging.info(f"Skipping: {match.matchId}")
            continue
            
            

        

    return cricbuzz_urls

def extract_keyword(url):
    match = re.search(r'(\d+)$', url)
    return match.group(1) if match else None

def read_excel_file(filename):  
    try:  
        return pd.read_excel(filename)  
    except FileNotFoundError:  
        logging.error(f"Error: The file '{filename}' was not found.")  
    except Exception as e:  
        logging.error(f"An error occurred while reading '{filename}': {e}")  
    return None  

# Function to fetch data from API
def fetch_data(url):
    # Define request headers (modify if needed)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/html",
    }

    try:
        sleep(3)
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            soup = BeautifulSoup(response.text, "html.parser")
            return soup
        else:
            return None
    except requests.RequestException as e:
        logging.error(f"Error fetching {url}: {e}")
        
def edit_dataframe_values(df, search_str, replace_str):
    # Replace values in all string columns of the dataframe
    for column in df.select_dtypes(include=['object']).columns:
        df[column] = df[column].str.replace(search_str, replace_str, regex=False)
    return df

def replace_nan_values(df):
    # Replace NaN values with 0 for numeric columns and empty string for string columns
    string_columns = df.select_dtypes(include=['object']).columns
    df[string_columns] = df[string_columns].fillna(value="DAN11", inplace=True)
    return df

# Function to extract batting data  
def extract_batting_data(innings_id, soup, matchId):  
    innings_data = []  
    try:
        innings_table = soup.find('div', id=innings_id).find_all('div', class_='cb-col cb-col-100 cb-scrd-itms')  
        for row in innings_table:  
            cells = row.find_all('div', recursive=False)  
            if len(cells) >= 7:  # Ensure there's enough data  
                player = cells[0].get_text(strip=True)  
                dismissal = cells[1].get_text(strip=True)  
                runs = cells[2].get_text(strip=True)  
                balls = cells[3].get_text(strip=True)  
                fours = cells[4].get_text(strip=True)  
                sixes = cells[5].get_text(strip=True)  
                strike_rate = cells[6].get_text(strip=True)  
                innings_data.append([player, dismissal, runs, balls, fours, sixes, strike_rate, matchId])  
    except AttributeError as e:
        logging.error(f"Error extracting batting data: {e}")
    finally:
        logging.info(f"Extracted batting data for {innings_id}")
        return innings_data 
  
# Function to extract bowling data  
def extract_bowling_data(innings_id, soup, matchId):  
    bowling_data = []  
    try:
        bowling_table = soup.find('div',id=innings_id).find_all('div', class_='cb-ltst-wgt-hdr')[1].find_all('div', class_='cb-col cb-col-100 cb-scrd-itms')  
        for row in bowling_table:  
            cells = row.find_all('div', recursive=False)  
            if len(cells) >= 8:  # Ensure there's enough data  
                bowler = cells[0].get_text(strip=True)  
                overs = cells[1].get_text(strip=True)  
                maidens = cells[2].get_text(strip=True)  
                runs_conceded = cells[3].get_text(strip=True)  
                wickets = cells[4].get_text(strip=True)  
                no_balls = cells[5].get_text(strip=True)  
                wides = cells[6].get_text(strip=True)  
                economy = cells[7].get_text(strip=True)  
                
                bowling_data.append([bowler, overs, maidens, runs_conceded, wickets, no_balls, wides, economy, matchId])  
    except AttributeError as e:
        logging.error(f"Error extracting batting data: {e}")
    finally:
        logging.info(f"Extracted batting data for {innings_id}")
        return bowling_data 
  
# Function to extract catchers from the Dismissal column
def extract_catchers(dismissals):
    catchers = []
    for dismissal in dismissals:
        match = re.search(r'c ([A-Za-z ]+) b', dismissal)  # Extract player after "c 
        if match and match.group(1) == "and":
            candbcatcher = re.search(r'c and b ([A-Za-z ]+$)', dismissal) 
            catcher = candbcatcher.group(1).strip()
            catchers.append(catcher)
        elif match:
            catcher = match.group(1).strip()
            catchers.append(catcher)
        
    return catchers

def main(Match):
    # Query macthes table and save as dataframe
    matches_df = pd.DataFrame([{
        'id': p.id,
        'matchId': p.matchId, 
        'match_info': p.match_info,
        'date': p.date,
        'time': p.time

        } for p in Match.query.all()])
    
    print(matches_df)
    
    cricbuzz_urls = create_cricbuzz_urls(matches_df)
    logging.info(f"Number of URLs: {len(cricbuzz_urls)}")

    # Create SQLite connection
    conn = sqlite3.connect('cricket_stats.db')
    
    # Process each API URL
    dataframes = {}
    for i, url in enumerate(cricbuzz_urls):
        logging.info(f"Fetching: {url}")
        table_keyword = extract_keyword(url)
        if not table_keyword:
            logging.error(f"Could not extract keyword from URL: {url}")
            continue
        table_keyword = table_keyword.replace("-", "_").upper()
        logging.info(f"Keyword: {table_keyword}")

        data = fetch_data(url)

        if isinstance(data, BeautifulSoup):
            # Extract data  
            first_batting = extract_batting_data('innings_1', data, table_keyword)  
            second_batting = extract_batting_data('innings_2', data, table_keyword)  
            
            first_bowling = extract_bowling_data('innings_1', data, table_keyword)  
            second_bowling = extract_bowling_data('innings_2', data, table_keyword)  
            
            # Create DataFrames  
            batting_cols = ['Player', 'Dismissal', 'Runs', 'Balls', '4s', '6s', 'SR', 'matchId']
            bowling_cols = ['Bowler', 'Overs', 'Maidens', 'Runs', 'Wickets', 'No Balls', 'Wides', 'Economy', 'matchId']
            batting_1 = pd.DataFrame(first_batting, columns=batting_cols)  
            batting_2 = pd.DataFrame(second_batting, columns=batting_cols)  
            
            bowling_1 = pd.DataFrame(first_bowling, columns=bowling_cols)  
            bowling_2 = pd.DataFrame(second_bowling, columns=bowling_cols)  

            # Filter data
            batting_1_filtered = batting_1[pd.to_numeric(batting_1['Runs'], errors='coerce') >= 50]            
            batting_2_filtered = batting_2[pd.to_numeric(batting_2['Runs'], errors='coerce') >= 50]

            bowling_1_filtered = bowling_1[pd.to_numeric(bowling_1['Wickets'], errors='coerce') >= 3] 
            bowling_2_filtered = bowling_2[pd.to_numeric(bowling_2['Wickets'], errors='coerce') >= 3]

            # Extract catches
            catchers_list_1 = extract_catchers(batting_1['Dismissal'])
            catchers_list_2 = extract_catchers(batting_2['Dismissal'])
            catchers_list = catchers_list_1 + catchers_list_2
            catch_stats = Counter(catchers_list)
            catchers_df = pd.DataFrame(catch_stats.items(), columns=['Player', 'Catches'])

            # Store in dataframes dict
            if "Bat" in dataframes:
                dataframes["Bat"] = pd.concat([dataframes["Bat"], batting_1_filtered, batting_2_filtered])
            else:
                dataframes["Bat"] = pd.concat([batting_1_filtered, batting_2_filtered])

            if "Bowl" in dataframes:
                dataframes["Bowl"] = pd.concat([dataframes["Bowl"], bowling_1_filtered, bowling_2_filtered]) 
            else:
                dataframes["Bowl"] = pd.concat([bowling_1_filtered, bowling_2_filtered])            
                
            if "Field" in dataframes:
                dataframes["Field"] = pd.concat([dataframes["Field"], catchers_df]).groupby('Player')['Catches'].sum().reset_index()   
                dataframes["Field"]['matchId'] = table_keyword
            else:
                dataframes["Field"] = catchers_df

        sleep(1)

    # Store final dataframes in SQLite
    for key, df in dataframes.items():
        table_name = f'cricket_{key.lower()}'
        print(df)
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        logging.info(f"Stored {key} data in table: {table_name}")

    conn.close()
    return dataframes

if __name__ == "__main__":
    main()

    

