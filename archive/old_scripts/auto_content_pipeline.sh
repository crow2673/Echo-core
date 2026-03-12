#!/bin/bash
echo "Starting automated content generation pipeline..."

# Step 1: Run the content bot to generate drafts from topics
cd ~/content_bot
echo "Generating new drafts from topics.txt..."
~/Echo/run_content_bot.sh

# Step 2: Run the refinement script to polish drafts
echo "Refining drafts..."
python3 ~/content_bot/refine_content.py

# Step 3: Notify the user that refined drafts are ready
notify-send "Content Pipeline" "Drafts and refined drafts are ready for review in ~/content_bot/refined_drafts"

echo "Pipeline complete. Check the refined drafts."
