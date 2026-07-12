@echo off
powershell -Command "Start-Process pythonw -ArgumentList 'scanner.py' -WorkingDirectory '%~dp0' -Verb RunAs -WindowStyle Hidden"
