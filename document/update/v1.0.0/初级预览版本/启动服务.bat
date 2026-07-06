@echo off
cd /d "%~dp0"
echo Starting HTTP server...
echo Open browser: http://127.0.0.1:8890/3D编辑器原型.html
python -m http.server 8890 --bind 127.0.0.1
pause
