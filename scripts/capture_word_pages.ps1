param(
    [Parameter(Mandatory = $true)]
    [string]$DocumentPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

if (-not ("WordPageCaptureNative" -as [type])) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class WordPageCaptureNative
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint flags);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int command);

    [DllImport("user32.dll")]
    public static extern bool MoveWindow(
        IntPtr hWnd,
        int x,
        int y,
        int width,
        int height,
        bool repaint
    );
}
"@
}

$resolvedDocument = (Resolve-Path -LiteralPath $DocumentPath).Path
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null
Get-ChildItem -LiteralPath $resolvedOutput -Filter "page-*-raw.png" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force

$word = New-Object -ComObject Word.Application
$word.Visible = $true
$word.DisplayAlerts = 0

try {
    $document = $word.Documents.Open($resolvedDocument, $false, $true)
    $window = $word.ActiveWindow
    $window.WindowState = 0
    $window.View.Type = 3
    $window.View.Zoom.PageFit = 0
    $window.View.Zoom.Percentage = 48

    $handle = [IntPtr]$window.Hwnd
    [void][WordPageCaptureNative]::ShowWindow($handle, 1)
    Start-Sleep -Milliseconds 600

    $pageCount = $document.ComputeStatistics(2)
    for ($page = 1; $page -le $pageCount; $page++) {
        $pageRange = $document.GoTo(1, 1, $page)
        $pageRange.Select()
        $pageWidthPoints = [double]$pageRange.Sections.Item(1).PageSetup.PageWidth
        $targetWidth = [Math]::Min(
            1500,
            [Math]::Max(720, [Math]::Ceiling($pageWidthPoints * 1.6667 * 0.48 + 190))
        )
        if (-not [WordPageCaptureNative]::MoveWindow(
            $handle,
            0,
            0,
            [int]$targetWidth,
            830,
            $true
        )) {
            throw "Could not resize the Word window for page $page."
        }
        $window.View.Zoom.PageFit = 0
        $window.View.Zoom.Percentage = 48
        Start-Sleep -Milliseconds 350

        $rect = New-Object WordPageCaptureNative+RECT
        if (-not [WordPageCaptureNative]::GetWindowRect($handle, [ref]$rect)) {
            throw "Could not read the Word window rectangle for page $page."
        }

        $width = $rect.Right - $rect.Left
        $height = $rect.Bottom - $rect.Top
        $bitmap = New-Object System.Drawing.Bitmap($width, $height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $deviceContext = $graphics.GetHdc()
        try {
            if (-not [WordPageCaptureNative]::PrintWindow($handle, $deviceContext, 2)) {
                throw "PrintWindow failed for page $page."
            }
        }
        finally {
            $graphics.ReleaseHdc($deviceContext)
            $graphics.Dispose()
        }

        $outputFile = Join-Path $resolvedOutput ("page-{0:D3}-raw.png" -f $page)
        $bitmap.Save($outputFile, [System.Drawing.Imaging.ImageFormat]::Png)
        $bitmap.Dispose()
    }

    [pscustomobject]@{
        Pages = $pageCount
        OutputDirectory = $resolvedOutput
    }
}
finally {
    if ($null -ne $document) {
        try { $document.Close($false) } catch {}
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
    }
    try { $word.Quit() } catch {}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
