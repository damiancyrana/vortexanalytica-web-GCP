"""
Service for clustering news into narratives based on entities, topics, and sentiment.
"""
from __future__ import annotations

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Set, Optional, Tuple
from collections import defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

class NarrativeService:
    """Service for clustering news messages into coherent narratives."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(NarrativeService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        logger.info("Initializing NarrativeService...")
        self._initialized = True
        
        # Narrative clusters storage
        self.narratives: Dict[str, Dict[str, Any]] = {}
        self.narrative_lock = asyncio.Lock()
        
        # Configuration
        self.MIN_CLUSTER_SIZE = 2
        self.ENTITY_WEIGHT = 0.4
        self.TAG_WEIGHT = 0.3
        self.SENTIMENT_WEIGHT = 0.2
        self.TIME_WEIGHT = 0.1
        self.TIME_WINDOW_HOURS = 24
        
        logger.info("NarrativeService initialized")
    
    def _normalize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize message format from different analyzers."""
        normalized = {
            "news_id": message.get("news_id"),
            "title": message.get("title"),
            "time_reported": message.get("time_reported"),
            "entities": [],
            "tags": [],
            "sentiment": {"label": "Neutral", "score": 0.5},
            "narrative_impact": "Unknown",
            "summary": "",
            "market_relevance": 0.5
        }
        
        # Handle standard analyzer format
        if "analysis_payload" in message and "knowledge_graph_data" in message["analysis_payload"]:
            kg_data = message["analysis_payload"]["knowledge_graph_data"]
            
            # Extract entities
            for entity in kg_data.get("extracted_entities", []):
                normalized["entities"].append({
                    "name": entity.get("normalized_name", entity.get("text")),
                    "type": entity.get("type"),
                    "original": entity.get("text")
                })
            
            # Extract tags
            normalized["tags"] = kg_data.get("interpretation_tags", [])
            
            # Extract sentiment
            if "sentiment" in kg_data:
                if isinstance(kg_data["sentiment"], dict):
                    normalized["sentiment"] = kg_data["sentiment"]
                else:
                    normalized["sentiment"]["label"] = str(kg_data["sentiment"])
            
            normalized["narrative_impact"] = kg_data.get("narrative_impact", "Unknown")
            normalized["summary"] = kg_data.get("interpretation", "")
        
        # Handle whirlpool analyzer format (regular)
        elif "analysis_payload" in message and "whirlpool_analysis" in message["analysis_payload"]:
            wa_data = message["analysis_payload"]["whirlpool_analysis"]
            
            # Extract entities from various categories
            entities = wa_data.get("extracted_entities", {})
            
            # Add organizations
            for org in entities.get("organizations", []):
                normalized["entities"].append({
                    "name": org.get("name"),
                    "type": "ORG",
                    "ticker": org.get("ticker_symbol")
                })
            
            # Add locations
            for loc in entities.get("locations", []):
                normalized["entities"].append({
                    "name": loc.get("name"),
                    "type": loc.get("type", "GPE").upper()
                })
            
            # Add individuals
            for person in entities.get("individuals", []):
                normalized["entities"].append({
                    "name": person.get("name"),
                    "type": "PERSON"
                })
            
            # Extract tags
            normalized["tags"] = wa_data.get("suggested_labels", [])
            
            # Extract sentiment
            sentiment_data = wa_data.get("sentiment_analysis", {}).get("overall_sentiment", {})
            normalized["sentiment"] = {
                "label": sentiment_data.get("label", "Neutral"),
                "score": sentiment_data.get("confidence", 0.5)
            }
            
            # Extract other fields
            normalized["summary"] = wa_data.get("summary", "")
            market_rel = wa_data.get("market_relevance", {})
            normalized["market_relevance"] = market_rel.get("score", 0.5)
            
            # Determine narrative impact based on market relevance
            if normalized["market_relevance"] >= 0.7:
                normalized["narrative_impact"] = "Yes"
            elif normalized["market_relevance"] >= 0.4:
                normalized["narrative_impact"] = "Medium"
            else:
                normalized["narrative_impact"] = "Low"
        
        return normalized
    
    def _calculate_similarity(self, msg1: Dict[str, Any], msg2: Dict[str, Any]) -> float:
        """Calculate similarity between two normalized messages."""
        score = 0.0
        
        # Entity similarity
        entities1 = set(e["name"].lower() for e in msg1["entities"] if e["name"])
        entities2 = set(e["name"].lower() for e in msg2["entities"] if e["name"])
        
        if entities1 and entities2:
            entity_overlap = len(entities1.intersection(entities2))
            entity_union = len(entities1.union(entities2))
            if entity_union > 0:
                score += self.ENTITY_WEIGHT * (entity_overlap / entity_union)
        
        # Tag similarity
        tags1 = set(t.lower() for t in msg1["tags"])
        tags2 = set(t.lower() for t in msg2["tags"])
        
        if tags1 and tags2:
            tag_overlap = len(tags1.intersection(tags2))
            tag_union = len(tags1.union(tags2))
            if tag_union > 0:
                score += self.TAG_WEIGHT * (tag_overlap / tag_union)
        
        # Sentiment similarity
        sentiment_map = {"Positive": 1, "Neutral": 0, "Negative": -1}
        sent1 = sentiment_map.get(msg1["sentiment"]["label"], 0)
        sent2 = sentiment_map.get(msg2["sentiment"]["label"], 0)
        
        # Normalize sentiment difference to 0-1 range
        sent_similarity = 1 - abs(sent1 - sent2) / 2
        score += self.SENTIMENT_WEIGHT * sent_similarity
        
        # Time proximity (within time window)
        try:
            time1 = datetime.fromisoformat(msg1["time_reported"].replace('Z', '+00:00'))
            time2 = datetime.fromisoformat(msg2["time_reported"].replace('Z', '+00:00'))
            time_diff = abs((time1 - time2).total_seconds() / 3600)  # hours
            
            if time_diff <= self.TIME_WINDOW_HOURS:
                time_similarity = 1 - (time_diff / self.TIME_WINDOW_HOURS)
                score += self.TIME_WEIGHT * time_similarity
        except:
            pass
        
        return score
    
    async def add_message(self, message: Dict[str, Any]) -> Optional[str]:
        """Add a new message and assign it to a narrative cluster."""
        normalized = self._normalize_message(message)
        
        if not normalized["news_id"]:
            logger.warning("Message without news_id, skipping")
            return None
        
        async with self.narrative_lock:
            # Find best matching narrative
            best_narrative_id = None
            best_score = 0.0
            
            for narrative_id, narrative in self.narratives.items():
                # Calculate average similarity to messages in this narrative
                total_similarity = 0
                for existing_msg in narrative["messages"]:
                    similarity = self._calculate_similarity(normalized, existing_msg)
                    total_similarity += similarity
                
                avg_similarity = total_similarity / len(narrative["messages"]) if narrative["messages"] else 0
                
                if avg_similarity > best_score and avg_similarity > 0.3:  # Minimum threshold
                    best_score = avg_similarity
                    best_narrative_id = narrative_id
            
            # Create new narrative or add to existing
            if best_narrative_id:
                self._add_to_narrative(best_narrative_id, normalized)
            else:
                best_narrative_id = self._create_narrative(normalized)
            
            return best_narrative_id
    
    def _create_narrative(self, message: Dict[str, Any]) -> str:
        """Create a new narrative cluster."""
        narrative_id = f"narrative_{int(time.time() * 1000)}_{message['news_id']}"
        
        # Determine primary theme from entities and tags
        primary_theme = "General"
        if message["tags"]:
            primary_theme = message["tags"][0]
        elif message["entities"]:
            primary_theme = message["entities"][0]["name"]
        
        self.narratives[narrative_id] = {
            "id": narrative_id,
            "primary_theme": primary_theme,
            "messages": [message],
            "entities": {},
            "tags": {},
            "sentiment_distribution": {"Positive": 0, "Neutral": 0, "Negative": 0},
            "created_at": message["time_reported"],
            "updated_at": message["time_reported"],
            "strength": 1.0,
            "market_impact": message.get("market_relevance", 0.5)
        }
        
        self._update_narrative_stats(narrative_id)
        return narrative_id
    
    def _add_to_narrative(self, narrative_id: str, message: Dict[str, Any]) -> None:
        """Add a message to an existing narrative."""
        narrative = self.narratives[narrative_id]
        narrative["messages"].append(message)
        narrative["updated_at"] = message["time_reported"]
        
        self._update_narrative_stats(narrative_id)
    
    def _update_narrative_stats(self, narrative_id: str) -> None:
        """Update narrative statistics after adding a message."""
        narrative = self.narratives[narrative_id]
        
        # Reset counters
        narrative["entities"] = defaultdict(int)
        narrative["tags"] = defaultdict(int)
        narrative["sentiment_distribution"] = {"Positive": 0, "Neutral": 0, "Negative": 0}
        
        total_relevance = 0
        
        for msg in narrative["messages"]:
            # Count entities
            for entity in msg["entities"]:
                if entity["name"]:
                    narrative["entities"][entity["name"]] += 1
            
            # Count tags
            for tag in msg["tags"]:
                narrative["tags"][tag] += 1
            
            # Count sentiment
            sentiment = msg["sentiment"]["label"]
            if sentiment in narrative["sentiment_distribution"]:
                narrative["sentiment_distribution"][sentiment] += 1
            
            # Sum market relevance
            total_relevance += msg.get("market_relevance", 0.5)
        
        # Calculate narrative strength
        message_count = len(narrative["messages"])
        entity_diversity = len(narrative["entities"])
        tag_diversity = len(narrative["tags"])
        
        # Strength formula: combination of volume, diversity, and impact
        narrative["strength"] = (
            0.4 * min(message_count / 10, 1.0) +  # Volume component (normalized to 10)
            0.3 * min(entity_diversity / 5, 1.0) +  # Entity diversity (normalized to 5)
            0.3 * min(tag_diversity / 5, 1.0)  # Tag diversity (normalized to 5)
        )
        
        # Update market impact
        narrative["market_impact"] = total_relevance / message_count if message_count > 0 else 0.5
        
        # Update primary theme based on most common tag or entity
        if narrative["tags"]:
            narrative["primary_theme"] = max(narrative["tags"].items(), key=lambda x: x[1])[0]
        elif narrative["entities"]:
            narrative["primary_theme"] = max(narrative["entities"].items(), key=lambda x: x[1])[0]
    
    async def get_active_narratives(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get all active narratives within the specified time window."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        active_narratives = []
        
        async with self.narrative_lock:
            for narrative_id, narrative in self.narratives.items():
                try:
                    updated_at = datetime.fromisoformat(narrative["updated_at"].replace('Z', '+00:00'))
                    if updated_at > cutoff_time:
                        # Convert defaultdicts to regular dicts for JSON serialization
                        narrative_copy = narrative.copy()
                        narrative_copy["entities"] = dict(narrative["entities"])
                        narrative_copy["tags"] = dict(narrative["tags"])
                        active_narratives.append(narrative_copy)
                except:
                    continue
        
        # Sort by strength
        active_narratives.sort(key=lambda x: x["strength"], reverse=True)
        return active_narratives
    
    async def get_narrative_details(self, narrative_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific narrative."""
        async with self.narrative_lock:
            narrative = self.narratives.get(narrative_id)
            if not narrative:
                return None
            
            # Create a deep copy with regular dicts
            details = {
                "id": narrative["id"],
                "primary_theme": narrative["primary_theme"],
                "messages": narrative["messages"],
                "entities": dict(narrative["entities"]),
                "tags": dict(narrative["tags"]),
                "sentiment_distribution": narrative["sentiment_distribution"],
                "created_at": narrative["created_at"],
                "updated_at": narrative["updated_at"],
                "strength": narrative["strength"],
                "market_impact": narrative["market_impact"],
                "message_count": len(narrative["messages"])
            }
            
            # Sort entities and tags by frequency
            details["top_entities"] = sorted(
                details["entities"].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]
            
            details["top_tags"] = sorted(
                details["tags"].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]
            
            return details
    
    async def find_related_narratives(self, narrative_id: str, max_results: int = 5) -> List[Tuple[str, float]]:
        """Find narratives related to the given narrative."""
        async with self.narrative_lock:
            source_narrative = self.narratives.get(narrative_id)
            if not source_narrative:
                return []
            
            related = []
            
            # Compare with other narratives
            for other_id, other_narrative in self.narratives.items():
                if other_id == narrative_id:
                    continue
                
                # Calculate similarity based on shared entities and tags
                source_entities = set(source_narrative["entities"].keys())
                other_entities = set(other_narrative["entities"].keys())
                
                source_tags = set(source_narrative["tags"].keys())
                other_tags = set(other_narrative["tags"].keys())
                
                entity_overlap = len(source_entities.intersection(other_entities))
                tag_overlap = len(source_tags.intersection(other_tags))
                
                if entity_overlap > 0 or tag_overlap > 0:
                    similarity = (
                        0.6 * (entity_overlap / max(len(source_entities), 1)) +
                        0.4 * (tag_overlap / max(len(source_tags), 1))
                    )
                    related.append((other_id, similarity))
            
            # Sort by similarity and return top results
            related.sort(key=lambda x: x[1], reverse=True)
            return related[:max_results]
    
    async def cleanup_old_narratives(self, days: int = 7) -> int:
        """Remove narratives older than specified days."""
        cutoff_time = datetime.now() - timedelta(days=days)
        removed_count = 0
        
        async with self.narrative_lock:
            to_remove = []
            
            for narrative_id, narrative in self.narratives.items():
                try:
                    updated_at = datetime.fromisoformat(narrative["updated_at"].replace('Z', '+00:00'))
                    if updated_at < cutoff_time:
                        to_remove.append(narrative_id)
                except:
                    continue
            
            for narrative_id in to_remove:
                del self.narratives[narrative_id]
                removed_count += 1
        
        logger.info(f"Removed {removed_count} old narratives")
        return removed_count