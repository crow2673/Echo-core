#!/usr/bin/env python3
"""
Script to simulate investment growth and risk for various strategies
Provide data-driven insights for decision-making
"""

import logging
from pathlib import Path
import psutil
import random
import sys

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / 'logs' / 'investment_simulation.log'
MEMORY_DIR = BASE / 'memory'

# Setup logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(message)s')

# Import notify function
sys.path.insert(0, str(BASE))
from core.notifier import notify

# Environment variables
env_file = Path.home() / ".config/echo/golem.env"
ENV = {}
for line in env_file.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        ENV[k] = v

# Define investment simulation function
def simulate_investment(initial_investment, growth_rate, risk_factor, years):
    """
    Simulate investment growth and risk over a number of years.

    :param initial_investment: Initial investment amount
    :param growth_rate: Annual growth rate as a percentage
    :param risk_factor: Risk factor as a percentage
    :param years: Number of years to simulate
    :return: Final investment amount after the specified years
    """
    investment = initial_investment
    for _ in range(years):
        growth = investment * (growth_rate / 100)
        risk_adjustment = random.uniform(-risk_factor, risk_factor) / 100
        investment += growth + (investment * risk_adjustment)
    return investment

def main():
    # Check system resources
    cpu_usage = psutil.cpu_percent(interval=2)
    memory_usage = psutil.virtual_memory().percent
    if cpu_usage > 80 or memory_usage > 80:
        notify("High System Load", f"CPU: {cpu_usage}%, Memory: {memory_usage}%")
        logging.warning(f"High system load - CPU: {cpu_usage}%, Memory: {memory_usage}%")
        return

    # Simulation parameters
    initial_investment = float(ENV.get('INITIAL_INVESTMENT', 1000))
    growth_rate = float(ENV.get('GROWTH_RATE', 7))
    risk_factor = float(ENV.get('RISK_FACTOR', 2))
    years = int(ENV.get('YEARS', 10))

    try:
        final_investment = simulate_investment(initial_investment, growth_rate, risk_factor, years)
        result_path = MEMORY_DIR / 'investment_results.txt'
        tmp = result_path.with_suffix('.tmp')
        tmp.write_text(f"Initial Investment: {initial_investment}\nFinal Investment: {final_investment}\nYears: {years}\nGrowth Rate: {growth_rate}%\nRisk Factor: {risk_factor}%")
        tmp.rename(result_path)
        logging.info(f"Investment simulation completed - Initial: {initial_investment}, Final: {final_investment}")
    except Exception as e:
        notify("Simulation Error", str(e), urgent=True)
        logging.error(f"Error in investment simulation: {str(e)}")

if __name__ == "__main__":
    main()