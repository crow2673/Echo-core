#!/bin/bash
cd ~/Echo
python3 echo_devto_publisher.py --file content/self_heal_article_draft.md >> logs/devto_publish.log 2>&1
