[CmdletBinding()]
param(
    [switch]$SkipAppBuild,
    [switch]$NoInstall,
    [switch]$LaunchInstaller
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    Write-Host ""
    Write-Host ("> {0} {1}" -f $Executable, ($Arguments -join " ")) -ForegroundColor DarkCyan
    & $Executable @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Command failed with exit code $exitCode: $Executable"
    }
}

function Find-InnoCompiler {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command -and $command.Source -and (Test-Path $command.Source -PathType Leaf)) {
        return $command.Source
    }

    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
    }
    $programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
    if ($programFilesX86) {
        $candidates += Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe"
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate -PathType Leaf) {
            return $candidate
        }
    }
    return $null
}

try {
    $iscc = Find-InnoCompiler

    if (-not $iscc) {
        if ($NoInstall) {
            throw "Inno Setup 6 was not found. Install it first, then rerun this script."
        }

        $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
        if (-not $winget -or -not $winget.Source) {
            throw "Inno Setup 6 is missing and winget is unavailable. Install Inno Setup 6 from https://jrsoftware.org/isdl.php, then rerun this script."
        }

        Write-Host "Inno Setup 6 not found. Installing for the current Windows user with WinGet..." -ForegroundColor Yellow
        Invoke-CheckedNative -Executable $winget.Source -Arguments @(
            "install", "--id", "JRSoftware.InnoSetup", "--exact",
            "--source", "winget", "--scope", "user", "--interactive",
            "--accept-package-agreements", "--accept-source-agreements"
        )

        $iscc = Find-InnoCompiler
        if (-not $iscc) {
            throw "WinGet completed but ISCC.exe was not found. Check the Inno Setup 6 installation, then rerun this script."
        }
    }

    Write-Host "Using Inno Setup compiler: $iscc" -ForegroundColor Green

    if (-not $SkipAppBuild) {
        $python = Get-Command "python.exe" -ErrorAction Stop
        $cargo = Get-Command "cargo.exe" -ErrorAction Stop

        Invoke-CheckedNative -Executable $python.Source -Arguments @(
            "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller"
        )
        Invoke-CheckedNative -Executable $cargo.Source -Arguments @(
            "build", "--release", "--manifest-path", "sandbox-rs/Cargo.toml"
        )
        Invoke-CheckedNative -Executable $python.Source -Arguments @(
            "scripts/package_edith.py"
        )
    }

    $version = (Get-Content -LiteralPath (Join-Path $repoRoot "VERSION") -Raw -Encoding UTF8).Trim()
    if (-not $version) {
        throw "VERSION is empty; cannot name the installer."
    }

    $sourceDir = Join-Path $repoRoot "dist\EDITH"
    $appExe = Join-Path $sourceDir "EDITH.exe"
    if (-not (Test-Path $sourceDir -PathType Container)) {
        throw "Application bundle not found: $sourceDir. Run the packaging step first."
    }
    if (-not (Test-Path $appExe -PathType Leaf)) {
        throw "Application executable not found: $appExe. Packaging did not produce EDITH.exe."
    }

    $installerDir = Join-Path $repoRoot "dist\installer"
    New-Item -ItemType Directory -Path $installerDir -Force | Out-Null
    $setupExe = Join-Path $installerDir "EDITH-Setup-$version-x64.exe"

    Invoke-CheckedNative -Executable $iscc -Arguments @(
        (Join-Path $repoRoot "installer\windows\EDITH.iss"),
        "/DAppVersion=$version",
        "/DSourceDir=$sourceDir"
    )

    if (-not (Test-Path $setupExe -PathType Leaf)) {
        throw "Inno Setup returned success but the expected installer was not created: $setupExe"
    }

    $artifact = Get-Item -LiteralPath $setupExe
    if ($artifact.Length -le 0) {
        throw "Installer file is empty: $setupExe"
    }

    $hash = (Get-FileHash -LiteralPath $setupExe -Algorithm SHA256).Hash
    Write-Host ""
    Write-Host "BUILD SUCCESSFUL" -ForegroundColor Green
    Write-Host "Application EXE : $appExe" -ForegroundColor Cyan
    Write-Host "Installer EXE   : $setupExe" -ForegroundColor Cyan
    Write-Host ("Installer size  : {0:N1} MB" -f ($artifact.Length / 1MB)) -ForegroundColor Cyan
    Write-Host "SHA256          : $hash" -ForegroundColor DarkGray

    if ($LaunchInstaller) {
        Start-Process -FilePath $setupExe
    }
}
finally {
    Pop-Location
}
