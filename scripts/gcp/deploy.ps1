[CmdletBinding()]
param(
    [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
    [string]$Region = "asia-southeast1",
    [string]$EmbeddingLocation = "",
    [string]$EmbeddingVertexLocations = $env:EMBEDDING_VERTEX_LOCATIONS,
    [double]$EmbeddingVertexRequestsPerMinute = 4.5,
    [string]$Repository = "vlegal",
    [string]$Tag = "",
    [ValidatePattern("^[a-z][a-z0-9-]{0,47}[a-z0-9]$")]
    [string]$ServiceName = "vlegalai",
    [string]$RunServiceAccount = "",
    [string]$CorpusBucket = "",
    [string]$CloudSqlInstance = $env:GCP_CLOUD_SQL_INSTANCE,
    [string]$Neo4jUri = $env:NEO4J_URI,
    [string]$Neo4jUser = $env:NEO4J_USER,
    [string]$Neo4jDatabase = $env:NEO4J_DATABASE,
    [string]$ExternalUrl = "",
    [ValidateSet("all", "migrate", "reindex", "article", "web", "api", "worker", "beat")]
    [string]$Component = "all",
    [switch]$ExecuteMigrate,
    [switch]$ExecuteReindex,
    [switch]$ExecuteArticlePublish,
    [switch]$ExecuteJobs
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    throw "Truyền -ProjectId hoặc đặt GOOGLE_CLOUD_PROJECT."
}
if ([string]::IsNullOrWhiteSpace($Neo4jUri) -and $Component -in @("all", "reindex", "web", "api", "worker")) {
    throw "Truyền -Neo4jUri hoặc đặt NEO4J_URI."
}
if (
    -not [string]::IsNullOrWhiteSpace($Neo4jUri) -and
    (
        [string]::IsNullOrWhiteSpace($Neo4jUser) -or
        [string]::IsNullOrWhiteSpace($Neo4jDatabase)
    )
) {
    try {
        $neo4jInstanceId = ([uri]$Neo4jUri).Host.Split(".")[0]
    }
    catch {
        throw "Neo4jUri không hợp lệ; không thể suy ra Neo4jUser/Neo4jDatabase."
    }
    if ([string]::IsNullOrWhiteSpace($neo4jInstanceId)) {
        throw "Truyền Neo4jUser và Neo4jDatabase."
    }
    if ([string]::IsNullOrWhiteSpace($Neo4jUser)) {
        $Neo4jUser = $neo4jInstanceId
    }
    if ([string]::IsNullOrWhiteSpace($Neo4jDatabase)) {
        $Neo4jDatabase = $neo4jInstanceId
    }
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
    throw "EmbeddingVertexRequestsPerMinute must be greater than zero for the regional Vertex pool."
}
if ([string]::IsNullOrWhiteSpace($CorpusBucket)) {
    $CorpusBucket = "$ProjectId-vlegal-corpus"
}

$imageRoot = "$Region-docker.pkg.dev/$ProjectId/$Repository"
$appImage = "$imageRoot/vlegal-app`:$Tag"
$webService = $ServiceName
$workerPool = "vlegal-worker"
$beatPool = "vlegal-beat"
$migrateJob = "vlegal-migrate"
$reindexJob = "vlegal-reindex"
$articleJob = "vlegal-publish-article"

$apiSecrets = @(
    "DATABASE_URL=vlegal-database-url:latest",
    "NEO4J_PASSWORD=vlegal-neo4j-password:latest",
    "GEMINI_API_KEY=vlegal-gemini-api-key:latest",
    "SESSION_SECRET=vlegal-session-secret:latest",
    "MESSAGE_ENCRYPTION_KEY=vlegal-message-key:latest",
    "OIDC_CLIENT_ID=vlegal-oidc-client-id:latest",
    "OIDC_CLIENT_SECRET=vlegal-oidc-client-secret:latest",
    "TAVILY_API_KEY=vlegal-tavily-key:latest"
) -join ","

$workerSecrets = @(
    "DATABASE_URL=vlegal-database-url:latest",
    "NEO4J_PASSWORD=vlegal-neo4j-password:latest",
    "GEMINI_API_KEY=vlegal-gemini-api-key:latest",
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
    $serviceJson = & gcloud run services describe $Name --project=$ProjectId --region=$Region --format=json
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($serviceJson)) {
        throw "Không lấy được URL của Cloud Run service $Name."
    }

    try {
        $service = $serviceJson | ConvertFrom-Json
        $projectNumber = [string]$service.metadata.namespace
        $urlsJson = [string]$service.metadata.annotations.'run.googleapis.com/urls'
        $urls = if ([string]::IsNullOrWhiteSpace($urlsJson)) {
            @()
        }
        else {
            $decodedUrls = $urlsJson | ConvertFrom-Json
            @(
                foreach ($candidateUrl in $decodedUrls) {
                    [string]$candidateUrl
                }
            )
        }
        $projectNumberUrl = $urls |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($projectNumber) -and
                ([uri]$_).Host -like "*-$projectNumber.*"
            } |
            Select-Object -First 1
        if (-not [string]::IsNullOrWhiteSpace($projectNumberUrl)) {
            return [string]$projectNumberUrl
        }

        $statusUrl = [string]$service.status.url
        if (-not [string]::IsNullOrWhiteSpace($statusUrl)) {
            return $statusUrl
        }
    }
    catch {
        throw "Cloud Run trả về cấu trúc URL không hợp lệ cho service ${Name}: $($_.Exception.Message)"
    }

    throw "Không lấy được URL của Cloud Run service $Name."
}

