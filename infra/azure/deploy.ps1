param(
    [Parameter(Mandatory = $true)][string]$ResourceGroup,
    [Parameter(Mandatory = $true)][string]$Location,
    [Parameter(Mandatory = $true)][string]$AcrName,
    [Parameter(Mandatory = $true)][string]$DatabaseUrl,
    [Parameter(Mandatory = $true)][string]$AzureSearchEndpoint,
    [Parameter(Mandatory = $true)][string]$AzureSearchApiKey,
    [Parameter(Mandatory = $true)][string]$OpenRouterApiKey,
    [string]$AuthSecretKey = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
)

$ErrorActionPreference = "Stop"

Write-Host "1. Ensuring Resource Group and Azure Container Registry..."
az group create --name $ResourceGroup --location $Location | Out-Null
az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true | Out-Null

$acrServer = "$AcrName.azurecr.io"
$acrUser = az acr credential show --name $AcrName --query "username" -o tsv
$acrPass = az acr credential show --name $AcrName --query "passwords[0].value" -o tsv
$backendImage = "${acrServer}/enterprise-ai-backend:latest"
$frontendImage = "${acrServer}/enterprise-ai-frontend:latest"

Write-Host "2. Building & pushing images in Azure Container Registry..."
az acr build --registry $AcrName --image enterprise-ai-backend:latest --file backend/Dockerfile.backend backend
az acr build --registry $AcrName --image enterprise-ai-frontend:latest --file frontend/Dockerfile frontend

Write-Host "3. Running Alembic migrations against serverless PostgreSQL..."
Push-Location backend
$env:DATABASE_URL = $DatabaseUrl
uv run alembic upgrade head
Pop-Location

Write-Host "4. Deploying scale-to-zero Azure Container Apps (minReplicas: 0)..."
az deployment group create `
    --resource-group $ResourceGroup `
    --template-file infra/azure/container-apps.bicep `
    --parameters `
        location=$Location `
        acrServer=$acrServer `
        acrUsername=$acrUser `
        acrPassword=$acrPass `
        backendImage=$backendImage `
        frontendImage=$frontendImage `
        databaseUrl=$DatabaseUrl `
        azureSearchEndpoint=$AzureSearchEndpoint `
        azureSearchApiKey=$AzureSearchApiKey `
        openrouterApiKey=$OpenRouterApiKey `
        authSecretKey=$AuthSecretKey

Write-Host "Deployment complete!"
az containerapp list --resource-group $ResourceGroup --query "[].{Name:name, URL:properties.configuration.ingress.fqdn}" -o table
