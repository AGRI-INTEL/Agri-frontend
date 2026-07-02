"""
Elasticsearch full-text search service with SQL ILIKE fallback
"""

import logging
from typing import Any, Optional

from sqlalchemy import select, or_
from sqlalchemy.sql import func

from config.config import get_settings
from config.database import get_db, es_client as global_es_client

settings = get_settings()
logger = logging.getLogger(__name__)

try:
    from elasticsearch import AsyncElasticsearch, NotFoundError as ESNotFoundError

    ES_AVAILABLE = True
except ImportError:
    AsyncElasticsearch = None
    ESNotFoundError = Exception
    ES_AVAILABLE = False

SEARCHABLE_MODELS: dict[str, Any] = {}

SUPPORTED_INDICES = {"actors", "indicators", "community_posts", "crops"}


class SearchService:

    async def index_document(self, index: str, doc_id: str, body: dict) -> bool:
        if not ES_AVAILABLE or global_es_client is None:
            logger.debug("Elasticsearch unavailable — skipping index for %s/%s", index, doc_id)
            return False

        try:
            await global_es_client.index(index=index, id=doc_id, document=body, refresh="wait_for")
            logger.info("Indexed document %s/%s", index, doc_id)
            return True
        except Exception as e:
            logger.error("Elasticsearch index failed for %s/%s: %s", index, doc_id, e)
            return False

    async def search(
        self,
        index: str,
        query: str,
        size: int = 20,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        if ES_AVAILABLE and global_es_client is not None:
            try:
                return await self._search_elastic(index, query, size, filters)
            except Exception as e:
                logger.warning("Elasticsearch search failed — falling back to SQL: %s", e)

        return await self._search_sql(index, query, size, filters)

    async def bulk_index(self, index: str, documents: list[dict]) -> int:
        if not ES_AVAILABLE or global_es_client is None:
            logger.debug("Elasticsearch unavailable — skipping bulk index for %s (%d docs)", index, len(documents))
            return 0

        try:
            bulk_body: list[dict] = []
            for doc in documents:
                doc_id = doc.get("id")
                if not doc_id:
                    continue
                bulk_body.append({"index": {"_index": index, "_id": doc_id}})
                bulk_body.append(doc)

            if not bulk_body:
                return 0

            response = await global_es_client.bulk(operations=bulk_body, refresh="wait_for")
            success_count = response.get("items", []).__len__() if not response.get("errors") else sum(
                1 for item in response.get("items", []) if "error" not in item.get("index", {})
            )
            logger.info("Bulk indexed %d/%d docs to %s", success_count, len(documents), index)
            return success_count
        except Exception as e:
            logger.error("Elasticsearch bulk index failed for %s: %s", index, e)
            return 0

    async def _search_elastic(
        self,
        index: str,
        query: str,
        size: int = 20,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        must = [{"match": {"_all": query}}]
        if filters:
            for field, value in filters.items():
                must.append({"term": {field: value}})

        search_body = {
            "query": {"bool": {"must": must}},
            "size": min(size, settings.MAX_PAGE_SIZE),
        }

        response = await global_es_client.search(index=index, body=search_body)
        hits = response.get("hits", {}).get("hits", [])
        return [{"id": h["_id"], "score": h["_score"], **h["_source"]} for h in hits]

    async def _search_sql(
        self,
        index: str,
        query: str,
        size: int = 20,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        if index not in SUPPORTED_INDICES:
            logger.warning("Unsupported search index: %s", index)
            return []

        model = self._get_model_for_index(index)
        if model is None:
            return []

        async for db in get_db():
            try:
                stmt = select(model)
                search_fields = self._get_search_fields(index)

                conditions = []
                for field in search_fields:
                    column = getattr(model, field, None)
                    if column is not None:
                        conditions.append(column.ilike(f"%{query}%"))

                if conditions:
                    stmt = stmt.where(or_(*conditions))

                if filters:
                    for field, value in filters.items():
                        column = getattr(model, field, None)
                        if column is not None:
                            stmt = stmt.where(column == value)

                stmt = stmt.limit(min(size, settings.MAX_PAGE_SIZE))
                result = await db.execute(stmt)
                rows = result.scalars().all()

                results = []
                for row in rows:
                    row_dict = self._row_to_dict(row)
                    row_dict["score"] = 1.0
                    results.append(row_dict)
                return results
            except Exception as e:
                logger.error("SQL search failed for index=%s: %s", index, e)
                return []

    def _get_model_for_index(self, index: str) -> Any:
        if index in SEARCHABLE_MODELS:
            return SEARCHABLE_MODELS[index]

        try:
            if index == "actors":
                from api.models.sql.actors import Actor
                SEARCHABLE_MODELS["actors"] = Actor
                return Actor
            elif index == "indicators":
                from api.models.sql.indicators import IndicateurValeur
                SEARCHABLE_MODELS["indicators"] = IndicateurValeur
                return IndicateurValeur
            elif index == "community_posts":
                from api.models.sql.community import Post
                SEARCHABLE_MODELS["community_posts"] = Post
                return Post
            elif index == "crops":
                from api.models.sql.agricultural import Crop
                SEARCHABLE_MODELS["crops"] = Crop
                return Crop
        except ImportError as e:
            logger.error("Could not import model for index=%s: %s", index, e)
        return None

    def _get_search_fields(self, index: str) -> list[str]:
        fields = {
            "actors": ["nom", "prenom", "pays", "ville", "description"],
            "indicators": ["source", "contexte"],
            "community_posts": ["title", "content"],
            "crops": ["name", "variety", "description", "growing_conditions"],
        }
        return fields.get(index, ["name", "title", "description"])

    def _row_to_dict(self, row: Any) -> dict:
        if hasattr(row, "_mapping"):
            return dict(row._mapping)
        if hasattr(row, "__table__"):
            return {c.name: getattr(row, c.name) for c in row.__table__.columns}
        if hasattr(row, "dict"):
            return row.dict()
        return {"id": str(getattr(row, "id", ""))}


search_service = SearchService()
