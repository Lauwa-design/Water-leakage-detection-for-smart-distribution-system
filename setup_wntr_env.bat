@echo off
echo Creating WNTR environment for hydraulic simulation...
echo.

:: Create new conda environment with Python 3.10
call conda create -n thiwasco-wntr python=3.10 -y

:: Activate environment
call conda activate thiwasco-wntr

:: Install WNTR and dependencies (numpy 2.x compatible)
pip install wntr pandas numpy

echo.
echo =========================================
echo WNTR Environment Setup Complete!
echo =========================================
echo.
echo To use:
echo   conda activate thiwasco-wntr
echo   python src/generate_scenarios.py
echo.
echo Then copy data/raw/simulated_leaks.csv to main environment
echo.
pause
