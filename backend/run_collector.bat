@echo off
title SafeTravel LK - Continuous Data Collector
echo Starting SafeTravel LK Continuous Data Collector...
echo Project: Sri Lanka Tourist Police Intelligence Engine
echo.
cd /d %~dp0
python data_pipeline\continuous_runner.py
pause
