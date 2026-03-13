#!/bin/bash
cd ~vastai_kaalia
wget -q https://s3.amazonaws.com/public.vast.ai/kaalia/daemons$(cat ~/.channel 2>/dev/null)/update -O install_update.sh

chmod +x install_update.sh

./install_update.sh "$@"