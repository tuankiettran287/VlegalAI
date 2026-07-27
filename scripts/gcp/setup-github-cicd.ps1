[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ProjectId,

    [ValidatePattern("^\d+$")]
    [string]$GitHubRepositoryId = "1299341579",

    [ValidatePattern("^\d+$")]
    [string]$GitHubRepositoryOwnerId = "148296828",

    [string]$Region = "asia-southeast1",
    [ValidatePattern("^[A-Za-z0-9._/-]+$")]
    [string]$Branch = "master",
    [ValidatePattern("^[a-z][a-z0-9-]{3,31}$")]
    [string]$PoolId = "github-actions",
    [ValidatePattern("^[a-z][a-z0-9-]{3,31}$")]
    [string]$ProviderId = "vlegal",
    [ValidatePattern("^[a-z][a-z0-9-]{4,28}[a-z0-9]$")]
    [string]$DeployServiceAccountName = "vlegal-github-deploy",
    [ValidatePattern("^[a-z][a-z0-9-]{4,28}[a-z0-9]$")]
    [string]$RuntimeServiceAccountName = "vlegal-run",
    [string]$ArtifactRepository = "vlegal",
    [string]$CorpusBucket = "",
    [string]$Network = "default",
    [string]$Subnet = "default"
)

$ErrorActionPreference = "Stop"

function Invoke-Gcloud {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "gcloud failed: gcloud $($Arguments -join ' ')"
    }
}

function Test-GcloudResource {
    param([Parameter(Mandatory)][string[]]$Arguments)

    & gcloud @Arguments *> $null
    return $LASTEXITCODE -eq 0
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "Google Cloud CLI (gcloud) is required."
}

if ([string]::IsNullOrWhiteSpace($CorpusBucket)) {
    $CorpusBucket = "$ProjectId-vlegal-corpus"
}

$projectNumber = (
    & gcloud projects describe $ProjectId --format="value(projectNumber)"
).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($projectNumber)) {
    throw "Cannot resolve project number for $ProjectId."
}

$deployServiceAccount = "$DeployServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$runtimeServiceAccount = "$RuntimeServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$cloudRunServiceAgent = "service-$projectNumber@serverless-robot-prod.iam.gserviceaccount.com"

Invoke-Gcloud @(
    "services", "enable",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "compute.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "--project=$ProjectId",
    "--quiet"
)

if (-not (Test-GcloudResource @(
    "compute", "networks", "describe", $Network,
    "--project=$ProjectId"
))) {
    throw "VPC network '$Network' does not exist in project $ProjectId."
}
if (-not (Test-GcloudResource @(
    "compute", "networks", "subnets", "describe", $Subnet,
    "--project=$ProjectId",
    "--region=$Region"
))) {
    throw "Subnet '$Subnet' does not exist in region $Region."
}

if (-not (Test-GcloudResource @(
    "iam", "service-accounts", "describe", $deployServiceAccount,
    "--project=$ProjectId"
))) {
    Invoke-Gcloud @(
        "iam", "service-accounts", "create", $DeployServiceAccountName,
        "--project=$ProjectId",
        "--display-name=VLegalAI GitHub deployment",
        "--quiet"
    )
}

if (-not (Test-GcloudResource @(
    "iam", "service-accounts", "describe", $runtimeServiceAccount,
    "--project=$ProjectId"
))) {
    Invoke-Gcloud @(
        "iam", "service-accounts", "create", $RuntimeServiceAccountName,
        "--project=$ProjectId",
        "--display-name=VLegalAI Cloud Run runtime",
        "--quiet"
    )
}

if (-not (Test-GcloudResource @(
    "artifacts", "repositories", "describe", $ArtifactRepository,
    "--project=$ProjectId",
    "--location=$Region"
))) {
    Invoke-Gcloud @(
        "artifacts", "repositories", "create", $ArtifactRepository,
        "--project=$ProjectId",
        "--location=$Region",
        "--repository-format=docker",
        "--description=VLegalAI application images",
        "--quiet"
    )
}

if (-not (Test-GcloudResource @(
    "storage", "buckets", "describe", "gs://$CorpusBucket",
    "--project=$ProjectId"
))) {
    Invoke-Gcloud @(
        "storage", "buckets", "create", "gs://$CorpusBucket",
        "--project=$ProjectId",
        "--location=$Region",
        "--uniform-bucket-level-access",
        "--quiet"
    )
}

if (-not (Test-GcloudResource @(
    "iam", "workload-identity-pools", "describe", $PoolId,
    "--project=$ProjectId",
    "--location=global"
))) {
    Invoke-Gcloud @(
        "iam", "workload-identity-pools", "create", $PoolId,
        "--project=$ProjectId",
        "--location=global",
        "--display-name=GitHub Actions",
        "--description=OIDC identities for VLegalAI deployments",
        "--quiet"
    )
}

