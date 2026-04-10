@echo off
powershell -Command "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd g:/project; python scanner.py' -Verb RunAs"