function Deploy-Migrate {
    $arguments = @(
        "run", "jobs", "deploy", $migrateJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$appImage",
        "--service-account=$RunServiceAccount",
        "--command=alembic",
        "--args=upgrade,head",
        "--cpu=1", "--memory=1Gi", "--task-timeout=15m", "--max-retries=1",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest",
        "--quiet"
    )
    if (-not [string]::IsNullOrWhiteSpace($CloudSqlInstance)) {
        $arguments += "--set-cloudsql-instances=$CloudSqlInstance"
    }
    Invoke-Gcloud $arguments
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
        "LEGAL_EMBEDDING_CHECKPOINT_ENABLED=true",
        "LEGAL_EMBEDDING_CHECKPOINT_BATCH_SIZE=640",
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
        "EMBEDDING_AUTO_TRUNCATE=true",
        "GEMINI_DATA_POLICY=redact",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser",
        "NEO4J_DATABASE=$Neo4jDatabase"
    ) -join ","

    $arguments = @(
        "run", "jobs", "deploy", $reindexJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$appImage",
        "--service-account=$RunServiceAccount",
        "--command=python",
        "--args=scripts/sync_external_graphrag.py,--reset-neo4j,--reset-postgres",
        "--tasks=1", "--parallelism=1", "--max-retries=0", "--task-timeout=24h",
        "--cpu=4", "--memory=8Gi",
        "--add-volume=name=legal-data,type=cloud-storage,bucket=$CorpusBucket,readonly=true,mount-options=uid=10001;gid=10001",
        "--add-volume-mount=volume=legal-data,mount-path=/app/legal-data",
        "--set-env-vars=$envVars",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest,NEO4J_PASSWORD=vlegal-neo4j-password:latest",
        "--quiet"
    )
    if (-not [string]::IsNullOrWhiteSpace($CloudSqlInstance)) {
        $arguments += "--set-cloudsql-instances=$CloudSqlInstance"
    }
    Invoke-Gcloud $arguments
    if ($ExecuteJobs -or $ExecuteReindex) {
        Invoke-Gcloud @("run", "jobs", "execute", $reindexJob, "--project=$ProjectId", "--region=$Region", "--wait")
    }
}

function Deploy-ArticlePublisher {
    $envVars = @(
        "APP_ENV=production",
        "LOG_LEVEL=INFO",
        "GEMINI_USE_ADC=true",
        "GEMINI_PROJECT_ID=$ProjectId",
        "GEMINI_LOCATION=global",
        "GEMINI_MODEL=gemini-2.5-flash",
        "GEMINI_MAX_CONCURRENT_GENERATIONS=2",
        "GEMINI_DATA_POLICY=redact",
        "DATABASE_POOL_SIZE=2",
        "DATABASE_MAX_OVERFLOW=2"
    ) -join ","

    $arguments = @(
        "run", "jobs", "deploy", $articleJob,
        "--project=$ProjectId", "--region=$Region",
        "--image=$appImage",
        "--service-account=$RunServiceAccount",
        "--command=python",
        "--args=scripts/publish_daily_article.py",
        "--tasks=1", "--parallelism=1", "--max-retries=1", "--task-timeout=45m",
        "--cpu=2", "--memory=2Gi",
        "--set-env-vars=$envVars",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest,GEMINI_API_KEY=vlegal-gemini-api-key:latest,TAVILY_API_KEY=vlegal-tavily-key:latest",
        "--quiet"
    )
    if (-not [string]::IsNullOrWhiteSpace($CloudSqlInstance)) {
        $arguments += "--set-cloudsql-instances=$CloudSqlInstance"
    }
    Invoke-Gcloud $arguments
    if ($ExecuteJobs -or $ExecuteArticlePublish) {
        Invoke-Gcloud @("run", "jobs", "execute", $articleJob, "--project=$ProjectId", "--region=$Region", "--wait")
    }
}

