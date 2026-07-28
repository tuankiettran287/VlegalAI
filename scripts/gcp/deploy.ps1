[CmdletBinding()]
param(
    [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
    [string]$Region = "asia-southeast1",
    [string]$EmbeddingLocation = "",
    [string]$EmbeddingVertexLocations = $env:EMBEDDING_VERTEX_LOCATIONS,
    [double]$EmbeddingVertexRequestsPerMinute = 4.5,
    [string]$Repository = "vlegal",
    [string]$Tag = "",
    [string]$RunServiceAccount = "",
    [string]$CorpusBucket = "",
    [string]$Network = "default",
    [string]$Subnet = "default",
    [string]$Neo4jUri = $env:NEO4J_URI,
    [string]$Neo4jUser = "neo4j",
    [string]$Neo4jDatabase = "neo4j",
    [string]$FrontendUrl = "",
    [ValidateRange(0, 100)]
    [int]$WorkerInstances = 0,
    [ValidateRange(0, 100)]
    [int]$BeatInstances = 0,
    [ValidateSet("all", "migrate", "reindex", "api", "frontend", "worker", "beat")]
    [string]$Component = "all",
    [switch]$ExecuteMigrate,
    [switch]$ExecuteReindex,
    [switch]$ExecuteJobs
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "Truyền -ProjectId hoặc đặt GOOGLE_CLOUD_PROJECT."
}
if ([string]::IsNullOrWhiteSpace($Neo4jUri) -and $Component -in @("all", "reindex", "api", "worker")) {
    throw "Truyền -Neo4jUri hoặc đặt NEO4J_URI."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = (& git -C $repoRoot rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Tag)) {
        throw "Không lấy được Git SHA; hãy truyền -Tag."
    }
}
if ([string]::IsNullOrWhiteSpace($RunServiceAccount)) {
    $RunServiceAccount = "vlegal-run@$ProjectId.iam.gserviceaccount.com"
}
if ([string]::IsNullOrWhiteSpace($EmbeddingLocation)) {
    $EmbeddingLocation = "global"
}
if ([string]::IsNullOrWhiteSpace($EmbeddingVertexLocations)) {
    $EmbeddingVertexLocations = @(
        "asia-east1", "asia-east2", "asia-northeast1", "asia-northeast3",
        "asia-south1", "asia-southeast1", "australia-southeast1",
        "europe-central2", "europe-north1", "europe-southwest1",
        "europe-west1", "europe-west2", "europe-west3", "europe-west4",
        "europe-west6", "europe-west8", "europe-west9", "me-central1",
        "me-central2", "me-west1", "northamerica-northeast1",
        "southamerica-east1", "us-central1", "us-east1", "us-east4",
        "us-east5", "us-south1", "us-west1", "us-west4"
    ) -join "|"
}
$EmbeddingVertexLocations = (
    $EmbeddingVertexLocations -split "[,;|\s]+" |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
) -join "|"
if ($EmbeddingVertexRequestsPerMinute -le 0) {
    throw "EmbeddingVertexRequestsPerMinute must be greater than zero."
}
if ([string]::IsNullOrWhiteSpace($CorpusBucket)) {
    $CorpusBucket = "$ProjectId-vlegal-corpus"
}

$imageRoot = "$Region-docker.pkg.dev/$ProjectId/$Repository"
$backendImage = "$imageRoot/vlegal-backend`:$Tag"
$frontendImage = "$imageRoot/vlegal-frontend`:$Tag"
$apiService = "vlegal-api"
$frontendService = "vlegal-frontend"
$workerPool = "vlegal-worker"
$beatPool = "vlegal-beat"
$migrateJob = "vlegal-migrate"
$reindexJob = "vlegal-reindex"

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

function Get-PublicServiceUrl {
    param([Parameter(Mandatory)][string]$Name)
    $projectNumber = (& gcloud run services describe $Name --project=$ProjectId --region=$Region --format="value(metadata.namespace)").Trim()
    if ($LASTEXITCODE -ne 0 -or $projectNumber -notmatch "^\d+$") {
        throw "Không lấy được project number từ Cloud Run service $Name."
    }
    return "https://$Name-$projectNumber.$Region.run.app"
}

