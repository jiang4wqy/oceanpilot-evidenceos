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

function Assert-Equal {
    param(
        [AllowNull()]
        [object]$Actual,

        [AllowNull()]
        [object]$Expected,

        [Parameter(Mandatory = $true)]
        [string]$Step
    )

    if ([string]$Actual -cne [string]$Expected) {
        throw "[$Step] expected '$Expected', received '$Actual'"
    }
}

function New-EvidenceFact {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Code,

        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return [pscustomobject]@{
        Code = $Code
        Value = $Value
    }
}

$observedAt = "2026-08-05T04:00:00Z"
$scenarios = @(
    [pscustomobject]@{
        BusinessGroup = "3DS / callback"
        Scenario = "authentication or callback incomplete"
        RuleId = "THREEDS_INCOMPLETE_V1"
        ResponsibleTeam = "TECHNICAL_SUPPORT"
        Priority = "MEDIUM"
        ReviewReasons = @("INSUFFICIENT_SOURCE_QUALITY", "LOW_CONFIDENCE")
        Facts = @(
            (New-EvidenceFact "transaction.reference" "txn_threeds_001")
            (New-EvidenceFact "transaction.occurred_at" $observedAt)
            (New-EvidenceFact "context.environment" "PROD")
            (New-EvidenceFact "symptom.status" "PENDING")
            (New-EvidenceFact "integration.type" "API")
            (New-EvidenceFact "authentication.status" "REQUIRED")
            (New-EvidenceFact "callback.delivery_status" "NOT_RECEIVED")
        )
    }
    [pscustomobject]@{
        BusinessGroup = "Risk decline"
        Scenario = "risk decision declined"
        RuleId = "RISK_DECLINE_V1"
        ResponsibleTeam = "RISK"
        Priority = "HIGH"
        ReviewReasons = @("INSUFFICIENT_SOURCE_QUALITY", "LOW_CONFIDENCE", "RISK_DECISION")
        Facts = @(
            (New-EvidenceFact "transaction.reference" "txn_risk_001")
            (New-EvidenceFact "transaction.occurred_at" $observedAt)
            (New-EvidenceFact "context.environment" "PROD")
            (New-EvidenceFact "symptom.status" "DECLINED")
            (New-EvidenceFact "integration.type" "API")
            (New-EvidenceFact "risk.decision_code" "RISK_DECLINE")
        )
    }
    [pscustomobject]@{
        BusinessGroup = "Configuration mismatch"
        Scenario = "merchant-side mismatch"
        RuleId = "CONFIG_MISMATCH_MERCHANT_V1"
        ResponsibleTeam = "TECHNICAL_SUPPORT"
        Priority = "MEDIUM"
        ReviewReasons = @("INSUFFICIENT_SOURCE_QUALITY", "LOW_CONFIDENCE")
        Facts = @(
            (New-EvidenceFact "transaction.reference" "txn_config_merchant_001")
            (New-EvidenceFact "transaction.occurred_at" $observedAt)
            (New-EvidenceFact "context.environment" "PROD")
            (New-EvidenceFact "symptom.status" "FAILED")
            (New-EvidenceFact "integration.type" "API")
            (New-EvidenceFact "payment.method" "CARD")
            (New-EvidenceFact "configuration.check_result" "MERCHANT_SIDE_MISMATCH")
        )
    }
    [pscustomobject]@{
        BusinessGroup = "Configuration mismatch"
        Scenario = "PSP profile mismatch"
        RuleId = "CONFIG_MISMATCH_PSP_V1"
        ResponsibleTeam = "PSP_SUPPORT"
        Priority = "MEDIUM"
        ReviewReasons = @("INSUFFICIENT_SOURCE_QUALITY", "LOW_CONFIDENCE")
        Facts = @(
            (New-EvidenceFact "transaction.reference" "txn_config_psp_001")
            (New-EvidenceFact "transaction.occurred_at" $observedAt)
            (New-EvidenceFact "context.environment" "PROD")
            (New-EvidenceFact "symptom.status" "FAILED")
            (New-EvidenceFact "integration.type" "API")
            (New-EvidenceFact "payment.method" "CARD")
            (New-EvidenceFact "configuration.check_result" "PSP_PROFILE_MISMATCH")
        )
    }
)

