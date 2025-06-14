"""
Backend/services/narrative_service.py
Service for clustering news into narratives and analyzing their strength
"""
from __future__ import annotations

import logging
import asyncio
import time
import orjson
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import redis.asyncio as redis
from redis.asyncio.connection import BlockingConnectionPool

from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

class NarrativeService:
    """Service for clustering news messages into narratives."""
    _instance = None
    _initialized = False
    
    # Redis connection
    _redis_pool: Optional[BlockingConnectionPool] = None
    _redis_client: Optional[redis.Redis] = None
    
    # Narrative data
    _narratives: Dict[str, Dict[str, Any]] = {}
    _message_to_narrative: Dict[str, str] = {}
    _last_update: float = 0
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NarrativeService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        logger.info("Initializing NarrativeService...")
        self._initialized = True
        self._narratives = {}
        self._message_to_narrative = {}
        self._last_update = time.time()

    async def _ensure_redis_initialized(self) -> None:
        """Ensure Redis is initialized."""
        if self._redis_client is None:
            await self._initialize_redis()
    
    async def _initialize_redis(self) -> None:
        """Initialize async Redis connection."""
        try:
            settings = get_settings()
            
            if settings.REDIS_URL:
                logger.info(f"Connecting to Redis for narratives: {settings.REDIS_URL}")
                self._redis_pool = BlockingConnectionPool.from_url(
                    settings.REDIS_URL,
                    max_connections=10,
                    decode_responses=True,
                )
            else:
                self._redis_pool = BlockingConnectionPool(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    password=settings.REDIS_PASSWORD,
                    max_connections=10,
                    decode_responses=True,
                )
            
            self._redis_client = redis.Redis(connection_pool=self._redis_pool)
            await self._redis_client.ping()
            logger.info("Narrative Redis connection established")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis for narratives: {e}")
            raise

    async def _get_redis_client(self) -> redis.Redis:
        """Get Redis client."""
        await self._ensure_redis_initialized()
        if not self._redis_client:
            raise RuntimeError("Redis client not initialized")
        return self._redis_client

    def _extract_key_entities(self, message: Dict[str, Any]) -> Set[str]:
        """Extract key entities from a message."""
        entities = set()
        
        # Handle nested structure: analysis_payload.knowledge_graph_data
        if "analysis_payload" in message:
            knowledge_data = message["analysis_payload"].get("knowledge_graph_data", {})
            
            # Extract from interpretation_tags
            if "interpretation_tags" in knowledge_data:
                for tag in knowledge_data["interpretation_tags"]:
                    if tag and isinstance(tag, str):
                        entities.add(tag.lower())
            
            # Extract from entities
            if "extracted_entities" in knowledge_data:
                for entity in knowledge_data["extracted_entities"]:
                    if isinstance(entity, dict):
                        text = entity.get("normalized_name") or entity.get("text")
                        if text:
                            entities.add(text.lower())
        
        # Also check for whirlpool_analysis structure (from regular topic)
        if "analysis_payload" in message:
            whirlpool_data = message["analysis_payload"].get("whirlpool_analysis", {})
            
            # Extract from suggested_labels
            if "suggested_labels" in whirlpool_data:
                for label in whirlpool_data["suggested_labels"]:
                    if label and isinstance(label, str):
                        entities.add(label.lower())
            
            # Extract from extracted_entities
            if "extracted_entities" in whirlpool_data:
                entities_data = whirlpool_data["extracted_entities"]
                
                # Organizations
                for org in entities_data.get("organizations", []):
                    if isinstance(org, dict) and "name" in org:
                        entities.add(org["name"].lower())
                
                # Individuals
                for person in entities_data.get("individuals", []):
                    if isinstance(person, dict) and "name" in person:
                        entities.add(person["name"].lower())
                
                # Locations
                for location in entities_data.get("locations", []):
                    if isinstance(location, dict) and "name" in location:
                        entities.add(location["name"].lower())
        
        # Fallback to direct fields if they exist (for backward compatibility)
        if "interpretation_tags" in message:
            for tag in message["interpretation_tags"]:
                if tag and isinstance(tag, str):
                    entities.add(tag.lower())
        
        if "extracted_entities" in message:
            for entity in message["extracted_entities"]:
                if isinstance(entity, dict):
                    text = entity.get("normalized_name") or entity.get("text")
                    if text:
                        entities.add(text.lower())
        
        logger.debug(f"Extracted entities from message {message.get('news_id', 'unknown')}: {entities}")
        return entities

    def _calculate_similarity(self, entities1: Set[str], entities2: Set[str]) -> float:
        """Calculate Jaccard similarity between two entity sets."""
        if not entities1 or not entities2:
            return 0.0
        
        intersection = len(entities1 & entities2)
        union = len(entities1 | entities2)
        
        return intersection / union if union > 0 else 0.0

    def _find_narrative_for_message(self, message: Dict[str, Any], entities: Set[str]) -> Optional[str]:
        """Find existing narrative that best matches the message."""
        if not entities:
            return None
        
        best_narrative = None
        best_score = 0.0
        threshold = 0.3  # Minimum similarity to join a narrative
        
        for narrative_id, narrative in self._narratives.items():
            similarity = self._calculate_similarity(entities, narrative["entities"])
            if similarity > threshold and similarity > best_score:
                best_score = similarity
                best_narrative = narrative_id
        
        return best_narrative

    def _create_narrative_id(self) -> str:
        """Create unique narrative ID."""
        return f"narrative_{int(time.time() * 1000)}_{len(self._narratives)}"

    def _calculate_narrative_strength(self, narrative: Dict[str, Any]) -> float:
        """Calculate narrative strength based on volume and recency."""
        message_count = len(narrative["messages"])
        
        # Base strength from message count (log scale)
        base_strength = min(1.0, (message_count ** 0.5) / 10)
        
        # Recency factor
        now = time.time()
        last_update = narrative.get("last_update", now)
        hours_old = (now - last_update) / 3600
        recency_factor = max(0.1, 1.0 - (hours_old / 24))  # Decay over 24 hours
        
        # Impact factor from sentiment strength
        sentiment_scores = narrative.get("sentiment_scores", {"positive": 0, "negative": 0, "neutral": 0})
        total_sentiment = sum(sentiment_scores.values())
        if total_sentiment > 0:
            max_sentiment = max(sentiment_scores.values())
            sentiment_strength = max_sentiment / total_sentiment
        else:
            sentiment_strength = 0.5
        
        # Combined strength
        strength = base_strength * recency_factor * (0.5 + 0.5 * sentiment_strength)
        return min(1.0, max(0.1, strength))

    def _determine_narrative_sentiment(self, narrative: Dict[str, Any]) -> str:
        """Determine overall narrative sentiment."""
        scores = narrative.get("sentiment_scores", {"positive": 0, "negative": 0, "neutral": 0})
        
        if scores["positive"] > scores["negative"] * 1.5:
            return "positive"
        elif scores["negative"] > scores["positive"] * 1.5:
            return "negative"
        else:
            return "neutral"

    async def add_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Add a message to narratives and return narrative ID."""
        try:
            message_id = message.get("news_id")
            if not message_id:
                logger.debug("Message has no news_id, skipping")
                return None
            
            # Skip if already processed
            if message_id in self._message_to_narrative:
                return self._message_to_narrative[message_id]
            
            # Extract entities
            entities = self._extract_key_entities(message)
            if not entities:
                logger.debug(f"No entities found in message {message_id}: {message.get('title', 'no title')}")
                return None
            
            logger.debug(f"Found entities for message {message_id}: {entities}")
            
            # Find or create narrative
            narrative_id = self._find_narrative_for_message(message, entities)
            
            if narrative_id:
                # Add to existing narrative
                narrative = self._narratives[narrative_id]
                narrative["messages"].append(message_id)
                narrative["entities"].update(entities)
                narrative["last_update"] = time.time()
                
                # Update sentiment scores
                sentiment = "neutral"  # default
                
                # Extract sentiment from nested structure
                if "analysis_payload" in message:
                    knowledge_data = message["analysis_payload"].get("knowledge_graph_data", {})
                    if "sentiment" in knowledge_data:
                        sentiment_data = knowledge_data["sentiment"]
                        if isinstance(sentiment_data, dict):
                            sentiment = sentiment_data.get("label", "neutral").lower()
                        else:
                            sentiment = str(sentiment_data).lower()
                    
                    # Also check whirlpool analysis
                    whirlpool_data = message["analysis_payload"].get("whirlpool_analysis", {})
                    if "sentiment_analysis" in whirlpool_data:
                        overall_sentiment = whirlpool_data["sentiment_analysis"].get("overall_sentiment", {})
                        if isinstance(overall_sentiment, dict):
                            sentiment = overall_sentiment.get("label", "neutral").lower()
                else:
                    # Fallback for direct sentiment field
                    sentiment = message.get("sentiment", "neutral").lower()
                
                if sentiment in narrative["sentiment_scores"]:
                    narrative["sentiment_scores"][sentiment] += 1
                
                logger.info(f"Added message {message_id} to existing narrative {narrative_id}")
            else:
                # Create new narrative
                narrative_id = self._create_narrative_id()
                
                # Extract sentiment for new narrative
                sentiment = "neutral"
                if "analysis_payload" in message:
                    knowledge_data = message["analysis_payload"].get("knowledge_graph_data", {})
                    if "sentiment" in knowledge_data:
                        sentiment_data = knowledge_data["sentiment"]
                        if isinstance(sentiment_data, dict):
                            sentiment = sentiment_data.get("label", "neutral").lower()
                        else:
                            sentiment = str(sentiment_data).lower()
                    
                    whirlpool_data = message["analysis_payload"].get("whirlpool_analysis", {})
                    if "sentiment_analysis" in whirlpool_data:
                        overall_sentiment = whirlpool_data["sentiment_analysis"].get("overall_sentiment", {})
                        if isinstance(overall_sentiment, dict):
                            sentiment = overall_sentiment.get("label", "neutral").lower()
                
                self._narratives[narrative_id] = {
                    "id": narrative_id,
                    "messages": [message_id],
                    "entities": entities,
                    "created": time.time(),
                    "last_update": time.time(),
                    "sentiment_scores": {
                        "positive": 1 if sentiment == "positive" else 0,
                        "negative": 1 if sentiment == "negative" else 0,
                        "neutral": 1 if sentiment == "neutral" else 0,
                    },
                    "title": self._generate_narrative_title(message, entities),
                    "summary": self._extract_summary(message)
                }
                
                logger.info(f"Created new narrative {narrative_id} for message {message_id}")
            
            self._message_to_narrative[message_id] = narrative_id
            self._last_update = time.time()
            
            # Recalculate strength and sentiment
            narrative = self._narratives[narrative_id]
            narrative["strength"] = self._calculate_narrative_strength(narrative)
            narrative["sentiment"] = self._determine_narrative_sentiment(narrative)
            
            # Store in Redis
            await self._store_narrative_in_redis(narrative_id, narrative)
            
            return narrative_id
            
        except Exception as e:
            logger.error(f"Error adding message to narratives: {e}", exc_info=True)
            return None

    def _generate_narrative_title(self, message: Dict[str, Any], entities: Set[str]) -> str:
        """Generate a title for the narrative."""
        # Use the most prominent entities
        entity_list = list(entities)
        
        # Sort entities by relevance (prioritize certain types)
        priority_entities = []
        other_entities = []
        
        for entity in entity_list:
            entity_lower = entity.lower()
            # Prioritize countries, companies, and specific topics
            if any(keyword in entity_lower for keyword in ['iran', 'israel', 'us', 'united states', 'russia', 'china', 'bitcoin', 'oil', 'gold']):
                priority_entities.append(entity)
            else:
                other_entities.append(entity)
        
        # Combine prioritized entities first
        final_entities = (priority_entities[:2] + other_entities[:1])[:3]
        
        if final_entities:
            # Create more diverse titles based on entity combinations
            if len(final_entities) == 1:
                return final_entities[0].title()
            elif len(final_entities) == 2:
                return f"{final_entities[0].title()} - {final_entities[1].title()}"
            else:
                # For 3+ entities, create a more compact format
                main_entity = final_entities[0].title()
                others = ", ".join(e.title() for e in final_entities[1:3])
                return f"{main_entity} ({others})"
        
        # Fallback: extract key words from the first message title
        if "title" in message:
            # Extract key words (capitalized words, countries, etc.)
            words = message["title"].split()
            key_words = []
            for word in words:
                if word[0].isupper() and len(word) > 2 and word not in ['The', 'And', 'For', 'But']:
                    key_words.append(word)
            
            if key_words:
                return " ".join(key_words[:3])
        
        return "Market Update"

    def _extract_summary(self, message: Dict[str, Any]) -> str:
        """Extract summary from message."""
        # Try to get interpretation from knowledge graph data
        if "analysis_payload" in message:
            knowledge_data = message["analysis_payload"].get("knowledge_graph_data", {})
            if "interpretation" in knowledge_data:
                return knowledge_data["interpretation"][:200]
            
            # Try whirlpool analysis summary
            whirlpool_data = message["analysis_payload"].get("whirlpool_analysis", {})
            if "summary" in whirlpool_data:
                return whirlpool_data["summary"][:200]
        
        # Fallback to interpretation field
        if "interpretation" in message:
            return message["interpretation"][:200]
        
        # Fallback to title
        return message.get("title", "")[:200]

    async def _store_narrative_in_redis(self, narrative_id: str, narrative: Dict[str, Any]) -> None:
        """Store narrative in Redis."""
        try:
            client = await self._get_redis_client()
            settings = get_settings()
            
            # Store narrative data
            key = f"{settings.NARRATIVE_REDIS_PREFIX}:{narrative_id}"
            await client.hset(key, mapping={
                "data": orjson.dumps(narrative).decode(),
                "updated": str(time.time())
            })
            
            # Set expiration (7 days)
            await client.expire(key, 7 * 24 * 3600)
            
            # Add to sorted set for quick retrieval
            await client.zadd(
                f"{settings.NARRATIVE_REDIS_PREFIX}:active",
                {narrative_id: narrative["strength"]}
            )
            
        except Exception as e:
            logger.error(f"Error storing narrative in Redis: {e}")

    async def get_active_narratives(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get active narratives sorted by strength."""
        try:
            client = await self._get_redis_client()
            settings = get_settings()
            
            # Get top narratives by strength
            narrative_ids = await client.zrevrange(
                f"{settings.NARRATIVE_REDIS_PREFIX}:active",
                0, limit - 1
            )
            
            narratives = []
            for narrative_id in narrative_ids:
                key = f"{settings.NARRATIVE_REDIS_PREFIX}:{narrative_id}"
                data = await client.hget(key, "data")
                if data:
                    try:
                        narrative = orjson.loads(data)
                        narratives.append(narrative)
                    except Exception as e:
                        logger.error(f"Error parsing narrative {narrative_id}: {e}")
            
            # Add from memory if Redis is empty
            if not narratives and self._narratives:
                sorted_narratives = sorted(
                    self._narratives.values(),
                    key=lambda x: x.get("strength", 0),
                    reverse=True
                )[:limit]
                narratives = sorted_narratives
            
            logger.info(f"Retrieved {len(narratives)} active narratives")
            return narratives
            
        except Exception as e:
            logger.error(f"Error getting active narratives: {e}")
            # Fallback to in-memory data
            sorted_narratives = sorted(
                self._narratives.values(),
                key=lambda x: x.get("strength", 0),
                reverse=True
            )[:limit]
            return sorted_narratives

    async def get_narrative_details(self, narrative_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific narrative."""
        try:
            # Check memory first
            if narrative_id in self._narratives:
                return self._narratives[narrative_id]
            
            # Check Redis
            client = await self._get_redis_client()
            settings = get_settings()
            
            key = f"{settings.NARRATIVE_REDIS_PREFIX}:{narrative_id}"
            data = await client.hget(key, "data")
            
            if data:
                return orjson.loads(data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting narrative details: {e}")
            return None

    async def get_narrative_messages(self, narrative_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get messages belonging to a narrative."""
        try:
            narrative = await self.get_narrative_details(narrative_id)
            if not narrative:
                return []
            
            message_ids = narrative.get("messages", [])[-limit:]
            
            # Get messages from news service
            from Backend.services.news_service import NewsService
            news_service = NewsService()
            
            # Get all recent messages and filter
            all_messages = await news_service.get_messages(limit=200)
            
            messages = []
            for msg in all_messages:
                if msg.get("news_id") in message_ids:
                    messages.append(msg)
            
            return messages
            
        except Exception as e:
            logger.error(f"Error getting narrative messages: {e}")
            return []

    async def find_related_narratives(self, narrative_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Find narratives related to the given one."""
        try:
            source_narrative = await self.get_narrative_details(narrative_id)
            if not source_narrative:
                return []
            
            source_entities = set(source_narrative.get("entities", []))
            if not source_entities:
                return []
            
            # Get all narratives
            all_narratives = await self.get_active_narratives(limit=50)
            
            # Calculate similarities
            related = []
            for narrative in all_narratives:
                if narrative["id"] == narrative_id:
                    continue
                
                entities = set(narrative.get("entities", []))
                similarity = self._calculate_similarity(source_entities, entities)
                
                if similarity > 0.1:  # Minimum threshold
                    narrative["similarity"] = similarity
                    related.append(narrative)
            
            # Sort by similarity and return top results
            related.sort(key=lambda x: x["similarity"], reverse=True)
            return related[:limit]
            
        except Exception as e:
            logger.error(f"Error finding related narratives: {e}")
            return []

    async def cleanup_old_narratives(self, max_age_hours: int = 24) -> int:
        """Remove old narratives."""
        try:
            client = await self._get_redis_client()
            settings = get_settings()
            
            cutoff_time = time.time() - (max_age_hours * 3600)
            
            # Get all narrative IDs
            all_ids = await client.zrange(
                f"{settings.NARRATIVE_REDIS_PREFIX}:active",
                0, -1
            )
            
            removed_count = 0
            for narrative_id in all_ids:
                key = f"{settings.NARRATIVE_REDIS_PREFIX}:{narrative_id}"
                updated = await client.hget(key, "updated")
                
                if updated and float(updated) < cutoff_time:
                    await client.delete(key)
                    await client.zrem(
                        f"{settings.NARRATIVE_REDIS_PREFIX}:active",
                        narrative_id
                    )
                    removed_count += 1
            
            # Clean up in-memory data
            to_remove = []
            for narrative_id, narrative in self._narratives.items():
                if narrative.get("last_update", 0) < cutoff_time:
                    to_remove.append(narrative_id)
            
            for narrative_id in to_remove:
                del self._narratives[narrative_id]
                # Clean up message mappings
                msgs_to_remove = [
                    msg_id for msg_id, n_id in self._message_to_narrative.items()
                    if n_id == narrative_id
                ]
                for msg_id in msgs_to_remove:
                    del self._message_to_narrative[msg_id]
            
            logger.info(f"Cleaned up {removed_count} old narratives")
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up narratives: {e}")
            return 0

    async def close_connections(self) -> None:
        """Close Redis connections."""
        try:
            if self._redis_client:
                await self._redis_client.close()
                logger.info("Closed narrative Redis client")
            
            if self._redis_pool:
                await self._redis_pool.disconnect()
                logger.info("Closed narrative Redis pool")
                
        except Exception as e:
            logger.warning(f"Error closing narrative Redis connections: {e}")
