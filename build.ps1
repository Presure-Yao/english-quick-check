# Run from PowerShell: .\build.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$Python = Join-Path $PSScriptRoot '.venv-build\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    python -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Could not create build environment. Install Python 3.10+ with Tkinter.' }
}
& $Python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
& $Python -m unittest test_core test_hotkey test_ui
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; build stopped.' }
& $Python -m PyInstaller --noconfirm --clean --onedir --windowed --name 'English Quick Check' --icon assets/app.ico --version-file version_info.txt --add-data 'assets/app.ico;assets' app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
$Folder = Join-Path $PSScriptRoot 'dist\English Quick Check'
$Report = Join-Path $PSScriptRoot ('build\smoke-' + [guid]::NewGuid().ToString('N') + '.json')
$Process = Start-Process -FilePath (Join-Path $Folder 'English Quick Check.exe') -ArgumentList @('--smoke-test', ('"' + $Report + '"')) -PassThru
if (-not $Process.WaitForExit(30000)) { $Process.Kill(); throw 'Packaged GUI test timed out.' }
if ($Process.ExitCode -ne 0 -or -not (Test-Path $Report)) { throw 'Packaged GUI test failed to write a report.' }
$Result = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if (-not $Result.ok -or -not $Result.frozen) { throw "Packaged GUI test failed: $($Result.error)" }
Copy-Item README.md (Join-Path $Folder 'README.md')
# Keep this script ASCII-compatible with Windows PowerShell 5.1.
$GuideName = -join ([char[]](0x4f7f, 0x7528, 0x8bf4, 0x660e))
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "$GuideName.txt") -Destination $Folder
New-Item -ItemType Directory -Force release | Out-Null
$Archive = Join-Path $PSScriptRoot 'release\English-Quick-Check-v0.2.1-windows-x64.zip'
Compress-Archive -Path $Folder -DestinationPath $Archive -Force
$Hash = (Get-FileHash $Archive -Algorithm SHA256).Hash.ToLower()
"$Hash  English-Quick-Check-v0.2.1-windows-x64.zip" | Set-Content -Encoding ascii 'release\SHA256SUMS.txt'
Write-Host "Portable build ready: $Archive"