function Deploy-Migrate {
    Invoke-Gcloud @(
        "run", "jobs", "deploy", $migrateJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$backendImage",
        "--service-account=$RunServiceAccount",
        "--command=alembic",
        "--args=upgrade,head",
        "--cpu=1", "--memory=1Gi", "--task-timeout=15m", "--max-retries=1",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest",
        "--quiet"
    )
    if ($ExecuteJobs -or $ExecuteMigrate) {
        Invoke-Gcloud @("run", "jobs", "execute", $migrateJob, "--project=$ProjectId", "--region=$Region", "--wait")
    }
}

function Deploy-Reindex {
    $envVars = @(
        "APP_ENV=production",
        "LEGAL_DATA_DIR=/app/legal-data",
        "LEGAL_STORAGE_DIR=/tmp/graphrag",
        "LEGAL_GRAPHRAG_DB=/tmp/graphrag/legal_graphrag.sqlite",
        "GEMINI_USE_ADC=true",
        "GEMINI_PROJECT_ID=$ProjectId",
        "EMBEDDING_PROVIDER=vertex",
        "EMBEDDING_MODEL=gemini-embedding-001",
        "EMBEDDING_LOCATION=$EmbeddingLocation",
        "EMBEDDING_VERTEX_LOCATIONS=$EmbeddingVertexLocations",
        "EMBEDDING_VERTEX_REQUESTS_PER_MINUTE=$EmbeddingVertexRequestsPerMinute",
        "EMBEDDING_MAX_CONCURRENCY=32",
        "EMBEDDING_BATCH_SIZE=20",
        "EMBEDDING_TIMEOUT_SECONDS=60",
        "EMBEDDING_MAX_RETRIES=8",
        "LEGAL_EMBEDDING_CHECKPOINT_ENABLED=true",
        "LEGAL_EMBEDDING_CHECKPOINT_BATCH_SIZE=640",
        "EMBEDDING_AUTO_TRUNCATE=true",
        "GEMINI_DATA_POLICY=redact",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser",
        "NEO4J_DATABASE=$Neo4jDatabase"
    ) -join ","

    Invoke-Gcloud @(
        "run", "jobs", "deploy", $reindexJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$backendImage",
        "--service-account=$RunServiceAccount",
        "--command=python",
        "--args=scripts/sync_external_graphrag.py,--reset-neo4j,--reset-postgres",
        "--tasks=1", "--parallelism=1", "--max-retries=3", "--task-timeout=24h",
        "--cpu=4", "--memory=8Gi",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--add-volume=mount-path=/app/legal-data,type=cloud-storage,bucket=$CorpusBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--set-env-vars=$envVars",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest,NEO4J_PASSWORD=vlegal-neo4j-password:latest",
        "--quiet"
    )
    if ($ExecuteJobs -or $ExecuteReindex) {
        Invoke-Gcloud @("run", "jobs", "execute", $reindexJob, "--project=$ProjectId", "--region=$Region", "--wait")
    }
}

