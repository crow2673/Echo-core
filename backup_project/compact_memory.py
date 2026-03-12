import json

memory_file = '~/Echo/echo_memory.json'
output_file = '~/Echo/echo_memory_compact.json'

# Load memory
with open(memory_file.replace('~', '/home/andrew')) as f:
    data = json.load(f)

# Keep latest capsule per ID
latest_capsules = {}
for capsule in data:
    cid = capsule.get('capsule_id', None)
    ts = capsule.get('timestamp', 0)
    if cid:
        if cid not in latest_capsules or ts > latest_capsules[cid].get('timestamp', 0):
            latest_capsules[cid] = capsule
    else:
        # Keep capsules without ID as-is
        latest_capsules[id(capsule)] = capsule

# Save compacted memory
with open(output_file.replace('~', '/home/andrew'), 'w') as f:
    json.dump(list(latest_capsules.values()), f, indent=2)

print(f"Compacted memory saved to {output_file}")
