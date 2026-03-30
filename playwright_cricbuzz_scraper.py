import os
import re
import json
import sqlite3
import logging
import subprocess
import pandas as pd
from bs4 import BeautifulSoup
from collections import Counter
from datetime import datetime
from time import sleep

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CRICBUZZ_SERIES_ID = 9241
DB_PATH = 'instance/cricket_stats.db'

_KNOWN_LIB_PATHS = [
    '/nix/store/cpwib3zazj49fm0y04y53w4xkbqsgrgm-mesa-25.0.7/lib',
    '/nix/store/wilz94hzz4q3fss6qvv625zvww4a6s4s-mesa-libgbm-25.0.1/lib',
    '/nix/store/1nsvsrqp5zm96r9p3rrq3yhlyw8jiy91-libX11-1.8.12/lib',
    '/nix/store/5flwv7rri80114p8vlz7l8qf8z5i557h-systemd-minimal-libs-257.6/lib',
    '/nix/store/gpb87pb8s826aggy1s3f352alp40dkj8-nspr-4.36/lib',
]

_NIX_ATTRS = [
    'mesa', 'libgbm', 'xorg.libX11', 'systemd-minimal-libs', 'nspr'
]


def _setup_ld_library_path():
    valid = [p for p in _KNOWN_LIB_PATHS if os.path.isdir(p)]
    if len(valid) < len(_KNOWN_LIB_PATHS):
        logging.warning("Some known lib paths missing — rediscovering via nix eval")
        for attr in _NIX_ATTRS:
            try:
                r = subprocess.run(
                    ['nix', 'eval', '--raw', f'nixpkgs#{attr}.outPath'],
                    capture_output=True, text=True, timeout=20
                )
                if r.returncode == 0:
                    p = r.stdout.strip() + '/lib'
                    if p not in valid and os.path.isdir(p):
                        valid.append(p)
            except Exception:
                pass
    existing = os.environ.get('LD_LIBRARY_PATH', '')
    merged = ':'.join(valid) + (':' + existing if existing else '')
    os.environ['LD_LIBRARY_PATH'] = merged
    logging.info(f"LD_LIBRARY_PATH configured with {len(valid)} Nix lib paths")


_setup_ld_library_path()

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


def _open_browser():
    pw = Stealth().use_sync(sync_playwright())
    p = pw.__enter__()
    browser = p.chromium.launch(
        headless=True,
        args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
    )
    ctx = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 720},
        locale='en-US',
    )
    page = ctx.new_page()
    page.goto('https://www.cricbuzz.com/', timeout=20000)
    page.wait_for_timeout(1500)
    return pw, browser, page


def _close_browser(pw, browser):
    try:
        browser.close()
    except Exception:
        pass
    try:
        pw.__exit__(None, None, None)
    except Exception:
        pass


