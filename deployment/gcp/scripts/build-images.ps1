[CmdletBinding()]
param(
    [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
    [string]$Region = "asia-southeast1",
    [string]$Repository = "vlegal",
    [string]$Tag = "",
    [switch]$Push
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "Pass -ProjectId or set GOOGLE_CLOUD_PROJECT."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path
if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = (& git -C $repoRoot rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Tag)) {
        throw "Cannot determine Git SHA; pass -Tag explicitly."
    }
}

$registry = "$Region-docker.pkg.dev"
$imageRoot = "$registry/$ProjectId/$Repository"

if ($Push) {
    & gcloud auth configure-docker $registry --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot configure Docker credentials for Artifact Registry."
    }
}

Push-Location $repoRoot
try {
    $target = "$imageRoot/vlegal-app`:$Tag"
    $arguments = @(
        "buildx", "build",
        "--platform=linux/amd64",
        "--file=docker/app.Dockerfile",
        "--tag=$target"
    )
    $arguments += if ($Push) { "--push" } else { "--load" }
    $arguments += "."

    Write-Host "Building app -> $target"
    & docker @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build image: app"
    }
}
finally {
    Pop-Location
}

Write-Host "Completed. Image tag: $Tag"
