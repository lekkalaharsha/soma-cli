@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8

:: Automatically detect and prepend Python Scripts paths to PATH in case they are not in the environment
for /f "usebackq tokens=*" %%i in (`python -c "import sys, os; print(os.path.join(sys.prefix, 'Scripts'))" 2^>nul`) do set "SYS_SCRIPTS=%%i"
for /f "usebackq tokens=*" %%i in (`python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))" 2^>nul`) do set "USER_SCRIPTS=%%i"
set "PATH=!SYS_SCRIPTS!;!USER_SCRIPTS!;!PATH!"

echo ==========================================
echo Starting SOMA CLI Brute Force Test Suite
echo ==========================================
echo.

echo [1/4] Uninstalling existing soma-cli...
call pip uninstall -y soma-cli >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [WARNING] Uninstall failed or not installed. Continuing...
) else (
    echo [PASS] Uninstalled successfully.
)
echo.

echo [2/4] Installing soma-cli fresh in editable mode with all extras...
call pip install -e .[all]
if !ERRORLEVEL! neq 0 (
    echo [FAIL] Installation failed! Exiting.
    exit /b 1
)
echo [PASS] Installed successfully.
echo.

echo [3/4] Running brute-force command tests...
echo.

set "FAILED_COMMANDS="
set /a PASSED_COUNT=0
set /a FAILED_COUNT=0

:: Helper macro to run a command and check status
goto :start_tests

:run_test
set "CMD=%~1"
echo Testing: !CMD!
call !CMD! > "%TEMP%\soma_test_out.log" 2>&1
if not errorlevel 1 (
    echo   [PASS]
    set /a PASSED_COUNT+=1
) else (
    echo   [FAIL] Exit Code: !ERRORLEVEL!
    if exist "%TEMP%\soma_test_out.log" (
        type "%TEMP%\soma_test_out.log"
        echo.
    )
    set "FAILED_COMMANDS=!FAILED_COMMANDS! [!CMD!]"
    set /a FAILED_COUNT+=1
)
exit /b 0

:start_tests
call :run_test "soma --help"
call :run_test "soma --version"
call :run_test "soma init --base ."
call :run_test "soma status"
call :run_test "soma status soma-v1-setup"
call :run_test "soma status soma-v1-setup --json"
call :run_test "soma history --days 5"
call :run_test "soma history --markdown"
call :run_test "soma context soma-v1-setup"
call :run_test "soma context soma-v1-setup --format json"
call :run_test "soma validate soma-v1-setup"
call :run_test "soma config list"
call :run_test "soma config get dormant_days"
call :run_test "soma config set dormant_days 30"
call :run_test "soma config reset dormant_days"
call :run_test "soma note soma-v1-setup TestNote"
call :run_test "soma note soma-v1-setup --list"
call :run_test "soma note soma-v1-setup --clear"
call :run_test "soma tag soma-v1-setup test-tag"
call :run_test "soma tag soma-v1-setup --list"
call :run_test "soma tag soma-v1-setup --remove test-tag"
call :run_test "soma briefing"
call :run_test "soma doctor"
call :run_test "soma activity --days 14"
call :run_test "soma drift soma-v1-setup"
call :run_test "soma predict soma-v1-setup soma/cli.py"
call :run_test "soma verify soma-v1-setup commit"
call :run_test "soma why soma-v1-setup soma/cli.py"
call :run_test "soma team soma-v1-setup"
call :run_test "soma agent init soma-v1-setup --print"
call :run_test "soma agent sync soma-v1-setup"

echo.
echo ==========================================
echo [4/4] Uninstalling soma-cli at end of tests...
call pip uninstall -y soma-cli >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [FAIL] Final uninstallation failed!
) else (
    echo [PASS] Final uninstallation successful.
)
echo.

echo ==========================================
echo               TEST SUMMARY
echo ==========================================
echo Passed Commands: !PASSED_COUNT!
echo Failed Commands: !FAILED_COUNT!
if !FAILED_COUNT! gtr 0 (
    echo Failed list: !FAILED_COMMANDS!
    exit /b 1
) else (
    echo [SUCCESS] All commands passed brute-force validation!
    exit /b 0
)
