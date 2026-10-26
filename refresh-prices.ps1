# Read the stores' feeds from THIS PC and ingest them on the server.
#
# Why this is not done by the server itself: Shopify refuses it (HTTP 429)
# since 2026-09-30. The full story is in backend/scripts/offsite_scrape.py.
#
# Scraped prices leave the site 48 hours after they were last read, so run
# this at least once a day. It takes about ten minutes.
#
#   ssh-add                 # load the key (asks for its passphrase)
#   .\refresh-prices.ps1
#   ssh-add -D              # put the key back behind its passphrase

$server = "root@2.28.103.13"
$feeds = Join-Path $env:TEMP "ahsan-feeds.jsonl.gz"

Push-Location (Join-Path $PSScriptRoot "backend")
try {
    & .\.venv\Scripts\python.exe scripts\offsite_scrape.py record $feeds
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "A store did not read to its end. What was read is still ingested; nothing is delisted for that store."
    }
    if (-not (Test-Path $feeds)) { throw "Nothing was recorded." }

    scp -q $feeds scripts\offsite_scrape.py "${server}:/tmp/"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed. Is the SSH key loaded? Run: ssh-add" }

    # Single quotes: every $ below is for the server's shell, not PowerShell.
    # NO DOUBLE QUOTES INSIDE IT: Windows PowerShell strips them when it hands
    # the string to ssh, and a quoted grep pattern containing | then reaches
    # the server as three piped commands ("^result:: command not found").
    ssh $server 'cd /opt/ahsan-se3r && W=$(docker compose -f deploy/docker-compose.yml ps -q worker) && docker cp -q /tmp/ahsan-feeds.jsonl.gz $W:/tmp/ && docker cp -q /tmp/offsite_scrape.py $W:/tmp/ && docker compose -f deploy/docker-compose.yml exec -T -e PYTHONPATH=/app worker python /tmp/offsite_scrape.py replay /tmp/ahsan-feeds.jsonl.gz 2>&1 | grep -e ^job -e ^result: -e ^error:; rm -f /tmp/ahsan-feeds.jsonl.gz /tmp/offsite_scrape.py'
}
finally {
    Pop-Location
    Remove-Item $feeds -ErrorAction SilentlyContinue
}
