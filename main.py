"""
Main entry point for Jelly Request application.
Orchestrates the IMDb scraping and Jellyseerr requesting process.
"""

import time
from config import RUN_INTERVAL_DAYS, logger
from imdb_scraper import scrape_imdb_top_movies
from jellyseerr_client import JellyseerrClient

def main():
    """Main application loop."""
    logger.info(f"Starting IMDb to Jellyseerr sync, configured to run every {RUN_INTERVAL_DAYS} day(s)")
    print(f"Configured to run every {RUN_INTERVAL_DAYS} day(s)")
    
    # Initialize Jellyseerr client
    jellyseerr = JellyseerrClient()
    
    while True:
        try:
            print("Scraping IMDb's Top Movies of the Week...")
            top_movies = scrape_imdb_top_movies()
            
            if not top_movies:
                logger.error("No movies found from IMDb")
                print("❌ No movies found.")
            else:
                logger.info(f"Scraped {len(top_movies)} unique movies")
                print(f"\n✅ Top Movies of the Week (Total: {len(top_movies)}):")
                for i, movie in enumerate(top_movies, 1):
                    print(f"{i}. {movie}")

                print("\nRequesting movies in Jellyseerr...")
                process_movies(jellyseerr, top_movies)
                
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            print(f"❌ Unexpected error: {e}")
        finally:
            logger.info(f"Completed run, sleeping for {RUN_INTERVAL_DAYS} day(s)")
            print(f"ℹ️ Completed run, sleeping for {RUN_INTERVAL_DAYS} day(s)")
            time.sleep(RUN_INTERVAL_DAYS * 24 * 60 * 60)  # Sleep for specified days

def process_movies(jellyseerr_client, movies):
    """
    Process a list of movies through Jellyseerr.
    
    Args:
        jellyseerr_client (JellyseerrClient): Initialized Jellyseerr client
        movies (list): List of movie titles to process
    """
    for i, movie in enumerate(movies, 1):
        print(f"\nProcessing '{movie}' ({i}/{len(movies)})...")
        try:
            # Search for the movie in Jellyseerr
            json_data = jellyseerr_client.search_movie(movie)
            if not json_data:
                continue
                
            # Extract movie details from search results
            imdb_id, media_id, tmdb_id = jellyseerr_client.get_movie_details(movie, json_data)
            if not media_id:
                continue
                
            # Make the request in Jellyseerr
            success, msg = jellyseerr_client.make_request(tmdb_id, media_id)
            if not success and "Request for this media already exists" not in msg:
                logger.error(f"Failed to request '{movie}': {msg}")
                print(f"❌ Failed to request '{movie}': {msg}")
                
        except Exception as e:
            logger.error(f"Error processing movie '{movie}': {e}")
            print(f"❌ Error processing movie '{movie}': {e}")
            continue  # Continue to next movie

if __name__ == "__main__":
    main()
