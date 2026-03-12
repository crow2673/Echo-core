import subprocess
import time
import datetime

def get_cpu_temp():
    """Retrieve CPU temperature using sensors command."""
    try:
        result = subprocess.run(['sensors'], capture_output=True, text=True, check=True)
        for line in result.stdout.split('\n'):
            if 'Core' in line and '°C' in line:
                temp_str = line.split('+')[-1].split('°')[0]
                return float(temp_str)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching CPU temperature: {e}")
        return None

def log_temperature(temp):
    """Log the current temperature with a WARNING prefix if above 80C."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"{timestamp} - CPU Temp: {temp:.2f}°C"
    if temp > 80:
        log_message = "WARNING: " + log_message
    with open('logs/cpu_temp.log', 'a') as log_file:
        log_file.write(log_message + '\n')

def monitor_cpu_temp():
    """Monitor CPU temperature every 5 minutes and log readings."""
    while True:
        temp = get_cpu_temp()
        if temp is not None:
            log_temperature(temp)
        time.sleep(300)  # Sleep for 5 minutes

if __name__ == "__main__":
    monitor_cpu_temp()