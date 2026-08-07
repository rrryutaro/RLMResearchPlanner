$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null

function Wait-WinRtResult($operation, [Type]$resultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1
    $task = $method.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.Wait()
    return $task.Result
}

$randomAccessStream = $null
$writer = $null
$bitmap = $null
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $pngBytes = [Convert]::FromBase64String([string]$request.png_base64)
    $language = [Windows.Globalization.Language]::new([string]$request.locale)
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
    if ($null -eq $engine) {
        throw "Windows OCR language is not installed: $($request.locale)"
    }

    $randomAccessStream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
    $writer = [Windows.Storage.Streams.DataWriter]::new(
        $randomAccessStream.GetOutputStreamAt(0)
    )
    $writer.WriteBytes($pngBytes)
    Wait-WinRtResult ($writer.StoreAsync()) ([UInt32]) | Out-Null
    $writer.DetachStream() | Out-Null
    $writer.Dispose()
    $writer = $null
    $randomAccessStream.Seek(0)

    $decoder = Wait-WinRtResult (
        [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($randomAccessStream)
    ) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Wait-WinRtResult (
        $decoder.GetSoftwareBitmapAsync()
    ) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Wait-WinRtResult (
        $engine.RecognizeAsync($bitmap)
    ) ([Windows.Media.Ocr.OcrResult])

    $lines = @()
    foreach ($line in $result.Lines) {
        $words = @($line.Words)
        if ($words.Count -eq 0) {
            continue
        }
        $left = ($words | ForEach-Object { $_.BoundingRect.X } | Measure-Object -Minimum).Minimum
        $top = ($words | ForEach-Object { $_.BoundingRect.Y } | Measure-Object -Minimum).Minimum
        $right = ($words | ForEach-Object {
            $_.BoundingRect.X + $_.BoundingRect.Width
        } | Measure-Object -Maximum).Maximum
        $bottom = ($words | ForEach-Object {
            $_.BoundingRect.Y + $_.BoundingRect.Height
        } | Measure-Object -Maximum).Maximum
        $lines += [PSCustomObject]@{
            text = [string]$line.Text
            x = [double]$left
            y = [double]$top
            width = [double]($right - $left)
            height = [double]($bottom - $top)
        }
    }

    [PSCustomObject]@{
        text = [string]$result.Text
        lines = $lines
    } | ConvertTo-Json -Depth 5 -Compress
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($null -ne $writer) {
        $writer.Dispose()
    }
    if ($null -ne $bitmap) {
        $bitmap.Dispose()
    }
    if ($null -ne $randomAccessStream) {
        $randomAccessStream.Dispose()
    }
}
