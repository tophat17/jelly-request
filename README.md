Jelly Request
A Dockerized Python script that scrapes IMDb's Most Popular Movies chart and automatically requests them in Jellyseerr, keeping your media library up-to-date with trending content.
What It Does
"Jelly Request" solves the problem of manually curating your media library by automating the discovery and request process. It fetches trending movies from IMDb and integrates with Jellyseerr to request only those not already in your library, saving you time and effort.
How It Works

Scraping: Uses Python to scrape movie titles from IMDb’s Most Popular Movies chart (https://www.imdb.com/chart/moviemeter).
Integration: Queries your Jellyseerr instance via its API to check for existing movies and submits requests for missing ones.
Scheduling: Runs on a configurable interval (e.g., weekly) inside a Docker container.
Logging: Outputs detailed logs for monitoring and debugging.

Features

Automated IMDb scraping and Jellyseerr requests.
Configurable movie limits and run intervals.
Simple and verbose logging modes.
Runs in Docker for easy deployment on Unraid.

Setup

Prerequisites:

A running Jellyseerr instance.
Docker and Docker Compose are installed on your Unraid server.


Clone the Repository:
git clone https://github.com/tophat17/jelly-request.git
cd jelly-request


Configure Environment Variables: Edit docker-compose.yml to set:

JELLYSEERR_URL: Your Jellyseerr instance URL (e.g., http://192.168.0.29:5054).
API_KEY: Your Jellyseerr API key (found in Jellyseerr settings).
MOVIE_LIMIT: Number of movies to scrape (default: 50).
RUN_INTERVAL_DAYS: Interval between runs in days (default: 7).
DEBUG_MODE: Logging mode (SIMPLE or VERBOSE).


Deploy the Container:
docker-compose up -d --build


View Logs:
docker logs jelly-request



Configuration Options

JELLYSEERR_URL: URL of your Jellyseerr instance.
API_KEY: Jellyseerr API key.
IMDB_URL: IMDb chart URL (default: https://www.imdb.com/chart/moviemeter).
MOVIE_LIMIT: Number of movies to scrape (default: 50).
RUN_INTERVAL_DAYS: Interval between runs in days (default: 7).
DEBUG_MODE: Logging mode (SIMPLE for minimal logs, VERBOSE for detailed logs).

Troubleshooting

Logs: Check /mnt/user/appdata/jelly-request/logs/imdb_jellyseerr.log for details.
API Issues: Verify that your Jellyseerr URL and API key are correct.
IMDb Scraping: Ensure the IMDb URL is accessible and unchanged.

Contributing
Contributions are welcome! Please open an issue or submit a pull request on GitHub.
License
This project is licensed under the MIT License.
