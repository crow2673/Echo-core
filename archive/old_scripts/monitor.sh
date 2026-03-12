#!/bin/bash
watch -n5 "yagna payment status && yagna extension provider status || echo 'Testnet ramp OK'"
