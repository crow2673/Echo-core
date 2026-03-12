import subprocess
print("Restarting Golem for fresh offers...")
subprocess.run(["systemctl", "--user", "restart", "golem-provider.service"])
print(subprocess.getoutput("journalctl --user -u golem-provider -n5 | grep Subscribed"))
print("Uptime tip: nohup ya-provider run --subnet open &")  # Alt subnet
