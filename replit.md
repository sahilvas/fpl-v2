# CricBattle - Cricket Fantasy League Stats

## Overview
CricBattle is a Flask-based web application for cricket fantasy league statistics, player tracking, predictions, and leaderboard management. It supports multiple fantasy leagues (FPL, JAL) and provides real-time scoring updates from cricket matches.

## Project Structure
- `main.py` - Main Flask application entry point with routes, models, and business logic
- `app.py` - Alternative/duplicate Flask application (same functionality)
- `jal_app.py` - JAL league specific functionality
- `update_scores_html.py` - Score update and HTML report generation
- `update_scores_from_scoreboard.py` - External scoreboard data integration
- `update_series_stats.py` - Series statistics updates
- `templates/` - Jinja2 HTML templates for web pages
- `static/` - CSS, images, and static assets
- `backups/` - Database backups

## Tech Stack
- **Backend**: Python 3.11, Flask 3.1
- **Database**: SQLite (cricbattle.db)
- **ORM**: Flask-SQLAlchemy
- **Scheduler**: APScheduler (background tasks)
- **Data Processing**: Pandas, BeautifulSoup
- **Charts**: Plotly

## Running the Application
The application runs on port 5000:
```bash
python main.py
```

## Key Features
- Fantasy team leaderboards (FPL, JAL)
- Player statistics and rankings
- Match predictions with side bets
- Real-time score updates via web scraping
- Admin dashboard for player management
- User authentication and payment tracking

## Configuration
- Debug mode: Enabled in local development
- Database path: `cricbattle.db` (local), `/mnt/sqlite/cricbattle.db` (production)
- Secret key: Set in app configuration

## User Preferences
- None recorded yet

## Recent Changes
- January 2026: Migrated to Replit environment
  - Updated port from 8080 to 5000
  - Fixed Python 3.11 f-string syntax issues
