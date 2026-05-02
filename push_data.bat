@echo off
echo =========================================
echo Summer Fest - Push data.csv to GitHub
echo =========================================
echo.
echo Pushing data.csv to GitHub...
cd /d "%~dp0"
git add data.csv
git diff --cached --quiet && (
    echo No changes in data.csv. Nothing to push.
) || (
    git commit -m "Manual data refresh - %date% %time%"
    git push origin main
    echo.
    echo Done! Streamlit Cloud will update shortly.
)
echo.
pause
