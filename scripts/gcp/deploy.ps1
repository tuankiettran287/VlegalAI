[CmdletBinding()]
param(
    [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
    [string]$Region = "asia-southeast1",
    [string]$Repository = "vlegal",
    [string]$Tag = "",
    [string]$RunServiceAccount = "",
    [string]$ModelBucket = "",
    [string]$EmbeddingBucket = "",
    [string]$CorpusBucket = "",
    [string]$Network = "default",
    [string]$Subnet = "default",
    [string]$Neo4jUri = $env:NEO4J_URI,
    [string]$Neo4jUser = "neo4j",
    [string]$FrontendUrl = "",
    [ValidateSet("all", "model-init", "migrate", "reindex", "api", "frontend", "worker", "beat")]
    [string]$Component = "all",
    [ValidateSet("nvidia-rtx-pro-6000", "nvidia-l4")]
    [string]$GpuType = "nvidia-rtx-pro-6000",
    [switch]$ExecuteJobs
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "Truyền -ProjectId hoặc đặt GOOGLE_CLOUD_PROJECT."
}
if ([string]::IsNullOrWhiteSpace($Neo4jUri) -and $Component -in @("all", "reindex", "api", "worker")) {
    throw "Truyền -Neo4jUri hoặc đặt NEO4J_URI."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = (& git -C $repoRoot rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Tag)) {
        throw "Không lấy được Git SHA; hãy truyền -Tag."
    }
}
if ([string]::IsNullOrWhiteSpace($RunServiceAccount)) {
    $RunServiceAccount = "vlegal-run@$ProjectId.iam.gserviceaccount.com"
}
if ([string]::IsNullOrWhiteSpace($ModelBucket)) {
    $ModelBucket = "$ProjectId-vlegal-qwen3-14b"
}
if ([string]::IsNullOrWhiteSpace($EmbeddingBucket)) {
    $EmbeddingBucket = "$ProjectId-vlegal-bge-m3"
}
if ([string]::IsNullOrWhiteSpace($CorpusBucket)) {
    $CorpusBucket = "$ProjectId-vlegal-corpus"
}

$imageRoot = "$Region-docker.pkg.dev/$ProjectId/$Repository"
$apiService = "vlegal-api"
$frontendService = "vlegal-frontend"
$workerPool = "vlegal-worker"
$beatPool = "vlegal-beat"
$migrateJob = "vlegal-migrate"
$modelJob = "vlegal-model-init"
$reindexJob = "vlegal-reindex"

$gpuCpu = if ($GpuType -eq "nvidia-l4") { "8" } else { "20" }
$gpuMemory = if ($GpuType -eq "nvidia-l4") { "32Gi" } else { "80Gi" }
$apiSecrets = @(
    "DATABASE_URL=vlegal-database-url:latest",
    "NEO4J_PASSWORD=vlegal-neo4j-password:latest",
    "SESSION_SECRET=vlegal-session-secret:latest",
    "MESSAGE_ENCRYPTION_KEY=vlegal-message-key:latest",
    "OIDC_CLIENT_ID=vlegal-oidc-client-id:latest",
    "OIDC_CLIENT_SECRET=vlegal-oidc-client-secret:latest",
    "TAVILY_API_KEY=vlegal-tavily-key:latest"
) -join ","

$workerSecrets = @(
    "DATABASE_URL=vlegal-database-url:latest",
    "NEO4J_PASSWORD=vlegal-neo4j-password:latest",
    "TAVILY_API_KEY=vlegal-tavily-key:latest"
) -join ","

function Invoke-Gcloud {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud thất bại: gcloud $($Arguments -join ' ')"
    }
}

function Get-ServiceUrl {
    param([Parameter(Mandatory)][string]$Name)
    $url = (& gcloud run services describe $Name --project=$ProjectId --region=$Region --format="value(status.url)").Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($url)) {
        throw "Không lấy được URL của Cloud Run service $Name."
    }
    return $url
}

