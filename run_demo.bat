@echo off
cls
echo ==========================================
echo SOMA CLI — Demo Auto-Run Script
echo.
echo 1. Position your recording window over this terminal.
echo 2. Start recording.
echo 3. Press any key here to begin the demo.
echo ==========================================
pause >nul

cls
echo ^> soma init --base .
call soma init --base .
timeout /t 4 >nul

echo.
echo ^> soma status
call soma status
timeout /t 4 >nul

echo.
echo ^> soma status soma-v1-setup
call soma status soma-v1-setup
timeout /t 4 >nul

echo.
echo ^> soma context soma-v1-setup
call soma context soma-v1-setup
timeout /t 5 >nul

echo.
echo ^> soma agent init soma-v1-setup --print
call soma agent init soma-v1-setup --print
echo.
echo ==========================================
echo Demo complete! You can stop recording now.
echo ==========================================
pause
