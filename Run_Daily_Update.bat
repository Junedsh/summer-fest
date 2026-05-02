@echo off
echo =========================================
echo Summer Fest Dashboard - Daily Data Update
echo =========================================
echo.
echo Fetching latest data from Redshift and pushing to GitHub...
call C:\Users\Lenovo\anaconda3\Scripts\activate.bat
python update_data.py
echo.
echo Update complete! You can close this window.
pause
