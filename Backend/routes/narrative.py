"""
Backend/routes/narrative.py - API endpoints for narrative clusters
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query, HTTPException, status

from Backend.core.dependencies import get_current_active_user
from Backend.services.narrative_service import NarrativeService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/narratives",
    tags=["narratives"],
    dependencies=[Depends(get_current_active_user)]
)

@router.get("/active")
async def get_active_narratives(
    limit: int = Query(20, ge=1, le=50),
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Get active narrative clusters sorted by strength."""
    try:
        narrative_service = NarrativeService()
        narratives = await narrative_service.get_active_narratives(limit=limit)
        
        # Transform for frontend
        clusters = []
        for narrative in narratives:
            clusters.append({
                "id": narrative["id"],
                "title": narrative.get("title", "Untitled"),
                "strength": narrative.get("strength", 0.5),
                "sentiment": narrative.get("sentiment", "neutral"),
                "message_count": len(narrative.get("messages", [])),
                "entities": list(narrative.get("entities", []))[:5],  # Top 5 entities
                "last_update": narrative.get("last_update", 0),
                "summary": narrative.get("summary", "")
            })
        
        # Calculate connections between narratives
        connections = []
        for i, n1 in enumerate(narratives):
            entities1 = set(n1.get("entities", []))
            for j, n2 in enumerate(narratives[i+1:], i+1):
                entities2 = set(n2.get("entities", []))
                if entities1 and entities2:
                    overlap = len(entities1 & entities2)
                    if overlap >= 2:  # At least 2 common entities
                        connections.append({
                            "source": n1["id"],
                            "target": n2["id"],
                            "strength": min(1.0, overlap / 5)  # Normalize
                        })
        
        return {
            "clusters": clusters,
            "connections": connections,
            "total": len(clusters)
        }
        
    except Exception as e:
        logger.error(f"Error getting active narratives: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve narratives"
        )

@router.get("/{narrative_id}")
async def get_narrative_details(
    narrative_id: str,
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Get detailed information about a specific narrative."""
    try:
        narrative_service = NarrativeService()
        
        # Get narrative details
        narrative = await narrative_service.get_narrative_details(narrative_id)
        if not narrative:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Narrative not found"
            )
        
        # Get messages
        messages = await narrative_service.get_narrative_messages(narrative_id, limit=20)
        
        # Get related narratives
        related = await narrative_service.find_related_narratives(narrative_id, limit=5)
        
        # Format response
        return {
            "narrative": {
                "id": narrative["id"],
                "title": narrative.get("title", "Untitled"),
                "strength": narrative.get("strength", 0.5),
                "sentiment": narrative.get("sentiment", "neutral"),
                "message_count": len(narrative.get("messages", [])),
                "entities": list(narrative.get("entities", [])),
                "created": narrative.get("created", 0),
                "last_update": narrative.get("last_update", 0),
                "summary": narrative.get("summary", ""),
                "sentiment_scores": narrative.get("sentiment_scores", {})
            },
            "messages": [
                {
                    "news_id": msg.get("news_id"),
                    "title": msg.get("title"),
                    "time_reported": msg.get("time_reported"),
                    "interpretation": msg.get("interpretation"),
                    "sentiment": msg.get("sentiment"),
                    "entities": msg.get("extracted_entities", [])
                }
                for msg in messages
            ],
            "related_narratives": [
                {
                    "id": r["id"],
                    "title": r.get("title", "Untitled"),
                    "similarity": r.get("similarity", 0),
                    "strength": r.get("strength", 0.5),
                    "sentiment": r.get("sentiment", "neutral")
                }
                for r in related
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting narrative details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve narrative details"
        )

@router.get("/{narrative_id}/messages")
async def get_narrative_messages(
    narrative_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Get messages belonging to a specific narrative."""
    try:
        narrative_service = NarrativeService()
        messages = await narrative_service.get_narrative_messages(narrative_id, limit=limit)
        
        return {
            "narrative_id": narrative_id,
            "messages": [
                {
                    "news_id": msg.get("news_id"),
                    "title": msg.get("title"),
                    "time_reported": msg.get("time_reported"),
                    "interpretation": msg.get("interpretation"),
                    "sentiment": msg.get("sentiment"),
                    "interpretation_tags": msg.get("interpretation_tags", []),
                    "entities": msg.get("extracted_entities", [])
                }
                for msg in messages
            ],
            "total": len(messages)
        }
        
    except Exception as e:
        logger.error(f"Error getting narrative messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve messages"
        )

@router.get("/stats/summary")
async def get_narrative_stats(
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Get summary statistics about narratives."""
    try:
        narrative_service = NarrativeService()
        narratives = await narrative_service.get_active_narratives(limit=100)
        
        # Calculate stats
        total_narratives = len(narratives)
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        total_messages = 0
        
        for narrative in narratives:
            sentiment = narrative.get("sentiment", "neutral")
            sentiment_counts[sentiment] += 1
            total_messages += len(narrative.get("messages", []))
        
        # Top entities across all narratives
        all_entities = defaultdict(int)
        for narrative in narratives:
            for entity in narrative.get("entities", []):
                all_entities[entity] += 1
        
        top_entities = sorted(
            all_entities.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        return {
            "total_narratives": total_narratives,
            "total_messages": total_messages,
            "sentiment_distribution": sentiment_counts,
            "top_entities": [
                {"name": entity, "count": count}
                for entity, count in top_entities
            ],
            "average_narrative_size": total_messages / total_narratives if total_narratives > 0 else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting narrative stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )

@router.post("/refresh")
async def refresh_narratives(
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Force refresh of narrative clustering from recent messages."""
    try:
        # This endpoint could trigger re-clustering of recent messages
        # For now, just return success
        narrative_service = NarrativeService()
        
        # Clean up old narratives
        removed = await narrative_service.cleanup_old_narratives(max_age_hours=48)
        
        return {
            "status": "success",
            "message": "Narratives refreshed",
            "removed_old": removed
        }
        
    except Exception as e:
        logger.error(f"Error refreshing narratives: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh narratives"
        )

# Helper to import defaultdict
from collections import defaultdict
