@echo off
setlocal enabledelayedexpansion

>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

if %errorlevel% neq 0 (
    echo Please run this setup as admin. & echo Requesting administrative privileges...
    powershell -Command "& {Start-Process -FilePath '%0' -ArgumentList '-Admin' -Verb RunAs}"
    goto End
)

echo Setting up ChromeDriver installation...

powershell -Command "& { $response = Invoke-WebRequest -Uri 'https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json'; if ($response.StatusCode -ne 200) { exit 1 }; $response.Content | Out-File 'latest_versions_info.json' }"
if %errorlevel% neq 0 ( 
    echo Please check your internet connection. See if any applications, firewalls, vpns, or devices are blocking the download.
    goto ExitSetup
)

for /f "delims=" %%a in ('powershell -Command "& {(Get-Content 'latest_versions_info.json' | ConvertFrom-Json).channels.Stable.version} "') do (
    set "latest_version=%%~a"
)

if not defined latest_version (
    echo FAILED to extract the latest version from the JSON file.
    goto ExitSetup
)

set "chrome_driver_url=https://storage.googleapis.com/chrome-for-testing-public/!latest_version!/win64/chromedriver-win64.zip"

echo Latest ChromeDriver version: !latest_version!.
echo Downloading ChromeDriver from URL: '!chrome_driver_url!' ...

powershell -Command "& {Invoke-WebRequest -Uri !chrome_driver_url! -OutFile 'chromedriver.zip'}"

set "chrome_install_dir=C:\Program Files\Google\Chrome"
if not exist "%chrome_install_dir%" mkdir "%chrome_install_dir%"

powershell -Command "& {Expand-Archive -Path 'chromedriver.zip' -DestinationPath '%chrome_install_dir%' -Force}"
if %errorlevel% neq 0 ( 
    echo FAILED to extract ChromeDriver. Check if any application is denying installation or extraction.
    goto ExitSetup
)

set "chromedriver_dir=%chrome_install_dir%\chromedriver-win64"

:CleanUp
del chromedriver.zip
del latest_versions_info.json
echo Removed setup files.

echo Opening Chrome Driver...
start "" "%chromedriver_dir%\chromedriver.exe"

:ExitSetup
pause
exit

:End