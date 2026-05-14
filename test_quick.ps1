$tests = @(
    @{ name = "Root"; url = "http://127.0.0.1:5000/" },
    @{ name = "Providers"; url = "http://127.0.0.1:5000/api/providers" },
    @{ name = "LLM Config"; url = "http://127.0.0.1:5000/api/config/llm" },
    @{ name = "Skills"; url = "http://127.0.0.1:5000/api/skills" }
)
foreach ($t in $tests) {
    try {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $r = Invoke-WebRequest -Uri $t.url -TimeoutSec 20 -UseBasicParsing
        $sw.Stop()
        Write-Host "$($t.name): $($r.StatusCode) ($($sw.ElapsedMilliseconds)ms)"
    } catch {
        Write-Host "$($t.name): FAIL - $($_.Exception.Message.Substring(0, [Math]::Min(80, $_.Exception.Message.Length)))"
    }
}
