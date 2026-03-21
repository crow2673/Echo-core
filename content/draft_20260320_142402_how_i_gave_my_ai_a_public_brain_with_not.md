# How I Gave My AI a Public Brain with Notion

If you’ve been following my journey to build Echo, a local, offline-first AI assistant running on Ubuntu with Ollama, you might be curious about how I made my AI’s thoughts accessible in a public, sharable format. Today, I’ll walk you through the process of how I integrated Notion with Echo to ensure my AI writes to a public Notion database every 5 minutes.

## Setting Up the Environment

First, let’s get the basics out of the way. I use Ubuntu 22.04 LTS as my base operating system, and Ollama for running the AI. For this project, I’ll be using Python to handle the Notion integration. Ensure you have Python installed on your system. You can check this by running:

```bash
python3 --version
```

If Python is not installed, you can install it via the terminal with:

```bash
sudo apt install python3
```

## Creating the Notion Integration

### Step 1: Setting Up Notion

1. **Create a Notion Database**: Go to Notion and create a new database where you want Echo’s thoughts to be recorded. Make sure it’s public so anyone can view the content.

2. **Get API Tokens**: Obtain the Notion API tokens. You’ll need a Notion API token from the Notion API. Head over to the Notion API documentation to get started.

### Step 2: Writing the Python Script

Now, let’s write a Python script that will interact with the Notion API and update the database every 5 minutes.

1. **Install Required Libraries**:

```bash
pip install requests
pip install python-dotenv
```

2. **Create a `.env` File**: Store your Notion API token and other secrets in a `.env` file.

```plaintext
NOTION_API_TOKEN=your_api_token_here
DATABASE_ID=your_database_id_here
```

3. **Write the Python Script**:

```python
import requests
import os
from dotenv import load_dotenv
import time

load_dotenv()

NOTION_API_TOKEN = os.getenv('NOTION_API_TOKEN')
DATABASE_ID = os.getenv('DATABASE_ID')

headers = {
    "Authorization": f"Bearer {NOTION_API_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def create_page_in_notion(title, content):
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "Title": {"title": [{"text": {"content": title}}]}
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "text": [{"text": {"content": content}}]
                }
            }
        ]
    }
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload
    )
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")

def main():
    while True:
        try:
            # Assuming you have a function or method that provides Echo's thoughts
            thoughts = "Echo's latest thought goes here"
            title = "Echo's Thought at " + time.strftime("%Y-%m-%d %H:%M:%S")
            create_page_in_notion(title, thoughts)
        except Exception as e:
            print(f"An error occurred: {e}")
        time.sleep(300)  # Sleep for 5 minutes

if __name__ == "__main__":
    main()
```

### Step 3: Automating the Script

To ensure the script runs every 5 minutes, you can use `cron` on your Linux system.

1. **Edit the Crontab**:

```bash
crontab -e
```

2. **Add a Job**:

```plaintext
*/5 * * * * /usr/bin/python3 /path/to/your_script.py
```

This cron job will run your Python script every 5 minutes.

### Step 4: Testing and Debugging

Before you go public, test the setup by running the script manually and checking if the content appears in your Notion database.

## Conclusion

By integrating Notion with Echo, I’ve created a public, sharable brain for my AI. This setup not only ensures transparency but also allows for collaboration and feedback from the community. The process is straightforward, and with the right setup, you can achieve a similar outcome.

If you have any questions or need further assistance, feel free to reach out. Happy coding!