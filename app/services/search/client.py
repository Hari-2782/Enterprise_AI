from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents import SearchClient

from app.core.config import settings

def get_search_index_client() :
    if not settings.azure_search_endpoint:
        raise RuntimeError("AZURE_SEARCH_ENDPOINT is not set in the environment variables.")
    
    if not settings.azure_search_api_key:
        raise RuntimeError("AZURE_SEARCH_API_KEY is not set in the environment variables.")
    
    credential = AzureKeyCredential(
        settings.azure_search_api_key.get_secret_value()
        )
    return SearchIndexClient(
        endpoint=settings.azure_search_endpoint, 
        credential=credential
        )


def get_search_client(index_name: str | None = None):
    if not settings.azure_search_endpoint:
        raise RuntimeError("AZURE_SEARCH_ENDPOINT is not set in the environment variables.")

    if not settings.azure_search_api_key:
        raise RuntimeError("AZURE_SEARCH_API_KEY is not set in the environment variables.")

    credential = AzureKeyCredential(
        settings.azure_search_api_key.get_secret_value()
    )
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=index_name or settings.azure_search_index_name,
        credential=credential,
    )

def check_search_connection():
    try:
        client = get_search_index_client()
        # Attempt to list indexes to check the connection
        indexes = list(client.list_indexes())
        return{
            "connected": True,
            "indexes": [index.name for index in indexes]
        }
    except Exception as e:
        return{
            "connected": False,
            "error": str(e)
        }
