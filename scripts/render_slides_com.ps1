param(
    [Parameter(Mandatory=$true)][string]$InputPptx,
    [Parameter(Mandatory=$true)][string]$OutputDir
)

$ErrorActionPreference = "Stop"
$inputPath = (Resolve-Path -LiteralPath $InputPptx).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

$ppt = $null
$presentation = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $presentation = $ppt.Presentations.Open($inputPath, $false, $false, $false)
    $presentation.Export($outputPath, "PNG", 1600, 900)
    $count = $presentation.Slides.Count
    $presentation.Close()
    $presentation = $null
    $ppt.Quit()
    $ppt = $null
    Write-Output "Rendered $count slides to $outputPath"
}
finally {
    if ($null -ne $presentation) {
        try { $presentation.Close() } catch { }
    }
    if ($null -ne $ppt) {
        try { $ppt.Quit() } catch { }
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
