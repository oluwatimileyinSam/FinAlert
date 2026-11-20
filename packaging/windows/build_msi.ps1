$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AppBuildScript = Join-Path $PSScriptRoot "build_app.ps1"
$WxsFile = Join-Path $PSScriptRoot "FinAlert.wxs"
$EulaAcceptance = Join-Path $HOME ".wix\wix7-osmf-eula.txt"
$MsiDirectory = Join-Path $ProjectRoot "dist\windows"
$MsiPath = Join-Path $MsiDirectory "FinAlert-1.0.0-x64.msi"
$AppExecutable = Join-Path $MsiDirectory "FinAlert\FinAlert.exe"

$WixCommand = Get-Command wix.exe -ErrorAction SilentlyContinue
if (-not $WixCommand) {
    throw "WiX 7.0.1 is required. Install the .NET SDK, then run: dotnet tool install --global wix --version 7.0.1"
}

$WixVersion = (& $WixCommand.Source --version | Select-Object -First 1).Trim()
if (-not $WixVersion.StartsWith("7.0.1")) {
    throw "WiX 7.0.1 is required; found: $WixVersion"
}

if (-not (Test-Path -LiteralPath $EulaAcceptance -PathType Leaf)) {
    throw "Review https://docs.firegiant.com/wix/osmf/, then accept the WiX terms manually with: wix eula accept wix7"
}

if (-not (Test-Path -LiteralPath $WxsFile -PathType Leaf)) {
    throw "The MSI definition was not found: $WxsFile"
}

New-Item -ItemType Directory -Force -Path $MsiDirectory | Out-Null

Push-Location $ProjectRoot
try {
    & $AppBuildScript

    if (-not (Test-Path -LiteralPath $AppExecutable -PathType Leaf)) {
        throw "The Windows app build did not produce FinAlert.exe."
    }

    & $WixCommand.Source extension add --global WixToolset.Util.wixext/7.0.1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install the WiX Util extension."
    }

    & $WixCommand.Source build `
        -arch x64 `
        -ext WixToolset.Util.wixext `
        -out $MsiPath `
        $WxsFile

    if ($LASTEXITCODE -ne 0) {
        throw "The FinAlert MSI build failed."
    }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $MsiPath -PathType Leaf)) {
    throw "The MSI build finished, but the output file was not found: $MsiPath"
}

Write-Output "Built: $MsiPath"
