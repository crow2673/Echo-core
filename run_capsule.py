#!/usr/bin/env python3
import argparse
from core.executor import execute_capsule

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True, help="capsule_id to run (exact match)")
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    print(execute_capsule(args.id, timeout_per_step=args.timeout))

if __name__ == "__main__":
    main()
