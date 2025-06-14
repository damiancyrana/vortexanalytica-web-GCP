"""
API routes for narrative clustering functionality.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from Backend.core.dependencies import get_current_active_user
from Backend.services.narrative_service import NarrativeService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/narratives",
    tags=["narratives"],
    dependencies=[Depends(get_current_active_user)]
)

# Get or create the narrative service instance
_narrative_service: Optional[NarrativeService] = None

def get_narrative_service() -> NarrativeService:
    """Get the narrative service instance."""
    global _narrative_service
    if _narrative_service is None:
        _narrative_service = NarrativeService()
    return _narrative_service

@router.get("/active")
async def get_active_narratives(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get all active narrative clusters within the specified time window.
    
    Args:
        hours: Number of hours to look back (1-168)
    
    Returns:
        List of active narratives with their metadata
    """
    try:
        service = get_narrative_service()
        narratives = await service.get_active_narratives(hours=hours)
        
        # Add graph layout hints
        for i, narrative in enumerate(narratives):
            # Simple circular layout based on index
            angle = (i / len(narratives)) * 2 * 3.14159
            narrative["layout_hint"] = {
                "x": 0.5 + 0.3 * (i % 3 - 1),
                "y": 0.5 + 0.3 * ((i // 3) % 3 - 1)
            }
        
        return {
            "narratives": narratives,
            "count": len(narratives),
            "time_window_hours": hours
        }
    except Exception as e:
        logger.error(f"Error getting active narratives: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve narratives")

@router.get("/{narrative_id}")
async def get_narrative_details(
    narrative_id: str,
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get detailed information about a specific narrative.
    
    Args:
        narrative_id: The ID of the narrative
    
    Returns:
        Detailed narrative information including all messages
    """
    try:
        service = get_narrative_service()
        details = await service.get_narrative_details(narrative_id)
        
        if not details:
            raise HTTPException(status_code=404, detail="Narrative not found")
        
        return details
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting narrative details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve narrative details")

@router.get("/{narrative_id}/related")
async def get_related_narratives(
    narrative_id: str,
    max_results: int = Query(5, ge=1, le=20, description="Maximum number of related narratives"),
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Find narratives related to the given narrative.
    
    Args:
        narrative_id: The ID of the source narrative
        max_results: Maximum number of related narratives to return
    
    Returns:
        List of related narratives with similarity scores
    """
    try:
        service = get_narrative_service()
        
        # Check if narrative exists
        narrative = await service.get_narrative_details(narrative_id)
        if not narrative:
            raise HTTPException(status_code=404, detail="Narrative not found")
        
        # Find related narratives
        related = await service.find_related_narratives(narrative_id, max_results)
        
        # Fetch details for each related narrative
        related_details = []
        for related_id, similarity in related:
            details = await service.get_narrative_details(related_id)
            if details:
                related_details.append({
                    "narrative": {
                        "id": details["id"],
                        "primary_theme": details["primary_theme"],
                        "strength": details["strength"],
                        "message_count": details["message_count"]
                    },
                    "similarity": similarity
                })
        
        return {
            "source_narrative_id": narrative_id,
            "related_narratives": related_details,
            "count": len(related_details)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding related narratives: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to find related narratives")

@router.get("/graph/connections")
async def get_narrative_connections(
    min_similarity: float = Query(0.3, ge=0, le=1, description="Minimum similarity threshold"),
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get connections between all active narratives for graph visualization.
    
    Args:
        min_similarity: Minimum similarity score to include a connection
        hours: Time window in hours
    
    Returns:
        Graph data with nodes (narratives) and edges (connections)
    """
    try:
        service = get_narrative_service()
        narratives = await service.get_active_narratives(hours=hours)
        
        nodes = []
        edges = []
        
        # Create nodes
        for narrative in narratives:
            nodes.append({
                "id": narrative["id"],
                "label": narrative["primary_theme"],
                "strength": narrative["strength"],
                "market_impact": narrative["market_impact"],
                "message_count": len(narrative["messages"]),
                "sentiment": max(narrative["sentiment_distribution"].items(), key=lambda x: x[1])[0] if narrative["sentiment_distribution"] else "Neutral"
            })
        
        # Create edges between related narratives
        processed_pairs = set()
        
        for i, narrative in enumerate(narratives):
            related = await service.find_related_narratives(narrative["id"], max_results=10)
            
            for related_id, similarity in related:
                if similarity >= min_similarity:
                    # Create a sorted pair to avoid duplicate edges
                    pair = tuple(sorted([narrative["id"], related_id]))
                    
                    if pair not in processed_pairs:
                        processed_pairs.add(pair)
                        edges.append({
                            "source": narrative["id"],
                            "target": related_id,
                            "weight": similarity
                        })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "min_similarity": min_similarity
        }
    except Exception as e:
        logger.error(f"Error getting narrative connections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve narrative connections")

@router.post("/cleanup")
async def cleanup_old_narratives(
    days: int = Query(7, ge=1, le=30, description="Remove narratives older than this many days"),
    current_user_session: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Admin endpoint to cleanup old narratives.
    
    Args:
        days: Number of days to keep narratives
    
    Returns:
        Number of narratives removed
    """
    try:
        # TODO: Add admin permission check
        user_id = current_user_session.get('user_id')
        logger.warning(f"User {user_id} triggered narrative cleanup (older than {days} days)")
        
        service = get_narrative_service()
        removed_count = await service.cleanup_old_narratives(days=days)
        
        return {
            "removed_count": removed_count,
            "days": days,
            "performed_by": user_id
        }
    except Exception as e:
        logger.error(f"Error during narrative cleanup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cleanup narratives")