$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Requirements = Join-Path $ProjectRoot "requirements.txt"
$Logo = Join-Path $ProjectRoot "assets\fin_alert_logo.svg"
$Icon = Join-Path $ProjectRoot "assets\FinAlert.ico"
$IconScript = Join-Path $PSScriptRoot "create_icon.py"
$PackagingRoot = Join-Path $env:LOCALAPPDATA "FinAlert\packaging"
$Venv = Join-Path $PackagingRoot "venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$PyInstaller = Join-Path $Venv "Scripts\pyinstaller.exe"
$DistRoot = Join-Path $ProjectRoot "dist\windows"
$WorkRoot = Join-Path $ProjectRoot "build\windows"
$SpecRoot = Join-Path $WorkRoot "specs"

if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    throw "requirements.txt was not found at: $Requirements"
}

if (-not (Test-Path -LiteralPath $Logo -PathType Leaf)) {
    throw "The FinAlert logo SVG was not found at: $Logo"
}

if (-not (Test-Path -LiteralPath $IconScript -PathType Leaf)) {
    throw "The Windows icon converter was not found at: $IconScript"
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $PythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($PythonLauncher) {
        & $PythonLauncher.Source -3.12 -m venv $Venv
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the packaging environment."
        }
    } else {
        $SystemPython = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $SystemPython) {
            throw "Install Python 3.12, then run this script again."
        }
        & $SystemPython.Source -m venv $Venv
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the packaging environment."
        }
    }
}

New-Item -ItemType Directory -Force -Path $DistRoot, $WorkRoot, $SpecRoot | Out-Null

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Could not upgrade pip."
}

& $Python -m pip install -r $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the project requirements."
}

& $Python -m pip install pyinstaller Pillow
if ($LASTEXITCODE -ne 0) {
    throw "Could not install PyInstaller and Pillow."
}

& $Python $IconScript
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the Windows app icon."
}

if (-not (Test-Path -LiteralPath $Icon -PathType Leaf)) {
    throw "The Windows icon was not created: $Icon"
}

Push-Location $ProjectRoot
try {
    & $PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name FinAlert `
        --icon $Icon `
        --hidden-import keyring.backends.Windows `
        --distpath $DistRoot `
        --workpath $WorkRoot `
        --specpath $SpecRoot `
        --add-data "$Logo;assets" `
        "main.py"

    if ($LASTEXITCODE -ne 0) {
        throw "The Windows app build failed."
    }
} finally {
    Pop-Location
}

$AppExecutable = Join-Path $DistRoot "FinAlert\FinAlert.exe"
if (-not (Test-Path -LiteralPath $AppExecutable -PathType Leaf)) {
    throw "Build finished, but FinAlert.exe was not found at: $AppExecutable"
}

Write-Output "Built: $AppExecutable"
