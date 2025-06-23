"""
Moduł tras płatności Stripe (Wersja Produkcyjna)
"""
from __future__ import annotations

import logging
import stripe
from typing import Dict, Any
from fastapi import FastAPI, Request, Depends, HTTPException, status, BackgroundTasks, Body
from fastapi.responses import ORJSONResponse, RedirectResponse

from Backend.core.dependencies import get_current_active_user
from Backend.core.config import Settings, get_settings
from Backend.services.stripe_service import get_stripe_service

logger = logging.getLogger(__name__)


def register_payment_routes(app: FastAPI, settings: Settings) -> None:
    """Rejestruje trasy związane z płatnościami"""
    
    stripe_service = get_stripe_service()
    
    @app.post("/api/payments/create-checkout-session", response_class=ORJSONResponse)
    async def create_checkout_session(
        current_user_session: Dict[str, Any] = Depends(get_current_active_user),
        settings: Settings = Depends(get_settings)
    ) -> Dict[str, str]:
        """Tworzy sesję Stripe Checkout dla planu Professional"""
        
        firebase_uid = current_user_session.get('user_id')
        email = current_user_session.get('email')
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Brak adresu email w sesji użytkownika"
            )
        
        try:
            # URLs dla przekierowania po płatności
            base_url = str(settings.base_url or f"https://{settings.SESSION_COOKIE_DOMAIN}")
            success_url = f"{base_url}/payment-success"
            cancel_url = f"{base_url}/settings"
            
            result = await stripe_service.create_checkout_session(
                firebase_uid=firebase_uid,
                email=email,
                success_url=success_url,
                cancel_url=cancel_url
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia sesji checkout: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Nie udało się utworzyć sesji płatności"
            )
    
    @app.post("/api/payments/create-portal-session", response_class=ORJSONResponse)
    async def create_portal_session(
        current_user_session: Dict[str, Any] = Depends(get_current_active_user),
        settings: Settings = Depends(get_settings)
    ) -> Dict[str, str]:
        """Tworzy sesję Stripe Customer Portal do zarządzania subskrypcją"""
        
        firebase_uid = current_user_session.get('user_id')
        
        try:
            base_url = str(settings.base_url or f"https://{settings.SESSION_COOKIE_DOMAIN}")
            return_url = f"{base_url}/settings"
            
            result = await stripe_service.create_portal_session(
                firebase_uid=firebase_uid,
                return_url=return_url
            )
            
            return result
            
        except ValueError as e:
            # Użytkownik nie ma jeszcze konta Stripe
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nie znaleziono aktywnej subskrypcji"
            )
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia sesji portal: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Nie udało się otworzyć panelu zarządzania"
            )
    
    @app.get("/api/payments/subscription-status", response_class=ORJSONResponse)
    async def get_subscription_status(
        current_user_session: Dict[str, Any] = Depends(get_current_active_user)
    ) -> Dict[str, Any]:
        """Pobiera aktualny status subskrypcji użytkownika"""
        
        firebase_uid = current_user_session.get('user_id')
        
        try:
            status = await stripe_service.get_subscription_status(firebase_uid)
            return status
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania statusu subskrypcji: {e}", exc_info=True)
            return {
                'status': 'error',
                'has_access': False,
                'error': 'Nie udało się pobrać statusu subskrypcji'
            }
    
    @app.post("/webhook/stripe", include_in_schema=False)
    async def stripe_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        settings: Settings = Depends(get_settings)
    ):
        """Endpoint webhook dla Stripe - weryfikuje podpis i przetwarza eventy"""
        
        # W trybie rozwojowym zwróć od razu sukces
        if settings.is_development:
            logger.info("Webhook Stripe w trybie rozwojowym - pomijanie")
            return {"received": True, "development": True}
        
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        if not sig_header:
            logger.warning("Brak nagłówka stripe-signature w webhook")
            raise HTTPException(status_code=400, detail="Brak podpisu")
        
        try:
            # Weryfikacja podpisu webhook
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            logger.error("Nieprawidłowy payload webhook")
            raise HTTPException(status_code=400, detail="Nieprawidłowy payload")
        except stripe.error.SignatureVerificationError:
            logger.error("Nieprawidłowy podpis webhook")
            raise HTTPException(status_code=400, detail="Nieprawidłowy podpis")
        
        # Przetwarzanie asynchroniczne
        background_tasks.add_task(process_webhook_async, event)
        
        return {"received": True}
    
    @app.get("/payment-success")
    async def payment_success(
        session_id: str,
        current_user_session: Dict[str, Any] = Depends(get_current_active_user)
    ):
        """Strona sukcesu po płatności - aktualizuje claims i przekierowuje"""
        
        try:
            # Pobierz sesję checkout
            session = stripe.checkout.Session.retrieve(session_id)
            
            if session.payment_status == 'paid' or session.subscription:
                # Aktualizuj status subskrypcji
                firebase_uid = current_user_session.get('user_id')
                subscription_data = await stripe_service.get_subscription_status(firebase_uid)
                
                # Aktualizuj Firebase claims
                await stripe_service.update_firebase_claims(firebase_uid, subscription_data)
                
                # Wyczyść cache
                stripe_service.clear_cache(firebase_uid)
            
            return RedirectResponse(url="/index?payment=success", status_code=303)
            
        except Exception as e:
            logger.error(f"Błąd podczas obsługi payment success: {e}", exc_info=True)
            return RedirectResponse(url="/settings?payment=error", status_code=303)


async def process_webhook_async(event: stripe.Event):
    """Asynchroniczne przetwarzanie webhook events"""
    
    try:
        stripe_service = get_stripe_service()
        result = stripe_service.process_webhook_event(event)
        
        # Jeśli trzeba zaktualizować Firebase claims
        if result.get('action') == 'update_claims' and result.get('firebase_uid'):
            subscription_data = await stripe_service.get_subscription_status(
                result['firebase_uid']
            )
            await stripe_service.update_firebase_claims(
                result['firebase_uid'], 
                subscription_data
            )
            stripe_service.clear_cache(result['firebase_uid'])
            
        logger.info(f"Webhook {event['type']} przetworzony pomyślnie")
        
    except Exception as e:
        logger.error(f"Błąd podczas przetwarzania webhook: {e}", exc_info=True)
        