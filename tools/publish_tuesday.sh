#!/bin/bash
# Tuesday auto-publish — points at next queued article
cd /home/andrew/Echo
python3 echo_devto_publisher.py --file /home/andrew/Echo/content/pending_review/test_pipeline_001_20260314_184630.md