def fetch_series_stats(page):
    """
    Fetch Most Runs, Most Sixes, Most Wickets from the Cricbuzz JSON API.
    Returns a dict {table_name: pd.DataFrame}.
    """
    stats_page = f'https://www.cricbuzz.com/cricket-series/{CRICBUZZ_SERIES_ID}/indian-premier-league-2026/stats'
    logging.info(f"Loading series stats page: {stats_page}")
    page.goto(stats_page, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(3000)

    stat_configs = [
        ('mostRuns',    'MOST_RUNS',    'most-runs'),
        ('mostSixes',   'MOST_SIXES',   'most-sixes'),
        ('mostWickets', 'MOST_WICKETS', 'most-wickets'),
    ]

    results = {}
    for api_key, table_name, _ in stat_configs:
        url = f'https://www.cricbuzz.com/api/cricket-series/series-stats/{CRICBUZZ_SERIES_ID}/{api_key}'
        logging.info(f"Fetching stats: {url}")
        try:
            resp = page.request.get(url)
            if resp.status != 200:
                logging.warning(f"{api_key}: HTTP {resp.status}")
                continue
            data = resp.json()
            stat_list = data.get('t20StatsList') or data.get('odisStatsList') or data.get('testStatsList')
            if not stat_list:
                logging.warning(f"{api_key}: no statsList in response")
                continue
            headers = stat_list.get('headers', [])
            rows = []
            for item in stat_list.get('values', []):
                vals = item.get('values', [])
                if len(vals) > len(headers):
                    vals = vals[1:]
                rows.append(vals)
            if headers and rows:
                max_cols = max(len(r) for r in rows)
                while len(headers) < max_cols:
                    headers.append(f'col{len(headers)}')
                rows = [r + [''] * (len(headers) - len(r)) for r in rows]
                df = pd.DataFrame(rows, columns=headers)
                results[table_name] = df
                logging.info(f"{api_key}: {len(df)} rows")
        except Exception as e:
            logging.error(f"Error fetching {api_key}: {e}")
    return results


def _parse_batting_grid(soup, innings_num, match_id):
    """Parse batting rows from rendered scorecard HTML."""
    rows = []
    bat_grids = soup.find_all('div', class_=lambda c: c and 'scorecard-bat-grid' in ' '.join(c))
    if not bat_grids:
        return rows

    innings_found = 0
    capture = False
    for grid in bat_grids:
        text_cells = [t.strip() for t in grid.get_text('|', strip=True).split('|') if t.strip()]
        if not text_cells:
            continue
        if innings_num == 1 and innings_found == 0:
            capture = True
            innings_found += 1
        elif innings_num == 2 and innings_found == 1:
            capture = True
        elif innings_num == 1 and innings_found >= 1:
            capture = False
        if capture and len(text_cells) >= 4:
            player = text_cells[0]
            if re.match(r'^[A-Z]', player) and not any(k in player for k in ['BATTING', 'PLAYER', 'Fall', 'Extras', 'Total', 'Yet']):
                dismissal = text_cells[1] if len(text_cells) > 1 else ''
                runs  = text_cells[2] if len(text_cells) > 2 else '0'
                balls = text_cells[3] if len(text_cells) > 3 else '0'
                fours = text_cells[4] if len(text_cells) > 4 else '0'
                sixes = text_cells[5] if len(text_cells) > 5 else '0'
                sr    = text_cells[6] if len(text_cells) > 6 else '0'
                rows.append([player, dismissal, runs, balls, fours, sixes, sr, match_id])
    return rows


def _parse_scorecard_text(page_text, match_id):
    """
    Fallback: parse batting + bowling from get_text('|') of the scorecard page.
    Returns (batting_rows, bowling_rows, catchers_list, potm).
    """
    batting_rows = []
    bowling_rows = []
    catchers = []
    potm = None

    segments = page_text.split('|')
    segments = [s.strip() for s in segments if s.strip()]

    i = 0
    mode = None  # 'bat' or 'bowl'
    innings = 0

    while i < len(segments):
        seg = segments[i]
        if seg == 'BATTING':
            mode = 'bat'
            innings += 1
            i += 1
            continue
        if seg == 'BOWLING':
            mode = 'bowl'
            i += 1
            continue
        if seg in ('Fall of wickets', 'Extras', 'Total', 'Did not bat'):
            mode = None
            i += 1
            continue
        if seg in ('PLAYER', 'Batter', 'O', 'M', 'R', 'W', 'NB', 'WD', 'ECO'):
            i += 1
            continue

        if mode == 'bat' and re.match(r'^[A-Z][a-z]', seg):
            if i + 6 < len(segments):
                dismissal = segments[i + 1]
                runs  = segments[i + 2]
                balls = segments[i + 3]
                fours = segments[i + 4]
                sixes = segments[i + 5]
                sr    = segments[i + 6]
                if re.match(r'^\d+\.?\d*$', runs.replace('*', '').replace('†', '')):
                    batting_rows.append([seg, dismissal, runs.replace('*','').replace('†',''), balls, fours, sixes, sr, match_id])
                    c = re.search(r'c (\w+ \w+|\w+) b', dismissal)
                    if c:
                        catchers.append(c.group(1))
                    i += 7
                    continue

        if mode == 'bowl' and re.match(r'^[A-Z][a-z]', seg):
            if i + 7 < len(segments):
                overs    = segments[i + 1]
                maidens  = segments[i + 2]
                runs_g   = segments[i + 3]
                wickets  = segments[i + 4]
                no_balls = segments[i + 5]
                wides    = segments[i + 6]
                economy  = segments[i + 7]
                if re.match(r'^\d+\.?\d*$', overs):
                    bowling_rows.append([seg, overs, maidens, runs_g, wickets, no_balls, wides, economy, match_id])
                    i += 8
                    continue

        if 'Player of the Match' in seg or 'Player Of The Match' in seg:
            if i + 1 < len(segments):
                potm = segments[i + 1]
        i += 1

    return batting_rows, bowling_rows, catchers, potm


def _parse_scorecard_grids(soup, match_id):
    """
    Parse batting and bowling from scorecard-bat-grid / scorecard-bowl-grid divs.
    Returns (batting_rows, bowling_rows, catchers, potm).
    """
    bat_cols  = ['Player', 'Dismissal', 'Runs', 'Balls', '4s', '6s', 'SR', 'matchId']
    bowl_cols = ['Bowler', 'Overs', 'Maidens', 'Runs', 'Wickets', 'No Balls', 'Wides', 'Economy', 'matchId']

    batting_rows = []
    bowling_rows = []
    catchers = []
    potm = None

    bat_grids = soup.find_all('div', class_=lambda c: c and 'scorecard-bat-grid' in ' '.join(c))
    for grid in bat_grids:
        cells = [t.strip() for t in grid.get_text('|', strip=True).split('|') if t.strip()]
        if not cells:
            continue
        player = cells[0]
        if not re.match(r'^[A-Z][a-z]', player):
            continue
        skip_words = {'BATTER', 'Batter', 'PLAYER', 'Fall', 'Extras', 'Total', 'Yet', 'Did', 'DNB', 'Absent'}
        if player in skip_words or re.match(r'^\d', player):
            continue
        dismissal = cells[1] if len(cells) > 1 else ''
        runs  = cells[2] if len(cells) > 2 else '0'
        balls = cells[3] if len(cells) > 3 else '0'
        fours = cells[4] if len(cells) > 4 else '0'
        sixes = cells[5] if len(cells) > 5 else '0'
        sr    = cells[6] if len(cells) > 6 else '0'
        if re.match(r'^\d+\.?\d*$', runs.replace('*', '').replace('†', '')):
            batting_rows.append([player, dismissal,
                                  runs.replace('*','').replace('†',''),
                                  balls, fours, sixes, sr, match_id])
            c = re.search(r'c ([A-Z][a-z]+(?: [A-Z][a-z]+)*) b', dismissal)
            if c:
                catchers.append(c.group(1))

    bowl_grids = soup.find_all('div', class_=lambda c: c and 'scorecard-bowl-grid' in ' '.join(c))
    for grid in bowl_grids:
        cells = [t.strip() for t in grid.get_text('|', strip=True).split('|') if t.strip()]
        if not cells:
            continue
        bowler = cells[0]
        if not re.match(r'^[A-Z][a-z]', bowler):
            continue
        skip_words = {'BOWLER', 'Bowler', 'O', 'M', 'R', 'W', 'NB', 'WD', 'ECO'}
        if bowler in skip_words:
            continue
        overs    = cells[1] if len(cells) > 1 else '0'
        maidens  = cells[2] if len(cells) > 2 else '0'
        runs_g   = cells[3] if len(cells) > 3 else '0'
        wickets  = cells[4] if len(cells) > 4 else '0'
        no_balls = cells[5] if len(cells) > 5 else '0'
        wides    = cells[6] if len(cells) > 6 else '0'
        economy  = cells[7] if len(cells) > 7 else '0'
        if re.match(r'^\d+\.?\d*$', overs):
            bowling_rows.append([bowler, overs, maidens, runs_g, wickets, no_balls, wides, economy, match_id])

    full_text = soup.get_text(' ', strip=True)
    for label in ['Player of the Match', 'Player Of The Match', 'PLAYER OF THE MATCH']:
        idx = full_text.find(label)
        if idx != -1:
            snippet = full_text[idx + len(label):idx + len(label) + 60].strip()
            name_match = re.match(r'^[:\-\s]*([A-Z][a-z]+ [A-Z][a-z]+)', snippet)
            if name_match:
                potm = name_match.group(1)
            break

    return batting_rows, bowling_rows, catchers, potm


def fetch_scorecard(page, match_id):
    """Fetch and parse scorecard for a single match."""
    url = f'https://www.cricbuzz.com/live-cricket-scorecard/{match_id}'
    logging.info(f"Loading scorecard: {url}")
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)
        title = page.title()
        if 'Access Denied' in title or not title:
            logging.warning(f"matchId {match_id}: Access denied / empty page")
            return None
        logging.info(f"matchId {match_id}: {title[:60]}")
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')

        bat_grids = soup.find_all('div', class_=lambda c: c and 'scorecard-bat-grid' in ' '.join(c))
        if not bat_grids:
            logging.info(f"matchId {match_id}: no batting grid — match not yet played or no scorecard")
            return None

        batting_rows, bowling_rows, catchers, potm = _parse_scorecard_grids(soup, str(match_id))
        logging.info(f"matchId {match_id}: {len(batting_rows)} batting, {len(bowling_rows)} bowling rows")
        return {
            'batting': batting_rows,
            'bowling': bowling_rows,
            'catchers': catchers,
            'potm': potm,
        }
    except Exception as e:
        logging.error(f"Error fetching scorecard for match {match_id}: {e}")
        return None


