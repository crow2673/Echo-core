#!/bin/bash
BALANCE=$(yagna payment status | grep -o '1000\.0000 tGLM\|[0-9.]\+ tGLM' | head -1 || echo "0 tGLM")
echo "$(date),$BALANCE" >> ~/Echo/memory/glm_balance.csv
echo "GLM: $BALANCE"
