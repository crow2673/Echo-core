import json
import requests  # for web API calls, optional if using local files or SDK

def get_live_income():
    """
    Return a dict of current tasks with their reward values.
    Example:
    {
        "task_1": 15.0,
        "task_2": 5.0,
        "crypto_mining_job": 0.2
    }
    """
    income_dict = {}

    # Example: Aether/Outlier API integration
    try:
        # Replace URL with your platform endpoint
        # resp = requests.get("https://api.aetherplatform.com/tasks?user=your_id")
        # tasks = resp.json()
        # for t in tasks:
        #     income_dict[t["name"]] = t["reward"]
        
        # Placeholder for testing
        income_dict = {
            "test_task_1": 15.0,
            "test_task_2": 7.5,
            "gather_water": 2.0,
            "new_unknown": 0.0
        }

    except Exception as e:
        print(f"Error fetching live income: {e}")

    return income_dict
