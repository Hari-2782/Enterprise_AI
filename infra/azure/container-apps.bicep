param location string = resourceGroup().location
param environmentName string = 'enterprise-ai-env'
param acrServer string
param acrUsername string
@secure()
param acrPassword string
param backendImage string
param frontendImage string

@secure()
param databaseUrl string
@secure()
param azureSearchEndpoint string
@secure()
param azureSearchApiKey string
@secure()
param openrouterApiKey string
@secure()
param authSecretKey string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {}
}

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'enterprise-ai-backend'
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
      }
      registries: [
        {
          server: acrServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: acrPassword }
        { name: 'database-url', value: databaseUrl }
        { name: 'search-key', value: azureSearchApiKey }
        { name: 'openrouter-key', value: openrouterApiKey }
        { name: 'auth-secret', value: authSecretKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'APP_ENV', value: 'production' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
            { name: 'AZURE_SEARCH_API_KEY', secretRef: 'search-key' }
            { name: 'MODEL_PROVIDER', value: 'openrouter' }
            { name: 'OPENROUTER_API_KEY', secretRef: 'openrouter-key' }
            { name: 'AUTH_SECRET_KEY', secretRef: 'auth-secret' }
            { name: 'CORS_ORIGINS', value: '*' }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'enterprise-ai-frontend'
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 3000
      }
      registries: [
        {
          server: acrServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: acrPassword }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'BACKEND_INTERNAL_URL'
              value: 'https://${backendApp.properties.configuration.ingress.fqdn}'
            }
            {
              name: 'NEXT_PUBLIC_API_BASE_URL'
              value: '/api/proxy'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}
