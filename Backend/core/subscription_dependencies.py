"""
Moduł zależności dla weryfikacji subskrypcji (Wersja Produkcyjna)
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Any, Optional
from fastapi import Request, Depends, HTTPException, status

from Backend.core.dependencies import get_current_active_user
from Backend.services.stripe_service import get_stripe_service

logger = logging.getLogger(__name__)


async def require_active_subscription(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Dependency która sprawdza czy użytkownik ma aktywną subskrypcję.
    Używaj tej dependency dla endpointów wymagających płatnej subskrypcji.
    """
    
    # Najpierw sprawdź Firebase custom claims (szybkie)
    if current_user.get('subscription_active'):
        # Sprawdź czy claims nie są przestarzałe (starsze niż 1h)
        updated_at = current_user.get('updated_at', 0)
        if time.time() - updated_at < 3600:  # 1 godzina
            return current_user
    
    # Jeśli claims są stare lub brak info o subskrypcji, sprawdź w Stripe
    firebase_uid = current_user.get('user_id')
    stripe_service = get_stripe_service()
    
    try:
        subscription_status = await stripe_service.get_subscription_status(firebase_uid)
        
        if not subscription_status.get('has_access'):
            logger.info(f"Użytkownik {firebase_uid} nie ma aktywnej subskrypcji")
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Wymagana aktywna subskrypcja",
                headers={"X-Subscription-Status": subscription_status.get('status', 'none')}
            )
        
        # Aktualizuj dane użytkownika o info o subskrypcji
        current_user['subscription_status'] = subscription_status.get('status')
        current_user['subscription_active'] = True
        current_user['trial_days_remaining'] = subscription_status.get('trial_days_remaining', 0)
        
        # Asynchronicznie zaktualizuj Firebase claims (bez czekania)
        import asyncio
        asyncio.create_task(
            stripe_service.update_firebase_claims(firebase_uid, subscription_status)
        )
        
        return current_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Błąd podczas sprawdzania subskrypcji: {e}", exc_info=True)
        # W przypadku błędu, pozwól na dostęp jeśli użytkownik miał wcześniej aktywną subskrypcję
        if current_user.get('subscription_active'):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nie można zweryfikować statusu subskrypcji"
        )


async def get_subscription_info(
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Optional[Dict[str, Any]]:
    """
    Opcjonalna dependency która pobiera info o subskrypcji bez wymagania aktywnej subskrypcji.
    Używaj do wyświetlania statusu subskrypcji w UI.
    """
    
    firebase_uid = current_user.get('user_id')
    stripe_service = get_stripe_service()
    
    try:
        return await stripe_service.get_subscription_status(firebase_uid)
    except Exception as e:
        logger.error(f"Błąd podczas pobierania info o subskrypcji: {e}")
        return None


def check_trial_period(subscription_info: Optional[Dict[str, Any]]) -> bool:
    """Sprawdza czy użytkownik jest w okresie próbnym"""
    if not subscription_info:
        return False
    
    return (
        subscription_info.get('status') == 'trialing' and
        subscription_info.get('trial_days_remaining', 0) > 0
    )