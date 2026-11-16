import logging
import uuid

from fastapi import FastAPI, Request

from app.services.search.client import check_search_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# logger = logging.getLogger(__name__)

logger = logging.getLogger("enterprise-ai")

app = FastAPI(
    title="Enterprise AI Intelligence Platform",
    version="0.1.0"
    )

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get(
        "X-Request-ID", str(uuid.uuid4())
        )
    request.state.request_id = request_id

    logger.info(
        "request_started",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id

    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code
        })
    return response
@app.get("/api/v1/health")

def health_check(request: Request):

    return{
        "status":"healthy",
        "service":"enterprise-ai",
        "request_id": request.state.request_id
    }

@app.get("/api/v1/health/azure-search")
def azure_search_health():

    try:
        result = check_search_connection()
        return {
            "status": "healthy",
            "Azure Search": result
        }  
    except Exception as e:
        logger.error(f"Azure Search health check failed: {e}")

        return {
            "status": "unhealthy",
            "azure_search":{
                "connected": False,
            }
        }    
