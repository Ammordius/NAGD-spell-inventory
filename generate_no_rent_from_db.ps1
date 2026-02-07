# PowerShell script to query TAKP database for no-rent items
# and generate no_rent_items.json

param(
    [string]$DatabaseName = "peq",
    [string]$DatabaseUser = "root",
    [string]$DatabaseHost = "localhost",
    [int]$DatabasePort = 3306
)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Generating No-Rent Items List" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Find MySQL executable
$mysqlExe = "mysql"
$found = Get-Command mysql -ErrorAction SilentlyContinue
if (-not $found) {
    $possiblePaths = @(
        "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
        "C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
        "C:\Program Files\MariaDB\*\bin\mysql.exe",
        "C:\xampp\mysql\bin\mysql.exe",
        "C:\wamp\bin\mysql\*\bin\mysql.exe"
    )
    
    foreach ($path in $possiblePaths) {
        $found = Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $mysqlExe = $found.FullName
            Write-Host "Found MySQL at: $mysqlExe" -ForegroundColor Green
            break
        }
    }
}

if (-not (Get-Command $mysqlExe -ErrorAction SilentlyContinue) -and -not (Test-Path $mysqlExe)) {
    Write-Host "Error: MySQL client not found. Please install MySQL or MariaDB." -ForegroundColor Red
    exit 1
}

# Check if password is needed (try without first)
Write-Host ""
Write-Host "Querying database for no-rent items (norent = 0)..." -ForegroundColor Yellow

# Run query and capture output
$outputFile = "no_rent_items_temp.txt"
$query = "SELECT id FROM items WHERE norent = 0 ORDER BY id;"

try {
    # Try without password first
    $mysqlArgs = @(
        "-h", $DatabaseHost,
        "-P", $DatabasePort.ToString(),
        "-u", $DatabaseUser,
        $DatabaseName,
        "-e", $query
    )
    
    & $mysqlExe $mysqlArgs | Out-File -FilePath $outputFile -Encoding ASCII
    
    # Read the output file and extract item IDs (skip header line)
    $itemIds = @()
    if (Test-Path $outputFile) {
        $lines = Get-Content $outputFile
        foreach ($line in $lines) {
            $line = $line.Trim()
            if ($line -and $line -match '^\d+$') {
                $itemIds += [int]$line
            }
        }
    }
    
    # Remove temp file
    Remove-Item $outputFile -ErrorAction SilentlyContinue
    
    if ($itemIds.Count -eq 0) {
        Write-Host "Warning: No no-rent items found. Check your database connection and query." -ForegroundColor Yellow
        exit 1
    }
    
    # Convert to JSON
    $jsonContent = $itemIds | ConvertTo-Json
    
    # Write to no_rent_items.json (UTF8 without BOM)
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText((Resolve-Path ".").Path + "\no_rent_items.json", $jsonContent, $utf8NoBom)
    
    Write-Host ""
    Write-Host "Successfully generated no_rent_items.json" -ForegroundColor Green
    Write-Host "  Found $($itemIds.Count) no-rent items" -ForegroundColor Green
    Write-Host ""
    Write-Host "First 10 item IDs:" -ForegroundColor Cyan
    $maxIndex = [Math]::Min(9, $itemIds.Count - 1)
    for ($i = 0; $i -le $maxIndex; $i++) {
        Write-Host "  $($itemIds[$i])"
    }
    if ($itemIds.Count -gt 10) {
        $remaining = $itemIds.Count - 10
        Write-Host "  ... and $remaining more" -ForegroundColor Gray
    }
    
} catch {
    # If connection failed, try with password prompt
    Write-Host "Connection failed, trying with password..." -ForegroundColor Yellow
    $securePassword = Read-Host "Enter MySQL password (or press Enter for no password)" -AsSecureString
    $password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword))
    
    if ($password) {
        $mysqlArgs = @(
            "-h", $DatabaseHost,
            "-P", $DatabasePort.ToString(),
            "-u", $DatabaseUser,
            "-p$password",
            $DatabaseName,
            "-e", $query
        )
        & $mysqlExe $mysqlArgs | Out-File -FilePath $outputFile -Encoding ASCII
    } else {
        $errorMsg = $_.Exception.Message
        Write-Host "Error occurred: $errorMsg" -ForegroundColor Red
        exit 1
    }
} finally {
    if (Test-Path $outputFile) {
        # Check if file has content
        $content = Get-Content $outputFile -ErrorAction SilentlyContinue
        if (-not $content -or $content.Count -eq 0) {
            Write-Host "No results returned. Check database connection." -ForegroundColor Red
            Remove-Item $outputFile -ErrorAction SilentlyContinue
            exit 1
        }
    }
}