function Deploy-ModelInit {
    Invoke-Gcloud @(
        "run", "jobs", "deploy", $modelJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$imageRoot/vlegal-model-init`:$Tag",
        "--service-account=$RunServiceAccount",
        "--cpu=4", "--memory=8Gi", "--task-timeout=3h", "--max-retries=3",
        "--set-env-vars=QWEN_MODEL_REPO=Qwen/Qwen3-14B,QWEN_MODEL_REVISION=main,EMBEDDING_MODEL_REPO=BAAI/bge-m3,EMBEDDING_MODEL_REVISION=main,HF_HUB_OFFLINE=0,TRANSFORMERS_OFFLINE=0",
        "--add-volume=mount-path=/models/qwen3,type=cloud-storage,bucket=$ModelBucket,readonly=false,mount-options=uid=10001;gid=10001",
        "--add-volume=mount-path=/models/embedding,type=cloud-storage,bucket=$EmbeddingBucket,readonly=false,mount-options=uid=10001;gid=10001",
        "--quiet"
    )
    if ($ExecuteJobs) {
        Invoke-Gcloud @("run", "jobs", "execute", $modelJob, "--project=$ProjectId", "--region=$Region", "--wait")
    }
}

function Deploy-Migrate {
    Invoke-Gcloud @(
        "run", "jobs", "deploy", $migrateJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$imageRoot/vlegal-migrate`:$Tag",
        "--service-account=$RunServiceAccount",
        "--cpu=1", "--memory=1Gi", "--task-timeout=15m", "--max-retries=1",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest",
        "--quiet"
    )
    if ($ExecuteJobs) {
        Invoke-Gcloud @("run", "jobs", "execute", $migrateJob, "--project=$ProjectId", "--region=$Region", "--wait")
    }
}

function Deploy-Reindex {
    $envVars = @(
        "APP_ENV=production",
        "LEGAL_DATA_DIR=/app/legal-data",
        "LEGAL_STORAGE_DIR=/tmp/graphrag",
        "LEGAL_GRAPHRAG_DB=/tmp/graphrag/legal_graphrag.sqlite",
        "EMBEDDING_MODEL_PATH=/models/embedding",
        "EMBEDDING_MODEL_REPO=BAAI/bge-m3",
        "EMBEDDING_MODEL_REVISION=main",
        "EMBEDDING_DEVICE=cuda",
        "EMBEDDING_BATCH_SIZE=4",
        "EMBEDDING_MAX_SEQUENCE_LENGTH=2048",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser",
        "HF_HUB_OFFLINE=1",
        "TRANSFORMERS_OFFLINE=1"
    ) -join ","

    Invoke-Gcloud @(
        "run", "jobs", "deploy", $reindexJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$imageRoot/vlegal-reindex`:$Tag",
        "--service-account=$RunServiceAccount",
        "--command=python",
        "--args=scripts/sync_external_graphrag.py,--reset-neo4j,--reset-postgres",
        "--tasks=1", "--parallelism=1", "--max-retries=1", "--task-timeout=24h",
        "--gpu=1", "--gpu-type=nvidia-l4", "--no-gpu-zonal-redundancy",
        "--cpu=4", "--memory=16Gi",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--add-volume=mount-path=/models/embedding,type=cloud-storage,bucket=$EmbeddingBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--add-volume=mount-path=/app/legal-data,type=cloud-storage,bucket=$CorpusBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--set-env-vars=$envVars",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest,NEO4J_PASSWORD=vlegal-neo4j-password:latest",
        "--quiet"
    )
    if ($ExecuteJobs) {
        Invoke-Gcloud @("run", "jobs", "execute", $reindexJob, "--project=$ProjectId", "--region=$Region", "--wait")
    }
}

function Deploy-Api {
    $envVars = @(
        "APP_ENV=production",
        "QWEN_MODEL_PATH=/models/qwen3",
        "QWEN_MODEL=Qwen3-14B",
        "QWEN_DEVICE=cuda",
        "QWEN_DTYPE=bfloat16",
        "QWEN_MAX_CONCURRENT_GENERATIONS=1",
        "EMBEDDING_MODEL_PATH=/models/embedding",
        "EMBEDDING_MODEL_REPO=BAAI/bge-m3",
        "EMBEDDING_MODEL_REVISION=main",
        "EMBEDDING_DEVICE=cuda",
        "EMBEDDING_BATCH_SIZE=4",
        "EMBEDDING_MAX_SEQUENCE_LENGTH=2048",
        "WEB_CONCURRENCY=1",
        "DATABASE_POOL_SIZE=5",
        "DATABASE_MAX_OVERFLOW=5",
        "RETRIEVER_BACKEND=hybrid_rag",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser"
    ) -join ","

    Invoke-Gcloud @(
        "run", "deploy", $apiService,
        "--project=$ProjectId", "--region=$Region",
        "--image=$imageRoot/vlegal-api`:$Tag",
        "--execution-environment=gen2", "--service-account=$RunServiceAccount", "--port=8080",
        "--gpu=1", "--gpu-type=$GpuType", "--no-gpu-zonal-redundancy",
        "--cpu=$gpuCpu", "--memory=$gpuMemory", "--concurrency=1",
        "--min=0", "--max=1", "--timeout=3600", "--no-cpu-throttling",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--allow-unauthenticated",
        "--add-volume=mount-path=/models/qwen3,type=cloud-storage,bucket=$ModelBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--add-volume=mount-path=/models/embedding,type=cloud-storage,bucket=$EmbeddingBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--set-env-vars=$envVars", "--set-secrets=$apiSecrets",
        "--quiet"
    )
}