$attributeMapping = @(
    "google.subject=assertion.sub",
    "attribute.repository_id=assertion.repository_id",
    "attribute.repository_owner_id=assertion.repository_owner_id",
    "attribute.ref=assertion.ref"
) -join ","
$attributeCondition = @(
    "assertion.repository_id == '$GitHubRepositoryId'",
    "assertion.repository_owner_id == '$GitHubRepositoryOwnerId'",
    "assertion.ref == 'refs/heads/$Branch'"
) -join " && "

$providerArguments = @(
    "--project=$ProjectId",
    "--location=global",
    "--workload-identity-pool=$PoolId",
    "--display-name=VLegalAI GitHub",
    "--issuer-uri=https://token.actions.githubusercontent.com",
    "--attribute-mapping=$attributeMapping",
    "--attribute-condition=$attributeCondition",
    "--quiet"
)

if (Test-GcloudResource @(
    "iam", "workload-identity-pools", "providers", "describe", $ProviderId,
    "--project=$ProjectId",
    "--location=global",
    "--workload-identity-pool=$PoolId"
)) {
    Invoke-Gcloud (@(
        "iam", "workload-identity-pools", "providers", "update-oidc", $ProviderId
    ) + $providerArguments)
}
else {
    Invoke-Gcloud (@(
        "iam", "workload-identity-pools", "providers", "create-oidc", $ProviderId
    ) + $providerArguments)
}

$projectBindings = @(
    @($deployServiceAccount, "roles/artifactregistry.writer"),
    @($deployServiceAccount, "roles/run.admin"),
    @($deployServiceAccount, "roles/serviceusage.serviceUsageConsumer"),
    @($runtimeServiceAccount, "roles/aiplatform.user"),
    @($runtimeServiceAccount, "roles/secretmanager.secretAccessor"),
    @($runtimeServiceAccount, "roles/serviceusage.serviceUsageConsumer"),
    @($cloudRunServiceAgent, "roles/compute.networkUser")
)
foreach ($binding in $projectBindings) {
    Invoke-Gcloud @(
        "projects", "add-iam-policy-binding", $ProjectId,
        "--member=serviceAccount:$($binding[0])",
        "--role=$($binding[1])",
        "--condition=None",
        "--quiet"
    )
}

Invoke-Gcloud @(
    "storage", "buckets", "add-iam-policy-binding", "gs://$CorpusBucket",
    "--member=serviceAccount:$runtimeServiceAccount",
    "--role=roles/storage.objectViewer",
    "--quiet"
)

Invoke-Gcloud @(
    "iam", "service-accounts", "add-iam-policy-binding", $runtimeServiceAccount,
    "--project=$ProjectId",
    "--member=serviceAccount:$deployServiceAccount",
    "--role=roles/iam.serviceAccountUser",
    "--quiet"
)

$workloadIdentityPoolName = (
    & gcloud iam workload-identity-pools describe $PoolId `
        --project=$ProjectId `
        --location=global `
        --format="value(name)"
).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($workloadIdentityPoolName)) {
    throw "Cannot resolve the Workload Identity Pool resource name."
}

$githubPrincipal = "principalSet://iam.googleapis.com/$workloadIdentityPoolName/attribute.repository_id/$GitHubRepositoryId"
Invoke-Gcloud @(
    "iam", "service-accounts", "add-iam-policy-binding", $deployServiceAccount,
    "--project=$ProjectId",
    "--member=$githubPrincipal",
    "--role=roles/iam.workloadIdentityUser",
    "--quiet"
)

$providerName = (
    & gcloud iam workload-identity-pools providers describe $ProviderId `
        --project=$ProjectId `
        --location=global `
        --workload-identity-pool=$PoolId `
        --format="value(name)"
).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($providerName)) {
    throw "Cannot resolve the Workload Identity Provider resource name."
}

Write-Host ""
Write-Host "GCP bootstrap completed. Configure the GitHub environment 'production' with:"
Write-Host ""
Write-Host "Variables:"
Write-Host "  GCP_PROJECT_ID=$ProjectId"
Write-Host "  GCP_REGION=$Region"
Write-Host "  GCP_EMBEDDING_LOCATION=$Region"
Write-Host "  GCP_REPOSITORY=$ArtifactRepository"
Write-Host "  GCP_RUN_SERVICE_ACCOUNT=$runtimeServiceAccount"
Write-Host "  GCP_DEPLOY_SERVICE_ACCOUNT=$deployServiceAccount"
Write-Host "  GCP_WORKLOAD_IDENTITY_PROVIDER=$providerName"
Write-Host "  GCP_CORPUS_BUCKET=$CorpusBucket"
Write-Host "  GCP_NETWORK=$Network"
Write-Host "  GCP_SUBNET=$Subnet"
Write-Host ""
Write-Host "Secret:"
Write-Host "  NEO4J_URI=<your Neo4j URI>"
Write-Host ""
Write-Host "The OIDC provider accepts only repository ID $GitHubRepositoryId, owner ID"
Write-Host "$GitHubRepositoryOwnerId and branch refs/heads/$Branch."
