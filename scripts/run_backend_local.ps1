param(
    [switch]$SkipMigrations,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Không tìm thấy Python virtual environment tại $pythonPath"
}

Push-Location $projectRoot
try {
    if (-not $SkipMigrations) {
        & $pythonPath -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Alembic migration thất bại với exit code $LASTEXITCODE"
        }
    }

    $uvicornArguments = @(
        "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000"
    )
    if ($Reload) {
        $uvicornArguments += "--reload"
    }
    & $pythonPath @uvicornArguments
} finally {
    Pop-Location
}
