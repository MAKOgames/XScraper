TwitterScraper
A script for scraping Twitter (X) profile data using the Playwright library. It collects information about followers, the number of tweets, and individual tweets along with engagement metrics (replies, reposts, likes, views). Results are saved to a JSON file.
Features
Collects general profile statistics (name, handle, followers, tweet count).
Parses tweets with their type (original, retweet, quote, promoted).
Extracts engagement metrics for each tweet (Reply, Repost, Like, Views).
Logs the process to a scraper.log file and the console.
Supports graceful shutdown with Ctrl+C.
Requirements
Python 3.8+
Installed Playwright:
bash
pip install playwright
playwright install
A running Chromium browser with remote debugging enabled:
bash
chromium --remote-debugging-port=9222
or
bash
google-chrome --remote-debugging-port=9222
Installation
Clone the repository or download the script:
bash
git clone <repository_URL>
cd <repository_folder>
Install dependencies:
bash
pip install playwright
playwright install
Launch Chromium with the remote debugging port enabled and open the Twitter profile page you want to scrape (e.g., https://twitter.com/username):
bash
chromium --remote-debugging-port=9222
Usage
Start Chromium with the --remote-debugging-port=9222 parameter and open the Twitter profile page you wish to scrape (e.g., https://twitter.com/username) in advance.
Ensure the browser is running with the specified port and the page is loaded.
Run the script:
bash
python twitter_scraper.py
The script will connect to the browser, scrape data from the open page, and save the results to a JSON file named in the format twitter_data_YYYY-MM-DD_HH-MM-SS.json.
Example Output
File twitter_data_2025-02-24_12-00-00.json:
json
{
    "Account Name": "User Name",
    "Handle": "@username",
    "Followers": 12300,
    "Tweet Count": 456,
    "Posts": [
        {
            "id": "123456789",
            "Post Type": "Original Post",
            "Text": "Hello, world!",
            "Date": "2025-02-23T10:00:00.000Z",
            "Engagement": {
                "Reply": 5,
                "Repost": 10,
                "Like": 50,
                "Views": 1000
            }
        }
    ]
}
Logging
Logs are written to the scraper.log file and displayed in the console.
Logging level: INFO.
Errors and warnings are also recorded for debugging purposes.
Notes
The script relies on the Twitter page structure as of February 2025. Changes to the interface may require selector updates.
An active Twitter profile tab must be open in the browser beforehand.
If tweets fail to load, check your internet connection or Twitter authorization.
Limitations
Does not support automatic login (manual authorization is required).
Scrapes only data visible on the page (e.g., no access to hidden tweets).
Does not use web search or APIs, relying solely on the open page.
Troubleshooting
Browser connection error: Ensure Chromium is running with --remote-debugging-port=9222 and the Twitter profile page is open in advance.
Tweets not parsing: Check the selectors in the get_tweet_elements() method—they may have changed.
Empty JSON: Verify the page is fully loaded before running the script.
License
MIT License. Use at your own risk.
Author
Script author: MAKO.
README compiled by Grok 3 from xAI.