#!/usr/bin/env python3
import requests
import csv
import os
from datetime import datetime

# Hard-coded Dev.to username
username = "crow"

# Define log file path
log_file = os.path.expanduser("~/Echo/memory/content_log.csv")
os.makedirs(os.path.dirname(log_file), exist_ok=True)

try:
    # Fetch latest articles from Dev.to API
    response = requests.get(f"https://dev.to/api/articles?username={username}")
    
    if response.status_code == 200:
        posts = response.json()

        # Debugging output: show total posts fetched
        print(f"Fetched {len(posts)} posts for user '{username}'.")

        # If no posts, exit gracefully
        if len(posts) == 0:
            print("No posts found for this user.")
            exit(0)

        # Print a sample post structure for debugging
        print(f"Sample first post: {posts[0]}")

        # Open the log file in append mode
        with open(log_file, "a", newline='') as f:
            writer = csv.writer(f)
            
            # Add a header row if the file is empty
            if os.stat(log_file).st_size == 0:
                writer.writerow(["Timestamp", "Title", "Views", "Claps"])  # Header

            # Add a timestamp for this run
            run_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Process and log each post
            logged_any = False  # Track if anything was logged

            for post in posts[:10]:  # Top 10 most recent posts
                title = post.get('title', 'Untitled')
                article_id = post.get('id')

                # Skip if no article ID (very rare)
                if not article_id:
                    print(f"Skipping post with missing ID: {title}")
                    continue
                
                # Fetch detailed article data to get views and claps
                details_endpoint = f"https://dev.to/api/articles/{article_id}"
                details_response = requests.get(details_endpoint)
                
                if details_response.status_code == 200:
                    detailed_post = details_response.json()
                    views = detailed_post.get('page_views_count', 0)
                    claps = detailed_post.get('public_reactions_count', 0)

                    # Log the data
                    writer.writerow([run_date, title, views, claps])
                    logged_any = True

                    # Debug: Show what we logged
                    print(f"Logged: Title: {title}, Views: {views}, Claps: {claps}")

                else:
                    print(f"Warning: Could not fetch details for article {article_id}. Status code: {details_response.status_code}")
                
        if logged_any:
            print(f"Logged top posts to {log_file}!")
        else:
            print(f"No articles logged. Check the API response or data fields.")
        
        # Display top performer for reference (based on views)
        if posts:
            # Find the top performer by fetching details of each post again to get the views
            top_viewed_post = None
            top_views = -1

            for post in posts[:10]:  # Check the top 10 posts again
                article_id = post.get('id')
                details_response = requests.get(f"https://dev.to/api/articles/{article_id}")
                if details_response.status_code == 200:
                    detailed_post = details_response.json()
                    views = detailed_post.get('page_views_count', 0)
                    if views > top_views:
                        top_views = views
                        top_viewed_post = post
            
            if top_viewed_post:
                print(f"Top performer: {top_viewed_post['title']} (Views: {top_views})")
            else:
                print("No top performer identified.")

    else:
        print(f"Error fetching posts: HTTP {response.status_code}")

except Exception as e:
    print(f"Error: {e}")
    exit(1)
