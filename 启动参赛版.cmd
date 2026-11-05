@echo off
chcp 65001 >nul
title 咕嘎管家(参赛版)
cd /d D:\rengongzhineng\heimao-zhuochong
"C:\Users\l\AppData\Local\Programs\Python\Python312\python.exe" comp_main.py
if errorlevel 1 pause