function Set-ApiExternalUrl {
    param([Parameter(Mandatory)][string]$Url)
    Invoke-Gcloud @(
        "run", "services", "update", $apiService,
        "--project=$ProjectId", "--region=$Region",
        "--update-env-vars=PUBLIC_URL=$Url,FRONTEND_URL=$Url,CORS_ORIGINS=$Url,OIDC_REDIRECT_URI=$Url/api/auth/google/callback,COOKIE_SECURE=true",
        "--quiet"
    )
}

function Deploy-Frontend {
    $apiUrl = Get-ServiceUrl $apiService
    Invoke-Gcloud @(
        "run", "deploy", $frontendService,
        "--project=$ProjectId", "--region=$Region",
        "--image=$imageRoot/vlegal-frontend`:$Tag",
        "--execution-environment=gen2", "--service-account=$RunServiceAccount", "--port=8080",
        "--cpu=1", "--memory=512Mi", "--concurrency=80", "--min=0", "--max=5",
        "--allow-unauthenticated", "--set-env-vars=API_UPSTREAM=$apiUrl",
        "--quiet"
    )
    return Get-ServiceUrl $frontendService
}

function Deploy-Worker {
    $envVars = @(
        "APP_ENV=production",
        "QWEN_MODEL_PATH=/models/qwen3",
        "QWEN_MODEL=Qwen3-14B",
        "QWEN_DEVICE=cuda",
        "QWEN_DTYPE=bfloat16",
        "QWEN_MAX_CONCURRENT_GENERATIONS=1",
        "EMBEDDING_MODEL_PATH=/models/embedding",
        "EMBEDDING_MODEL_REPO=BAAI/bge-m3",
        "EMBEDDING_MODEL_REVISION=main",
        "EMBEDDING_DEVICE=cuda",
        "EMBEDDING_BATCH_SIZE=4",
        "EMBEDDING_MAX_SEQUENCE_LENGTH=2048",
        "DATABASE_POOL_SIZE=2",
        "DATABASE_MAX_OVERFLOW=2",
        "RETRIEVER_BACKEND=hybrid_rag",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser"
    ) -join ","

    Invoke-Gcloud @(
        "run", "worker-pools", "deploy", $workerPool,
        "--project=$ProjectId", "--region=$Region", "--instances=1",
        "--image=$imageRoot/vlegal-worker`:$Tag", "--service-account=$RunServiceAccount",
        "--gpu=1", "--gpu-type=$GpuType", "--no-gpu-zonal-redundancy",
        "--cpu=$gpuCpu", "--memory=$gpuMemory",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--add-volume=mount-path=/models/qwen3,type=cloud-storage,bucket=$ModelBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--add-volume=mount-path=/models/embedding,type=cloud-storage,bucket=$EmbeddingBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--set-env-vars=$envVars", "--set-secrets=$workerSecrets",
        "--quiet"
    )
}

function Deploy-Beat {
    Invoke-Gcloud @(
        "run", "worker-pools", "deploy", $beatPool,
        "--project=$ProjectId", "--region=$Region", "--instances=1",
        "--image=$imageRoot/vlegal-beat`:$Tag", "--service-account=$RunServiceAccount",
        "--cpu=1", "--memory=512Mi",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--set-env-vars=APP_ENV=production",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest",
        "--quiet"
    )
}

switch ($Component) {
    "model-init" { Deploy-ModelInit }
    "migrate" { Deploy-Migrate }
    "reindex" { Deploy-Reindex }
    "api" {
        Deploy-Api
        $externalUrl = if ($FrontendUrl) { $FrontendUrl } else { Get-ServiceUrl $apiService }
        Set-ApiExternalUrl $externalUrl
        Write-Host "API URL: $(Get-ServiceUrl $apiService)"
    }
    "frontend" {
        $url = Deploy-Frontend
        Set-ApiExternalUrl $url
        Write-Host "Frontend URL: $url"
    }
    "worker" { Deploy-Worker }
    "beat" { Deploy-Beat }
    "all" {
        Deploy-ModelInit
        Deploy-Migrate
        Deploy-Reindex
        Deploy-Api
        $url = Deploy-Frontend
        Set-ApiExternalUrl $url
        Deploy-Worker
        Deploy-Beat
        Write-Host "Frontend URL: $url"
        Write-Host "API URL: $(Get-ServiceUrl $apiService)"
        Write-Host "OAuth redirect URI: $url/api/auth/google/callback"
    }
}
