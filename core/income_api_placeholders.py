"""
API-READY PLACEHOLDERS
---------------------
This module defines standardized hooks for real income sources.
NO real API calls are made here.
All values are simulated and safe.
"""

import time
import random

class IncomeSource:
    def __init__(self, name, resource_cost, skill_required):
        self.name = name
        self.resource_cost = resource_cost  # cpu %, mem %
        self.skill_required = skill_required
        self.last_check = 0

    def available(self):
        """
        Placeholder availability check.
        Later: real API heartbeat / auth check
        """
        return True

    def fetch_income(self):
        """
        Placeholder income fetch.
        Later: real API query
        """
        time.sleep(0.1)
        return round(random.uniform(0.05, 1.5), 3)


# ---- Placeholder Sources ----

class GolemIncome(IncomeSource):
    def __init__(self):
        super().__init__(
            name="golem_compute",
            resource_cost={"cpu": 70, "mem": 40},
            skill_required="compute"
        )

class CryptoMiningIncome(IncomeSource):
    def __init__(self):
        super().__init__(
            name="crypto_mining",
            resource_cost={"cpu": 80, "mem": 30},
            skill_required="crypto"
        )

class MicrotaskIncome(IncomeSource):
    def __init__(self):
        super().__init__(
            name="microtasks",
            resource_cost={"cpu": 10, "mem": 10},
            skill_required=None
        )


def load_income_sources():
    """
    Central registry.
    Echo can dynamically enable/disable sources later.
    """
    return [
        GolemIncome(),
        CryptoMiningIncome(),
        MicrotaskIncome()
    ]
