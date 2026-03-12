#!/bin/bash
echo "Running system cleanup..."
sudo apt autoremove -y
sudo apt clean
rm -rf ~/.cache/thumbnails/*
echo "Cleanup complete."
