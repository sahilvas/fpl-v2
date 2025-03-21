import requests
import pandas as pd
from bs4 import BeautifulSoup
from time import sleep
import re
import logging

# Define the list of Cricbuzz API URLs
cricbuzz_urls = [
    #"https://www.cricbuzz.com/api/html/series/9325/highest-score/0/0/0",
    "https://www.cricbuzz.com/api/html/series/9325/most-runs/0/0/0",
    #"https://www.cricbuzz.com/api/html/series/9325/most-hundreds/0/0/0", 
    #"https://www.cricbuzz.com/api/html/series/9325/most-fifties/0/0/0",
    #"https://www.cricbuzz.com/api/html/series/9325/most-sixes/0/0/0",
    "https://www.cricbuzz.com/api/html/series/9325/most-wickets/0/0/0",
    #"https://www.cricbuzz.com/api/html/series/9325/most-five-wickets/0/0/0"    
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
def fetch_data(url):
    # Define request headers (modify if needed)
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/html",
    }

    try:
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
    #numeric_columns = df.select_dtypes(include=['int64', 'float64']).columns
    string_columns = df.select_dtypes(include=['object']).columns
    
    #df[numeric_columns] = df[numeric_columns].fillna(0)
    df[string_columns] = df[string_columns].fillna(value="DAN11", inplace=True)
    return df


def main():
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
                    edit_dataframe_values(dataframes[f"{table_keyword}"], "Salman Agha", "Agha Salman")
                    edit_dataframe_values(dataframes[f"{table_keyword}"], "Shaheen Afridi", "Shaheen Shah Afridi")
                    edit_dataframe_values(dataframes[f"{table_keyword}"], "William ORourke", "William O’Rourke")
                    edit_dataframe_values(dataframes[f"{table_keyword}"], "Varun Chakaravarthy", "Varun Chakravarthy")
                    #edit_dataframe_values(dataframes[f"{table_keyword}"], "Duckett", "Ben Duckett")

        sleep(1)  # Avoid hitting API rate limits

    return dataframes                    
                                                 

if __name__ == "__main__":
    main()

    

