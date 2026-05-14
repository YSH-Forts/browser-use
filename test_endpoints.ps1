$tests = @(
    @{ name = "Root"; url = "http://127.0.0.1:5000/" },
    @{ name = "Providers"; url = "http://127.0.0.1:5000/api/providers" },
    @{ name = "Skills"; url = "http://127.0.0.1:5000/api/skills" },
    @{ name = "LLM Config"; url = "http://127.0.0.1:5000/api/config/llm" }
)
foreach ($t in $tests) {
    try {
        $r = Invoke-WebRequest -Uri $t.url -TimeoutSec 8 -UseBasicParsing
        Write-Host "$($t.name): $($r.StatusCode) ($($r.Content.Length) bytes)"
    } catch {
        Write-Host "$($t.name): ERROR - $($_.Exception.Message)"
    }
}
