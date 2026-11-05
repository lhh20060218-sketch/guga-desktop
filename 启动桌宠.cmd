@echo off
chcp 65001 >nul
title 咕嘎管家桌宠
cd /d D:\rengongzhineng\heimao-zhuochong
C:\Users\l\AppData\Local\Programs\Python\Python312\python.exe main.py
if errorlevel 1 pause
