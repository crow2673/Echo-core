import subprocess
import logging
from datetime import datetime

logging.basicConfig(filename='logs/golem_recommendations.log', level=logging.INFO, format='%(asctime)s - %(message)s')

def check_golem_status():
    """
    Check Golem provider status using ya-provider commands,
    identify why tasks=0, and log specific actionable recommendations.
    """
    try:
        # Fetch the current provider status
        result = subprocess.run(['ya-provider', 'status'], capture_output=True, text=True)
        status_output = result.stdout

        if "tasks=0" in status_output:
            logging.info("Current Golem status: No tasks assigned.")
            
            # Check specific reasons for no tasks
            config_result = subprocess.run(['ya-provider', 'config'], capture_output=True, text=True)
            config_output = config_result.stdout
            
            if "reputation" in config_output and "low" in config_output:
                logging.info("Reason: Low reputation. Recommendation: Increase Golem provider reputation through active promotion.")
            elif "price" in config_output and "high" in config_output:
                logging.info("Reason: High price. Recommendation: Decrease price to attract more tasks.")
            else:
                logging.info("Reason: Unknown issue with task assignment. Recommendation: Review Golem configuration and network status.")

        else:
            logging.info(f"Golem provider is active with the following status:\n{status_output}")

    except Exception as e:
        logging.error(f"Failed to check Golem status due to error: {e}")

if __name__ == "__main__":
    check_golem_status()