function Deploy-Web {
    $envVars = @(
        "APP_ENV=production",
        "LOG_LEVEL=INFO",
        "GEMINI_USE_ADC=true",
        "GEMINI_PROJECT_ID=$ProjectId",
        "GEMINI_LOCATION=global",
        "GEMINI_MODEL=gemini-2.5-flash",
        "LEGAL_CHAT_FAST_MODEL=gemini-2.5-flash",
        "LEGAL_CHAT_FAST_TIMEOUT_SECONDS=8",
        "LEGAL_CHAT_CITATION_REPAIR_TIMEOUT_SECONDS=2.5",
        "LEGAL_CHAT_GENERATION_TIMEOUT_SECONDS=12",
        "GEMINI_MAX_CONCURRENT_GENERATIONS=8",
        "QUERY_REWRITE_ENABLED=false",
        "QUERY_REWRITE_TIMEOUT_SECONDS=12",
        "QUERY_REWRITE_MIN_CONFIDENCE=0.75",
        "REQUIRE_FRESHNESS_CHECK=false",
        "LEGAL_FRESHNESS_TIMEOUT_SECONDS=90",
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
        "RETRIEVAL_POSTGRES_POOL_SIZE=3",
        "RETRIEVER_BACKEND=hybrid_rag",
        "POSTGRES_VECTOR_SIZE=1024",
        "NEO4J_URI=$Neo4jUri",
        "NEO4J_USER=$Neo4jUser",
        "NEO4J_DATABASE=$Neo4jDatabase",
        "FRONTEND_DIST_DIR=/app/frontend-dist"
    ) -join ","

    $arguments = @(
        "run", "deploy", $webService,
        "--project=$ProjectId", "--region=$Region",
        "--image=$appImage",
        "--execution-environment=gen2", "--service-account=$RunServiceAccount", "--port=8080",
        "--cpu=2", "--memory=4Gi", "--concurrency=16",
        "--min=0", "--max=5", "--timeout=3600",
        "--allow-unauthenticated",
        "--set-env-vars=$envVars", "--set-secrets=$apiSecrets",
        "--quiet"
    )
    if (-not [string]::IsNullOrWhiteSpace($CloudSqlInstance)) {
        $arguments += "--set-cloudsql-instances=$CloudSqlInstance"
    }
    Invoke-Gcloud $arguments
}

function Set-WebExternalUrl {
    param([Parameter(Mandatory)][string]$Url)
    Invoke-Gcloud @(
        "run", "services", "update", $webService,
        "--project=$ProjectId", "--region=$Region",
        "--update-env-vars=PUBLIC_URL=$Url,FRONTEND_URL=$Url,CORS_ORIGINS=$Url,OIDC_REDIRECT_URI=$Url/api/auth/google/callback,COOKIE_SECURE=true",
        "--quiet"
    )
}

function Deploy-Worker {
    $envVars = @(
        "APP_ENV=production",
        "LOG_LEVEL=INFO",
        "GEMINI_USE_ADC=true",
        "GEMINI_PROJECT_ID=$ProjectId",
        "GEMINI_LOCATION=global",
        "GEMINI_MODEL=gemini-2.5-flash",
        "GEMINI_MAX_CONCURRENT_GENERATIONS=8",
        "LEGAL_FRESHNESS_TIMEOUT_SECONDS=90",
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
        "NEO4J_DATABASE=$Neo4jDatabase"
    ) -join ","

    $arguments = @(
        "run", "worker-pools", "deploy", $workerPool,
        "--project=$ProjectId", "--region=$Region", "--instances=1",
        "--image=$appImage", "--service-account=$RunServiceAccount",
        "--command=celery",
        "--args=-A,app.worker.celery_app,worker,--loglevel=INFO,--concurrency=1",
        "--cpu=2", "--memory=4Gi",
        "--set-env-vars=$envVars", "--set-secrets=$workerSecrets",
        "--quiet"
    )
    if (-not [string]::IsNullOrWhiteSpace($CloudSqlInstance)) {
        $arguments += "--set-cloudsql-instances=$CloudSqlInstance"
    }
    Invoke-Gcloud $arguments
}

function Deploy-Beat {
    $arguments = @(
        "run", "worker-pools", "deploy", $beatPool,
        "--project=$ProjectId", "--region=$Region", "--instances=1",
        "--image=$appImage", "--service-account=$RunServiceAccount",
        "--command=celery",
        "--args=-A,app.scheduler.celery_app,beat,--loglevel=INFO",
        "--cpu=1", "--memory=512Mi",
        "--set-env-vars=APP_ENV=production",
        "--set-secrets=DATABASE_URL=vlegal-database-url:latest",
        "--quiet"
    )
    if (-not [string]::IsNullOrWhiteSpace($CloudSqlInstance)) {
        $arguments += "--set-cloudsql-instances=$CloudSqlInstance"
    }
    Invoke-Gcloud $arguments
}

switch ($Component) {
    "migrate" { Deploy-Migrate }
    "reindex" { Deploy-Reindex }
    "article" { Deploy-ArticlePublisher }
    { $_ -in @("web", "api") } {
        Deploy-Web
        $resolvedExternalUrl = if ($ExternalUrl) { $ExternalUrl } else { Get-ServiceUrl $webService }
        Set-WebExternalUrl $resolvedExternalUrl
        Write-Host "Service URL: $(Get-ServiceUrl $webService)"
    }
    "worker" { Deploy-Worker }
    "beat" { Deploy-Beat }
    "all" {
        Deploy-Migrate
        Deploy-Reindex
        Deploy-ArticlePublisher
        Deploy-Web
        $url = Get-ServiceUrl $webService
        Set-WebExternalUrl $url
        Deploy-Worker
        Deploy-Beat
        Write-Host "Service URL: $url"
        Write-Host "OAuth redirect URI: $url/api/auth/google/callback"
    }
}
