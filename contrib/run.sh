#!/bin/bash

# This script runs the live games API in production

cd /app/live-games
. ./venv/bin/activate
python3 lobbylist.py
