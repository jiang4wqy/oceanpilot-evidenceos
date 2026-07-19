param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Net.Http

function Invoke-JsonHttp {
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpClient]$Client,

        [Parameter(Mandatory = $true)]
        [System.Net.Http.HttpMethod]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [object]$Body
    )

    $request = [System.Net.Http.HttpRequestMessage]::new($Method, $Uri)
    $response = $null
    try {
        if ($PSBoundParameters.ContainsKey("Body")) {
            $json = $Body | ConvertTo-Json -Depth 10 -Compress
            $request.Content = [System.Net.Http.StringContent]::new(
                $json,
                [System.Text.Encoding]::UTF8,
                "application/json"
            )
        }

        $response = $Client.SendAsync($request).GetAwaiter().GetResult()
        $rawBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $jsonBody = $null
        if (-not [string]::IsNullOrWhiteSpace($rawBody)) {
            $jsonBody = $rawBody | ConvertFrom-Json
        }

        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Json = $jsonBody
            Raw = $rawBody
        }
    }
    finally {
        if ($null -ne $response) {
            $response.Dispose()
        }
        $request.Dispose()
    }
}

function Assert-HttpStatus {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Result,

        [Parameter(Mandatory = $true)]
        [int]$Expected,

        [Parameter(Mandatory = $true)]
        [string]$Step
    )

    if ($Result.StatusCode -ne $Expected) {
        throw "[$Step] expected HTTP $Expected, received $($Result.StatusCode): $($Result.Raw)"
    }
}

$serviceBaseUrl = $BaseUrl.TrimEnd("/")
$client = [System.Net.Http.HttpClient]::new()

Write-Host "SYNTHETIC LOCAL FOUNDATION DEMO - no external service connection or payment action."

try {
    $health = Invoke-JsonHttp `
        -Client $client `
        -Method ([System.Net.Http.HttpMethod]::Get) `
        -Uri "$serviceBaseUrl/health"
    Assert-HttpStatus -Result $health -Expected 200 -Step "health"

    $createPayload = [ordered]@{
        case_type = "PAYMENT_INCIDENT"
        summary = "Synthetic checkout failure for the local foundation demo"
        merchant_ref = "synthetic-merchant-demo"
        synthetic = $true
    }
    $created = Invoke-JsonHttp `
        -Client $client `
        -Method ([System.Net.Http.HttpMethod]::Post) `
        -Uri "$serviceBaseUrl/api/v1/cases" `
        -Body $createPayload
    Assert-HttpStatus -Result $created -Expected 201 -Step "create case"

    $caseId = [string]$created.Json.case.case_id
    if ([string]::IsNullOrWhiteSpace($caseId)) {
        throw "[create case] response did not contain case.case_id"
    }

    $evidencePayload = [ordered]@{
        evidence_id = [guid]::NewGuid().ToString()
        evidence_code = "context.environment"
        availability = "AVAILABLE"
        typed_value = "PROD"
        observed_at = "2026-07-19T12:00:00+08:00"
        source_ref = "synthetic:foundation-demo"
    }
    $evidence = Invoke-JsonHttp `
        -Client $client `
        -Method ([System.Net.Http.HttpMethod]::Post) `
        -Uri "$serviceBaseUrl/api/v1/cases/$caseId/evidence" `
        -Body $evidencePayload
    Assert-HttpStatus -Result $evidence -Expected 201 -Step "append evidence"

    $loaded = Invoke-JsonHttp `
        -Client $client `
        -Method ([System.Net.Http.HttpMethod]::Get) `
        -Uri "$serviceBaseUrl/api/v1/cases/$caseId"
    Assert-HttpStatus -Result $loaded -Expected 200 -Step "read case"

    $diagnosis = Invoke-JsonHttp `
        -Client $client `
        -Method ([System.Net.Http.HttpMethod]::Post) `
        -Uri "$serviceBaseUrl/api/v1/cases/$caseId/diagnose"
    Assert-HttpStatus -Result $diagnosis -Expected 501 -Step "deferred diagnosis"
    if ($diagnosis.Json.code -ne "FEATURE_DEFERRED") {
        throw "[deferred diagnosis] expected FEATURE_DEFERRED, received $($diagnosis.Raw)"
    }

    $summary = [ordered]@{
        health = $health.Json.status
        create_http = $created.StatusCode
        case_id = $caseId
        evidence_http = $evidence.StatusCode
        stored_evidence_count = @($loaded.Json.evidence).Count
        case_status = $loaded.Json.case.status
        diagnosis_http = $diagnosis.StatusCode
        diagnosis_code = $diagnosis.Json.code
    }

    Write-Host "Foundation flow completed with the expected deferred diagnosis boundary."
    $summary | ConvertTo-Json -Depth 10
}
finally {
    $client.Dispose()
}
