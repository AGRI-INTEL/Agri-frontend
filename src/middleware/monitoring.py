"""
Monitoring and metrics configuration using Prometheus
"""

from prometheus_client import Counter, Histogram, Gauge
from prometheus_client.openmetrics.exposition import generate_latest
from fastapi import FastAPI, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
import time

# Métriques HTTP
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"]
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Métriques base de données
DB_CONNECTIONS_ACTIVE = Gauge(
    "db_connections_active",
    "Number of active database connections"
)

DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation", "table"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# Métriques cache Redis
REDIS_OPERATIONS_TOTAL = Counter(
    "redis_operations_total",
    "Total number of Redis operations",
    ["operation"]
)

REDIS_OPERATION_DURATION = Histogram(
    "redis_operation_duration_seconds",
    "Redis operation duration in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1]
)

# Métriques authentification
AUTH_ATTEMPTS_TOTAL = Counter(
    "auth_attempts_total",
    "Total number of authentication attempts",
    ["status"]
)

# Métriques ML
ML_PREDICTION_DURATION = Histogram(
    "ml_prediction_duration_seconds",
    "Machine learning prediction duration in seconds",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

ML_PREDICTION_ERRORS = Counter(
    "ml_prediction_errors_total",
    "Total number of ML prediction errors",
    ["model", "error_type"]
)

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.time()
        
        response = await call_next(request)
        
        duration = time.time() - start_time
        status_code = response.status_code
        
        # Exclure les endpoints de monitoring des métriques
        if not request.url.path.startswith("/metrics"):
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=request.url.path,
                status=status_code
            ).inc()
            
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)
        
        return response

async def metrics_endpoint(request: Request) -> Response:
    """Endpoint pour exposer les métriques Prometheus"""
    return Response(
        generate_latest(),
        media_type="text/plain"
    )

def setup_monitoring(app: FastAPI) -> None:
    """Configure le monitoring pour l'application"""
    app.add_middleware(PrometheusMiddleware)
    app.add_route("/metrics", metrics_endpoint)
    
    # Initialiser les métriques de base
    DB_CONNECTIONS_ACTIVE.set(0)

class MetricsService:
    @staticmethod
    def record_db_query(operation: str, table: str, duration: float) -> None:
        """Enregistre la durée d'une requête DB"""
        DB_QUERY_DURATION.labels(
            operation=operation,
            table=table
        ).observe(duration)

    @staticmethod
    def record_redis_operation(operation: str, duration: float) -> None:
        """Enregistre une opération Redis"""
        REDIS_OPERATIONS_TOTAL.labels(operation=operation).inc()
        REDIS_OPERATION_DURATION.labels(operation=operation).observe(duration)

    @staticmethod
    def record_auth_attempt(success: bool) -> None:
        """Enregistre une tentative d'authentification"""
        status = "success" if success else "failure"
        AUTH_ATTEMPTS_TOTAL.labels(status=status).inc()

    @staticmethod
    def record_ml_prediction(model: str, duration: float) -> None:
        """Enregistre une prédiction ML"""
        ML_PREDICTION_DURATION.labels(model=model).observe(duration)

    @staticmethod
    def record_ml_error(model: str, error_type: str) -> None:
        """Enregistre une erreur de prédiction ML"""
        ML_PREDICTION_ERRORS.labels(
            model=model,
            error_type=error_type
        ).inc()