def _is_match_past(match_date_str):
    """Check if a match date is today or in the past."""
    try:
        month_day = match_date_str.split(',')[0].strip()
        match_dt = datetime.strptime(month_day + ' 2026', '%b %d %Y')
        return match_dt.date() <= datetime.today().date()
    except Exception:
        return False


def main(Match):
    """
    Main entry point called from main.py scheduler.
    Match: SQLAlchemy model class (has .query).
    """
    matches_df = pd.DataFrame([{
        'id': m.id,
        'matchId': m.matchId,
        'match_info': m.match_info,
        'date': m.date,
        'time': m.time,
    } for m in Match.query.all()])

    if matches_df.empty:
        logging.warning("No matches found in DB")
        return

    past_matches = matches_df[matches_df['date'].apply(_is_match_past)]
    logging.info(f"Total matches: {len(matches_df)}, past/today: {len(past_matches)}")

    conn = sqlite3.connect(DB_PATH)
    pw, browser, page = _open_browser()

    try:
        series_dfs = fetch_series_stats(page)
        for table_name, df in series_dfs.items():
            df.to_sql(table_name, conn, if_exists='replace', index=False)
            logging.info(f"Saved {table_name}: {len(df)} rows")
        conn.commit()

        bat_cols  = ['Player', 'Dismissal', 'Runs', 'Balls', '4s', '6s', 'SR', 'matchId']
        bowl_cols = ['Bowler', 'Overs', 'Maidens', 'Runs', 'Wickets', 'No Balls', 'Wides', 'Economy', 'matchId']
        field_cols = ['Player', 'Catches', 'matchId']
        potm_cols  = ['Player', 'matchId']

        for _, match_row in past_matches.iterrows():
            mid = str(match_row['matchId'])
            result = fetch_scorecard(page, match_row['matchId'])
            if not result:
                continue

            batting_rows = result['batting']
            bowling_rows = result['bowling']
            catchers     = result['catchers']
            potm         = result['potm']

            bat_df = pd.DataFrame(batting_rows, columns=bat_cols)
            bowl_df = pd.DataFrame(bowling_rows, columns=bowl_cols)
            catch_stats = Counter(catchers)
            field_df = pd.DataFrame(catch_stats.items(), columns=['Player', 'Catches'])
            if not field_df.empty:
                field_df['matchId'] = mid
            potm_df = pd.DataFrame({'Player': [potm], 'matchId': [mid]}) if potm else pd.DataFrame(columns=potm_cols)

            for table, df in [('cricket_bat', bat_df), ('cricket_bowl', bowl_df), ('cricket_field', field_df), ('cricket_potm', potm_df)]:
                if df.empty:
                    continue
                try:
                    conn.execute(f"DELETE FROM {table} WHERE matchId = ?", (mid,))
                    conn.commit()
                except Exception:
                    pass
                df.to_sql(table, conn, if_exists='append', index=False)
                logging.info(f"  {table}: {len(df)} rows for match {mid}")

            sleep(2)

        conn.commit()
        logging.info("playwright_cricbuzz_scraper.main() complete")

    except Exception as e:
        logging.error(f"playwright_cricbuzz_scraper error: {e}", exc_info=True)
    finally:
        _close_browser(pw, browser)
        conn.close()


if __name__ == '__main__':
    logging.info("Running playwright_cricbuzz_scraper standalone test")
    _setup_ld_library_path()
    conn = sqlite3.connect(DB_PATH)
    pw, browser, page = _open_browser()
    try:
        series_dfs = fetch_series_stats(page)
        for name, df in series_dfs.items():
            print(f"\n=== {name} ===")
            print(df.to_string(index=False))
        result = fetch_scorecard(page, 149618)
        if result:
            print("\n=== Batting ===")
            for r in result['batting']:
                print(r)
            print("\n=== Bowling ===")
            for r in result['bowling']:
                print(r)
            print("\nPOTM:", result['potm'])
    finally:
        _close_browser(pw, browser)
        conn.close()
