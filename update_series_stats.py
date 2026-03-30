import os
import sqlite3
import requests
import pandas as pd
from bs4 import BeautifulSoup
from time import sleep
import re
import logging

import update_scores_html

# Define the list of Cricbuzz API URLs
CRICBUZZ_SERIES_ID = "9241"  # IPL 2026

cricbuzz_urls = [
    #f"https://www.cricbuzz.com/api/html/series/{CRICBUZZ_SERIES_ID}/highest-score/0/0/0",
    f"https://www.cricbuzz.com/api/html/series/{CRICBUZZ_SERIES_ID}/most-runs/0/0/0",
    #f"https://www.cricbuzz.com/api/html/series/{CRICBUZZ_SERIES_ID}/most-hundreds/0/0/0",
    #f"https://www.cricbuzz.com/api/html/series/{CRICBUZZ_SERIES_ID}/most-fifties/0/0/0",
    f"https://www.cricbuzz.com/api/html/series/{CRICBUZZ_SERIES_ID}/most-sixes/0/0/0",
    f"https://www.cricbuzz.com/api/html/series/{CRICBUZZ_SERIES_ID}/most-wickets/0/0/0",
    #f"https://www.cricbuzz.com/api/html/series/{CRICBUZZ_SERIES_ID}/most-five-wickets/0/0/0"
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def extract_keyword(url):
    match = re.search(r'/series/\d+/([^/]+)/', url)
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
_cb_session = None

def _get_cb_session():
    """Return a requests Session pre-warmed with a visit to Cricbuzz homepage."""
    global _cb_session
    if _cb_session is None:
        _cb_session = requests.Session()
        _cb_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })
        try:
            _cb_session.get("https://www.cricbuzz.com/", timeout=10)
        except Exception:
            pass
    return _cb_session


def fetch_data(url):
    session = _get_cb_session()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": f"https://www.cricbuzz.com/cricket-series/{CRICBUZZ_SERIES_ID}/indian-premier-league-2026/stats",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Dest": "document",
    }
    try:
        response = session.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        body = response.text.strip()
        if not body:
            logging.warning(f"Empty response from {url}")
            return None
        if "text/html" in content_type or body.startswith("<"):
            return BeautifulSoup(body, "html.parser")
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
    #numeric_columns = df.select_dtypes(include=['int64', 'float64']).columns
    string_columns = df.select_dtypes(include=['object']).columns
    
    #df[numeric_columns] = df[numeric_columns].fillna(0)
    df[string_columns] = df[string_columns].fillna(value="DAN11", inplace=True)
    return df


def main(Player):

    # Create SQLite connection
    conn = sqlite3.connect('/mnt/sqlite/cricket_stats.db' if os.environ.get("WEBSITE_SITE_NAME") else '/mnt/sqlite/cricket_stats.db' if os.environ.get("GOOGLE_CLOUD_PROJECT") else 'instance/cricket_stats.db')  

    
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
        
        if isinstance(data, BeautifulSoup):  # HTML response
            tables = data.find_all("table", class_="cb-series-stats")
            for j, table in enumerate(tables):
                rows = table.find_all("tr")
                headers = [th.get_text(strip=True) for th in rows[0].find_all("th")] if rows else []
                table_data = [[td.get_text(strip=True) for td in row.find_all(["td", "th"])] for row in rows[1:]]
                
                if headers and table_data:
                    dataframes[f"{table_keyword}"] = pd.DataFrame(table_data, columns=headers)
                    #dataframes[f"{table_keyword}"] = replace_nan_values(dataframes[f"{table_keyword}"])
                    edit_dataframe_values(dataframes[f"{table_keyword}"], "Varun Chakaravarthy", "Varun Chakravarthy")
                    #edit_dataframe_values(dataframes[f"{table_keyword}"], "Duckett", "Ben Duckett")
                    edit_dataframe_values(dataframes[f"{table_keyword}"], "Philip Salt", "Phil Salt")
                    #update_scores_html.replace_player_name(dataframes[f"{table_keyword}"], Player)
                else:
                    logging.error(f"No data found in table {table_keyword} of {url}")

            if len(tables) == 0:
                logging.error(f"No tables found in {url}")
            
        else:
            logging.error(f"Unexpected response format or no data found from {url}")

        sleep(1)  # Avoid hitting API rate limits

     # Store final dataframes in SQLite
    for key, df in dataframes.items():
        #drop first column
        df = df.drop(df.columns[0], axis=1)
        
        table_name = f'cricket_{key.lower()}'
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        logging.info(f"Stored {key} data in table: {table_name}")

    conn.close()
    return dataframes                  
                                                 

if __name__ == "__main__":
    main()

    