function Deploy-Api {
    $envVars = @(
        "APP_ENV=production",
        "GEMINI_USE_ADC=true",
        "GEMINI_PROJECT_ID=$ProjectId",
        "GEMINI_LOCATION=global",
        "GEMINI_MODEL=gemini-3.5-flash",
        "LEGAL_CHAT_GENERATION_TIMEOUT_SECONDS=12",
        "GEMINI_MAX_CONCURRENT_GENERATIONS=8",
        "EMBEDDING_PROVIDER=vertex",
        "EMBEDDING_MODEL=gemini-embedding-001",
        "EMBEDDING_LOCATION=$EmbeddingLocation",
        "EMBEDDING_VERTEX_LOCATIONS=$EmbeddingVertexLocations",
        "EMBEDDING_VERTEX_REQUESTS_PER_MINUTE=$EmbeddingVertexRequestsPerMinute",
        "EMBEDDING_VERTEX_MAX_QUEUE_WAIT_SECONDS=2",
        "EMBEDDING_MAX_CONCURRENCY=8",
        "EMBEDDING_BATCH_SIZE=20",
        "EMBEDDING_TIMEOUT_SECONDS=8",
        "EMBEDDING_MAX_RETRIES=1",
        "EMBEDDING_AUTO_TRUNCATE=true",
        "GEMINI_DATA_POLICY=redact",
        "WEB_CONCURRENCY=1",
        "DATABASE_POOL_SIZE=5",
        "DATABASE_MAX_OVERFLOW=5",
        "RETRIEVER_BACKEND=hybrid_rag",
        "REQUIRE_FRESHNESS_CHECK=false",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser",
        "NEO4J_DATABASE=$Neo4jDatabase"
    ) -join ","

    Invoke-Gcloud @(
        "run", "deploy", $apiService,
        "--project=$ProjectId", "--region=$Region",
        "--image=$backendImage",
        "--execution-environment=gen2", "--service-account=$RunServiceAccount", "--port=8080",
        "--cpu=2", "--memory=4Gi", "--concurrency=16",
        "--min=0", "--max=5", "--timeout=3600",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--allow-unauthenticated",
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
        "--image=$frontendImage",
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
        "GEMINI_USE_ADC=true",
        "GEMINI_PROJECT_ID=$ProjectId",
        "GEMINI_LOCATION=global",
        "GEMINI_MODEL=gemini-3.5-flash",
        "GEMINI_MAX_CONCURRENT_GENERATIONS=8",
        "EMBEDDING_PROVIDER=vertex",
        "EMBEDDING_MODEL=gemini-embedding-001",
        "EMBEDDING_LOCATION=$EmbeddingLocation",
        "EMBEDDING_VERTEX_LOCATIONS=$EmbeddingVertexLocations",
        "EMBEDDING_VERTEX_REQUESTS_PER_MINUTE=$EmbeddingVertexRequestsPerMinute",
        "EMBEDDING_MAX_CONCURRENCY=8",
        "EMBEDDING_BATCH_SIZE=20",
        "EMBEDDING_TIMEOUT_SECONDS=60",
        "EMBEDDING_MAX_RETRIES=8",
        "EMBEDDING_AUTO_TRUNCATE=true",
        "GEMINI_DATA_POLICY=redact",
        "DATABASE_POOL_SIZE=2",
        "DATABASE_MAX_OVERFLOW=2",
        "RETRIEVER_BACKEND=hybrid_rag",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser",
        "NEO4J_DATABASE=$Neo4jDatabase",
        "REQUIRE_FRESHNESS_CHECK=false"
    ) -join ","

    Invoke-Gcloud @(
        "run", "worker-pools", "deploy", $workerPool,
        "--project=$ProjectId", "--region=$Region", "--instances=$WorkerInstances",
        "--image=$backendImage", "--service-account=$RunServiceAccount",
        "--command=celery",
        "--args=-A,app.worker.celery_app,worker,--loglevel=INFO,--concurrency=1",
        "--cpu=2", "--memory=4Gi",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--set-env-vars=$envVars", "--set-secrets=$workerSecrets",
        "--quiet"
    )
}

function Deploy-Beat {
    Invoke-Gcloud @(
        "run", "worker-pools", "deploy", $beatPool,
        "--project=$ProjectId", "--region=$Region", "--instances=$BeatInstances",
        "--image=$backendImage", "--service-account=$RunServiceAccount",
        "--command=celery",
        "--args=-A,app.scheduler.celery_app,beat,--loglevel=INFO",
        "--cpu=1", "--memory=512Mi",
        "--network=$Network", "--subnet=$Subnet", "--vpc-egress=private-ranges-only",
        "--set-env-vars=APP_ENV=production",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest",
        "--quiet"
    )
}

switch ($Component) {
    "migrate" { Deploy-Migrate }
    "reindex" { Deploy-Reindex }
    "api" {
        Deploy-Api
        $externalUrl = if ($FrontendUrl) {
            $FrontendUrl.TrimEnd("/")
        } else {
            Get-PublicServiceUrl $frontendService
        }
        Set-ApiExternalUrl $externalUrl
        Write-Host "API URL: $(Get-ServiceUrl $apiService)"
    }
    "frontend" {
        $url = Deploy-Frontend
        $externalUrl = if ($FrontendUrl) {
            $FrontendUrl.TrimEnd("/")
        } else {
            Get-PublicServiceUrl $frontendService
        }
        Set-ApiExternalUrl $externalUrl
        Write-Host "Frontend URL: $externalUrl"
    }
    "worker" { Deploy-Worker }
    "beat" { Deploy-Beat }
    "all" {
        Deploy-Migrate
        Deploy-Reindex
        Deploy-Api
        $url = Deploy-Frontend
        $externalUrl = if ($FrontendUrl) {
            $FrontendUrl.TrimEnd("/")
        } else {
            Get-PublicServiceUrl $frontendService
        }
        Set-ApiExternalUrl $externalUrl
        Deploy-Worker
        Deploy-Beat
        Write-Host "Frontend URL: $externalUrl"
        Write-Host "API URL: $(Get-ServiceUrl $apiService)"
        Write-Host "OAuth redirect URI: $externalUrl/api/auth/google/callback"
    }
}
