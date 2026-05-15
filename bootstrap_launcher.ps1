$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogPath = Join-Path $LogDir ("bootstrap-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

function Show-LauncherError {
    param([string]$Message)

    try {
        $shell = New-Object -ComObject WScript.Shell
        $shell.Popup("$Message`n`nLog: $LogPath", 0, "HelpAI Launcher", 16) | Out-Null
    } catch {
        Add-Content -Path $LogPath -Value "Failed to show error popup: $($_.Exception.Message)"
    }
}

function Test-Python {
    param(
        [string]$FilePath,
        [string[]]$Arguments = @()
    )

    try {
        & $FilePath @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-Python {
    $candidates = @(
        @{ FilePath = "py"; Arguments = @("-3.12") },
        @{ FilePath = "py"; Arguments = @("-3.11") },
        @{ FilePath = "python"; Arguments = @() }
    )

    foreach ($candidate in $candidates) {
        if (Test-Python -FilePath $candidate.FilePath -Arguments $candidate.Arguments) {
            return [pscustomobject]$candidate
        }
    }

    $knownPaths = @(
        (Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LocalAppData "Programs\Python\Python311\python.exe"),
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe"
    )

    foreach ($path in $knownPaths) {
        if ((Test-Path -LiteralPath $path) -and (Test-Python -FilePath $path)) {
            return [pscustomobject]@{ FilePath = $path; Arguments = @() }
        }
    }

    return $null
}

function Install-PythonWithWinget {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        return $false
    }

    & $winget.Source install --id Python.Python.3.12 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
    return ($LASTEXITCODE -eq 0)
}

function Invoke-Python {
    param(
        [pscustomobject]$Python,
        [string[]]$Arguments
    )

    & $Python.FilePath @($Python.Arguments) @Arguments
    return $LASTEXITCODE
}

function Assert-PathInsideRoot {
    param([string]$Path)

    $rootFullPath = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
    $targetFullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
    $prefix = $rootFullPath + "\"

    if (-not $targetFullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the HelpAI folder: $targetFullPath"
    }
}

try {
    Start-Transcript -Path $LogPath -Append | Out-Null

    Write-Host "HelpAI bootstrap started from $Root"

    $python = Find-Python
    if (-not $python) {
        Write-Host "Python 3.11+ not found. Trying winget install..."
        if (-not (Install-PythonWithWinget)) {
            throw "Python 3.11 or newer was not found, and winget could not install Python 3.12. Install Python 3.11+ manually from python.org, then run this launcher again."
        }

        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        $python = Find-Python
        if (-not $python) {
            throw "Python 3.12 installation finished, but python.exe was not found. Restart Windows or install Python 3.11+ manually, then run this launcher again."
        }
    }

    Write-Host "Using Python: $($python.FilePath) $($python.Arguments -join ' ')"

    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $venvPythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"

    if ((Test-Path -LiteralPath $venvPython) -and (-not (Test-Python -FilePath $venvPython))) {
        Write-Host "Existing .venv uses an unsupported Python. Rebuilding it..."
        $venvPath = Join-Path $Root ".venv"
        Assert-PathInsideRoot -Path $venvPath
        Remove-Item -LiteralPath $venvPath -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Host "Creating virtual environment..."
        $venvArgs = "-m venv .venv".Split(" ")
        $exitCode = Invoke-Python -Python $python -Arguments $venvArgs
        if ($exitCode -ne 0) {
            throw "Failed to create the virtual environment."
        }
    }

    if (-not (Test-Path -LiteralPath $venvPythonw)) {
        throw "The virtual environment was created, but pythonw.exe was not found."
    }

    Write-Host "Installing dependencies from requirements.txt..."
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install dependencies from requirements.txt."
    }

    Write-Host "Launching HelpAI..."
    Start-Process -FilePath $venvPythonw -ArgumentList @((Join-Path $Root "main.py")) -WorkingDirectory $Root -WindowStyle Hidden

    Stop-Transcript | Out-Null
} catch {
    $message = $_.Exception.Message
    try {
        Write-Host "ERROR: $message"
        Stop-Transcript | Out-Null
    } catch {
    }
    Show-LauncherError $message
    exit 1
}
