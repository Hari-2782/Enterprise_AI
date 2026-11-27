from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)


INDEX_NAME = "enterprise-knowledge"
VECTOR_ALGORITHM_NAME = "e5-hnsw"
VECTOR_PROFILE_NAME = "e5-vector-profile"
VECTOR_FIELD_NAME = "content_vector"
VECTOR_DIMENSIONS = 384


def build_search_index(index_name: str = INDEX_NAME) -> SearchIndex:
    """Build the Azure AI Search schema for chunk retrieval."""
    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SimpleField(
            name="document_id",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="version_id",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
        ),
        SearchableField(
            name="embedding_text",
            type=SearchFieldDataType.String,
        ),
        SearchableField(
            name="section_path",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="department",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="token_count",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
        SimpleField(
            name="source_token_start",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
        SimpleField(
            name="source_token_end",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
        SimpleField(
            name="source_token_count",
            type=SearchFieldDataType.Int32,
            filterable=True,
        ),
        SimpleField(
            name="page_numbers",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Int32),
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="sources_json",
            type=SearchFieldDataType.String,
            searchable=False,
            filterable=False,
            retrievable=True,
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            retrievable=False,
            vector_search_dimensions=VECTOR_DIMENSIONS,
            vector_search_profile_name=VECTOR_PROFILE_NAME,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM_NAME)],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE_NAME,
                algorithm_configuration_name=VECTOR_ALGORITHM_NAME,
            )
        ],
    )
    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
    )


def create_or_update_search_index(index_client, index_name: str) -> SearchIndex:
    """Create or update the configured vector index."""
    return index_client.create_or_update_index(
        build_search_index(index_name)
    )
