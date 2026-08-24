[CmdletBinding()]
param(
    [string]$MermaidCli = "@mermaid-js/mermaid-cli"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Join-Path $root "src"
$outputDir = Join-Path $root "pdf"
$config = Join-Path $root "mermaid-config.json"
$puppeteerConfig = Join-Path $root "puppeteer-config.json"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$sources = Get-ChildItem -LiteralPath $sourceDir -Filter "*.mmd" -File |
    Sort-Object Name

if ($sources.Count -ne 25) {
    throw "Expected 25 Mermaid sources, found $($sources.Count)."
}

foreach ($source in $sources) {
    $output = Join-Path $outputDir ($source.BaseName + ".pdf")
    # Resolve the executable explicitly.  Recent npx versions do not always
    # infer `mmdc` from a scoped package name when it is stored in a variable.
    & npx.cmd --yes "--package=$MermaidCli" mmdc `
        --input $source.FullName `
        --output $output `
        --configFile $config `
        --puppeteerConfigFile $puppeteerConfig `
        --pdfFit `
        --quiet

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $output)) {
        throw "Mermaid vector render failed for $($source.Name)."
    }
}

$outputs = Get-ChildItem -LiteralPath $outputDir -Filter "*.pdf" -File
if ($outputs.Count -ne $sources.Count) {
    throw "Vector output count mismatch: source=$($sources.Count), pdf=$($outputs.Count)."
}

Write-Host "Rendered $($outputs.Count) code-defined Mermaid diagrams to $outputDir"
