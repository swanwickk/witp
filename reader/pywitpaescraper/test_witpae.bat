@echo off
setlocal

set "DLL_DIR=C:\Matrix Games\War in the Pacific Admiral's Edition"
set "START_OF_DAY_FILE=C:\Matrix Games\War in the Pacific Admiral's Edition\SAVE\wpae002.pws"
set "END_OF_DAY_FILE=C:\Matrix Games\War in the Pacific Admiral's Edition\SAVE\wpae000.pws"
set "PWS_DIR=C:\Matrix Games\War in the Pacific Admiral's Edition\SAVE"
set "JAPAN_OUTPUT_DIR=%PWS_DIR%\JAPAN"
set "ALLIED_OUTPUT_DIR=%PWS_DIR%\ALLIED"
set "JAPAN_EXIT_CODE=0"
set "US_EXIT_CODE=0"
set "JAPAN_EXPORT_CHECK=0"
set "ALLIED_EXPORT_CHECK=0"
set "FINAL_EXIT_CODE=0"

echo ============================================================
echo  JAPAN run  (validates: Akagi ship, Tokyo base)
echo ============================================================
py -3-32 "%~dp0pywitpaescraper.py" ^
  --dll-dir "%DLL_DIR%" ^
  --start-of-day-file "%START_OF_DAY_FILE%" ^
  --end-of-day-file "%END_OF_DAY_FILE%" ^
  --japan ^
  --output-dir "%JAPAN_OUTPUT_DIR%"

set "JAPAN_EXIT_CODE=%ERRORLEVEL%"
if %JAPAN_EXIT_CODE% neq 0 (
  echo JAPAN run FAILED with exit code %JAPAN_EXIT_CODE%
) else (
  echo JAPAN run SUCCEEDED
  call :check_exports "%JAPAN_OUTPUT_DIR%" JAPAN_EXPORT_CHECK
)

echo.
echo ============================================================
echo  US run  (validates: Enterprise ship, Pearl Harbor base)
echo ============================================================
py -3-32 "%~dp0pywitpaescraper.py" ^
  --dll-dir "%DLL_DIR%" ^
  --start-of-day-file "%START_OF_DAY_FILE%" ^
  --end-of-day-file "%END_OF_DAY_FILE%" ^
  --alllied ^
  --output-dir "%ALLIED_OUTPUT_DIR%"

set "US_EXIT_CODE=%ERRORLEVEL%"
if %US_EXIT_CODE% neq 0 (
    echo US run FAILED with exit code %US_EXIT_CODE%
) else (
    echo US run SUCCEEDED
    call :check_exports "%ALLIED_OUTPUT_DIR%" ALLIED_EXPORT_CHECK
)

if %JAPAN_EXIT_CODE% neq 0 set "FINAL_EXIT_CODE=%JAPAN_EXIT_CODE%"
if %US_EXIT_CODE% neq 0 set "FINAL_EXIT_CODE=%US_EXIT_CODE%"
if %JAPAN_EXPORT_CHECK% neq 0 set "FINAL_EXIT_CODE=%JAPAN_EXPORT_CHECK%"
if %ALLIED_EXPORT_CHECK% neq 0 set "FINAL_EXIT_CODE=%ALLIED_EXPORT_CHECK%"

echo.
echo Both runs complete. JAPAN=%JAPAN_EXIT_CODE% US=%US_EXIT_CODE% JAPAN_EXPORT=%JAPAN_EXPORT_CHECK% ALLIED_EXPORT=%ALLIED_EXPORT_CHECK% Final=%FINAL_EXIT_CODE%
exit /b %FINAL_EXIT_CODE%

:check_exports
setlocal
set "OUT_DIR=%~1"
set "CHECK_CODE=0"

echo Verifying exports in "%OUT_DIR%"
for %%F in (ships.json ground_units.json airgroups.json bases.json taskforces.json turn.json threats.json) do (
  if not exist "%OUT_DIR%\%%F" (
    echo   MISSING: %%F
    set "CHECK_CODE=1"
  ) else (
    for %%S in ("%OUT_DIR%\%%F") do (
      if %%~zS LEQ 0 (
        echo   EMPTY: %%F
        set "CHECK_CODE=1"
      ) else (
        echo   OK: %%F (%%~zS bytes)
      )
    )
  )
)

if "%CHECK_CODE%"=="0" (
  py -3-32 "%~dp0verify_turn_json.py" "%OUT_DIR%\turn.json" "Dorniers"
  if errorlevel 1 (
    set "CHECK_CODE=1"
  )
)

if "%CHECK_CODE%"=="0" (
  echo Export smoke test PASSED for "%OUT_DIR%"
) else (
  echo Export smoke test FAILED for "%OUT_DIR%"
)

endlocal & set "%~2=%CHECK_CODE%"
exit /b 0