$serviceBaseUrl = $BaseUrl.TrimEnd("/")
$client = [System.Net.Http.HttpClient]::new()
$summaries = @()

Write-Host "SYNTHETIC LOCAL DEMO — no Oceanpayment or Feishu connection; no payment action is executed."
Write-Host "HTTP demo origin: MERCHANT / USER_REPORTED; expected review score 0.87, not the internal 0.94 fixture."

try {
    $health = Invoke-JsonHttp `
        -Client $client `
        -Method ([System.Net.Http.HttpMethod]::Get) `
        -Uri "$serviceBaseUrl/health"
    Assert-HttpStatus -Result $health -Expected 200 -Step "health"
    Assert-Equal -Actual $health.Json.status -Expected "ok" -Step "health body"

    foreach ($scenario in $scenarios) {
        $createPayload = [ordered]@{
            case_type = "PAYMENT_INCIDENT"
            summary = "Synthetic $($scenario.BusinessGroup): $($scenario.Scenario)"
            merchant_ref = "synthetic-demo-$([guid]::NewGuid().ToString('N'))"
            synthetic = $true
        }
        $created = Invoke-JsonHttp `
            -Client $client `
            -Method ([System.Net.Http.HttpMethod]::Post) `
            -Uri "$serviceBaseUrl/api/v1/cases" `
            -Body $createPayload
        Assert-HttpStatus -Result $created -Expected 201 -Step "$($scenario.RuleId) create case"

        $caseId = [string]$created.Json.case.case_id
        if ([string]::IsNullOrWhiteSpace($caseId)) {
            throw "[$($scenario.RuleId) create case] response did not contain case.case_id"
        }
        Assert-Equal `
            -Actual $created.Json.case.readiness.ready `
            -Expected $false `
            -Step "$($scenario.RuleId) initial readiness"
        if (@($created.Json.case.readiness.missing_fields).Count -eq 0) {
            throw "[$($scenario.RuleId) initial readiness] expected missing evidence"
        }

        foreach ($fact in $scenario.Facts) {
            $evidencePayload = [ordered]@{
                evidence_id = [guid]::NewGuid().ToString()
                evidence_code = $fact.Code
                availability = "AVAILABLE"
                typed_value = $fact.Value
                observed_at = $observedAt
                source_ref = "synthetic:http-demo:$($scenario.RuleId):$($fact.Code)"
            }
            $evidence = Invoke-JsonHttp `
                -Client $client `
                -Method ([System.Net.Http.HttpMethod]::Post) `
                -Uri "$serviceBaseUrl/api/v1/cases/$caseId/evidence" `
                -Body $evidencePayload
            Assert-HttpStatus `
                -Result $evidence `
                -Expected 201 `
                -Step "$($scenario.RuleId) append $($fact.Code)"
        }

        $loaded = Invoke-JsonHttp `
            -Client $client `
            -Method ([System.Net.Http.HttpMethod]::Get) `
            -Uri "$serviceBaseUrl/api/v1/cases/$caseId"
        Assert-HttpStatus -Result $loaded -Expected 200 -Step "$($scenario.RuleId) read case"
        Assert-Equal `
            -Actual $loaded.Json.case.status `
            -Expected "EVIDENCE_READY" `
            -Step "$($scenario.RuleId) evidence-ready status"
        Assert-Equal `
            -Actual $loaded.Json.case.readiness.ready `
            -Expected $true `
            -Step "$($scenario.RuleId) final readiness"
        Assert-Equal `
            -Actual @($loaded.Json.evidence).Count `
            -Expected @($scenario.Facts).Count `
            -Step "$($scenario.RuleId) stored evidence count"

        $diagnosis = Invoke-JsonHttp `
            -Client $client `
            -Method ([System.Net.Http.HttpMethod]::Post) `
            -Uri "$serviceBaseUrl/api/v1/cases/$caseId/diagnose"
        Assert-HttpStatus -Result $diagnosis -Expected 201 -Step "$($scenario.RuleId) diagnose"

        Assert-Equal `
            -Actual $diagnosis.Json.outcome `
            -Expected "CREATED" `
            -Step "$($scenario.RuleId) diagnosis outcome"
        Assert-Equal `
            -Actual $diagnosis.Json.case_status `
            -Expected "HUMAN_REVIEW" `
            -Step "$($scenario.RuleId) case status"
        Assert-Equal `
            -Actual @($diagnosis.Json.diagnosis.hypotheses).Count `
            -Expected 1 `
            -Step "$($scenario.RuleId) hypothesis count"

        $hypothesis = $diagnosis.Json.diagnosis.hypotheses[0]
        $route = $diagnosis.Json.diagnosis.routing_decision
        $ticket = $diagnosis.Json.diagnosis.ticket_draft
        Assert-Equal -Actual $hypothesis.rule_id -Expected $scenario.RuleId -Step "matched rule"
        Assert-Equal `
            -Actual ([decimal]$hypothesis.confidence_score) `
            -Expected ([decimal]"0.87") `
            -Step "$($scenario.RuleId) display confidence"
        Assert-Equal `
            -Actual $route.responsible_team `
            -Expected $scenario.ResponsibleTeam `
            -Step "$($scenario.RuleId) responsible team"
        Assert-Equal `
            -Actual $route.priority `
            -Expected $scenario.Priority `
            -Step "$($scenario.RuleId) priority"
        Assert-Equal `
            -Actual $diagnosis.Json.diagnosis.requires_human `
            -Expected $true `
            -Step "$($scenario.RuleId) human review"
        Assert-Equal `
            -Actual $diagnosis.Json.diagnosis.synthetic `
            -Expected $true `
            -Step "$($scenario.RuleId) synthetic diagnosis"
        Assert-Equal `
            -Actual $ticket.synthetic `
            -Expected $true `
            -Step "$($scenario.RuleId) synthetic ticket"

        $actualReviewReasons = @($diagnosis.Json.diagnosis.review_reasons | Sort-Object)
        $expectedReviewReasons = @($scenario.ReviewReasons | Sort-Object)
        Assert-Equal `
            -Actual ($actualReviewReasons -join ",") `
            -Expected ($expectedReviewReasons -join ",") `
            -Step "$($scenario.RuleId) review reasons"

        $storedEvidenceIds = @($loaded.Json.evidence.evidence_id)
        foreach ($evidenceRef in @($hypothesis.evidence_refs)) {
            if ($storedEvidenceIds -notcontains [string]$evidenceRef) {
                throw "[$($scenario.RuleId) evidence references] missing $evidenceRef"
            }
        }

        if ($null -eq $diagnosis.Json.audit_reference.diagnosis_id) {
            throw "[$($scenario.RuleId) audit reference] diagnosis_id is missing"
        }

        $summaries += [pscustomobject][ordered]@{
            business_group = $scenario.BusinessGroup
            scenario = $scenario.Scenario
            diagnosis_http = $diagnosis.StatusCode
            diagnosis_snapshot_status = $diagnosis.Json.diagnosis.status
            case_status = $diagnosis.Json.case_status
            readiness = $loaded.Json.case.readiness.ready
            matched_rule_id = $hypothesis.rule_id
            display_confidence = $hypothesis.confidence_score
            review_reasons = $actualReviewReasons
            responsible_team = $route.responsible_team
            priority = $route.priority
            ticket_title = $ticket.title
            next_action = $ticket.next_action
            audit_reference = [ordered]@{
                diagnosis_id = $diagnosis.Json.audit_reference.diagnosis_id
                case_revision = $diagnosis.Json.audit_reference.case_revision
                evidence_revision = $diagnosis.Json.audit_reference.evidence_revision
            }
            synthetic = $diagnosis.Json.diagnosis.synthetic
        }
    }

    Write-Host "SYNTHETIC DEMO SUMMARY"
    $summaries | ConvertTo-Json -Depth 10
}
finally {
    $client.Dispose()
}
