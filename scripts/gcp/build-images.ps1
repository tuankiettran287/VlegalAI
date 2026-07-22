[CmdletBinding()]
param(
    [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
    [string]$Region = "asia-southeast1",
    [string]$Repository = "vlegal",
    [string]$Tag = "",
    [ValidateSet("api", "frontend", "worker", "beat", "migrate", "model-init", "reindex")]
    [string[]]$Service = @("api", "frontend", "worker", "beat", "migrate", "model-init", "reindex"),
    [switch]$Push
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "Truyền -ProjectId hoặc đặt GOOGLE_CLOUD_PROJECT."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = (& git -C $repoRoot rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Tag)) {
        throw "Không lấy được Git SHA; hãy truyền -Tag."
    }
}

$registry = "$Region-docker.pkg.dev"
$imageRoot = "$registry/$ProjectId/$Repository"

if ($Push) {
    & gcloud auth configure-docker $registry --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Không cấu hình được Docker credential cho Artifact Registry."
    }
}

Push-Location $repoRoot
try {
    foreach ($name in $Service) {
        $image = "$imageRoot/vlegal-$name`:$Tag"
        $arguments = @(
            "buildx", "build",
            "--platform=linux/amd64",
            "--file=docker/$name.Dockerfile",
            "--tag=$image"
        )
        $arguments += if ($Push) { "--push" } else { "--load" }
        $arguments += "."

        Write-Host "Building $name -> $image"
        & docker @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Build image $name thất bại."
        }
    }
}
finally {
    Pop-Location
}

Write-Host "Hoàn tất. Image tag: $Tag"
