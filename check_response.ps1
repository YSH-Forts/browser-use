param([string]$Url, [string]$OutFile)
try {
    $r = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing
    Write-Host "Status: $($r.StatusCode)"
    Write-Host "Content-Length: $($r.Content.Length)"
    if ($r.Content.Length -gt 0) {
        Write-Host "First 500 chars:"
        Write-Host $r.Content.Substring(0, [Math]::Min(500, $r.Content.Length))
    } else {
        Write-Host "Content is empty!"
    }
    if ($OutFile) {
        $r.Content | Out-File -FilePath $OutFile -Encoding utf8
        Write-Host "Full content saved to $OutFile"
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}
