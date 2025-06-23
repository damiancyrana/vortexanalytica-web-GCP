"""
Stripe Service dla obsługi płatności i subskrypcji (Wersja Produkcyjna)
"""
from __future__ import annotations

import logging
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

import stripe
from stripe import StripeClient
import firebase_admin
from firebase_admin import auth as firebase_auth

from Backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class StripeService:
    """Singleton service do obsługi integracji Stripe"""
    _instance: Optional[StripeService] = None
    _client: Optional[StripeClient] = None
    _initialized: bool = False
    
    # Stałe dla planu Professional
    PROFESSIONAL_PRICE_ID: Optional[str] = None
    PROFESSIONAL_PRODUCT_ID: Optional[str] = None
    TRIAL_DAYS = 14
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StripeService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        settings = get_settings()
        
        # Sprawdź czy w trybie rozwojowym
        if settings.is_development:
            logger.warning("StripeService w trybie ROZWOJOWYM - funkcje płatności wyłączone")
            self._client = None
            self._initialized = True
            return
        
        # Inicjalizacja Stripe Client
        self._client = StripeClient(settings.STRIPE_SECRET_KEY)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Cache dla zapytań
        self._customer_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 600  # 10 minut
        
        self._initialized = True
        logger.info("StripeService zainicjalizowany")
        
        # Inicjalizacja produktu i ceny (async)
        asyncio.create_task(self._initialize_products())
    
    async def _initialize_products(self):
        """Inicjalizuje lub pobiera istniejące produkty Stripe"""
        # Pomiń w trybie rozwojowym
        if not self._client:
            return
            
        try:
            # Szukaj istniejącego produktu
            products = self._client.products.list(
                active=True,
                limit=100
            )
            
            professional_product = None
            for product in products.data:
                if product.metadata.get('plan_type') == 'professional':
                    professional_product = product
                    break
            
            # Stwórz produkt jeśli nie istnieje
            if not professional_product:
                professional_product = self._client.products.create(
                    name='Vortex Analytica Professional',
                    description='Pełny dostęp do analizy rynkowej w czasie rzeczywistym',
                    metadata={
                        'plan_type': 'professional',
                        'features': 'real-time,satellite,ml-analysis,priority-support'
                    }
                )
                logger.info(f"Utworzono produkt Professional: {professional_product.id}")
            
            self.PROFESSIONAL_PRODUCT_ID = professional_product.id
            
            # Szukaj istniejącej ceny PLN
            prices = self._client.prices.list(
                product=professional_product.id,
                active=True,
                currency='pln',
                limit=100
            )
            
            professional_price = None
            for price in prices.data:
                if price.unit_amount == 49900:  # 499 PLN
                    professional_price = price
                    break
            
            # Stwórz cenę jeśli nie istnieje
            if not professional_price:
                professional_price = self._client.prices.create(
                    unit_amount=49900,  # 499.00 PLN
                    currency='pln',
                    recurring={'interval': 'month'},
                    product=professional_product.id,
                    nickname='Professional Monthly PLN',
                    metadata={'plan': 'professional'}
                )
                logger.info(f"Utworzono cenę Professional PLN: {professional_price.id}")
            
            self.PROFESSIONAL_PRICE_ID = professional_price.id
            
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji produktów Stripe: {e}", exc_info=True)
    
    async def create_or_get_customer(self, firebase_uid: str, email: str) -> stripe.Customer:
        """Tworzy lub pobiera klienta Stripe powiązanego z użytkownikiem Firebase"""
        
        # W trybie rozwojowym zwróć dummy customer
        if not self._client:
            logger.info("Tryb rozwojowy - symulacja customer")
            # Zwróć prosty dict który będzie działał jak Customer object
            return type('Customer', (), {
                'id': 'dev_cus_123',
                'email': email,
                'metadata': {'firebase_uid': firebase_uid}
            })()
        
        # Sprawdź cache
        cache_key = f"{firebase_uid}:{email}"
        if cache_key in self._customer_cache:
            cached = self._customer_cache[cache_key]
            if time.time() - cached['timestamp'] < self._cache_ttl:
                return cached['customer']
        
        try:
            # Szukaj po metadanych Firebase UID
            customers = self._client.customers.list(
                email=email,
                limit=1
            )
            
            if customers.data:
                customer = customers.data[0]
                # Aktualizuj metadata jeśli brak Firebase UID
                if customer.metadata.get('firebase_uid') != firebase_uid:
                    customer = self._client.customers.modify(
                        customer.id,
                        metadata={'firebase_uid': firebase_uid}
                    )
                    logger.info(f"Zaktualizowano metadata klienta {customer.id}")
            else:
                # Stwórz nowego klienta
                customer = self._client.customers.create(
                    email=email,
                    metadata={
                        'firebase_uid': firebase_uid,
                        'created_via': 'vortex_app',
                        'timestamp': str(int(time.time()))
                    }
                )
                logger.info(f"Utworzono nowego klienta Stripe: {customer.id} dla {firebase_uid}")
            
            # Zapisz w cache
            self._customer_cache[cache_key] = {
                'customer': customer,
                'timestamp': time.time()
            }
            
            return customer
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia/pobierania klienta: {e}", exc_info=True)
            raise
    
    async def create_checkout_session(
        self,
        firebase_uid: str,
        email: str,
        success_url: str,
        cancel_url: str
    ) -> Dict[str, Any]:
        """Tworzy sesję Checkout z 14-dniowym okresem próbnym"""
        
        # W trybie rozwojowym zwróć dummy URL
        if not self._client:
            logger.info("Tryb rozwojowy - symulacja checkout session")
            return {
                'checkout_url': f"{success_url}?session_id=dev_session_123",
                'session_id': 'dev_session_123'
            }
        
        if not self.PROFESSIONAL_PRICE_ID:
            raise ValueError("Price ID nie został zainicjalizowany")
        
        try:
            customer = await self.create_or_get_customer(firebase_uid, email)
            
            checkout_session = self._client.checkout.sessions.create(
                customer=customer.id,
                line_items=[{
                    'price': self.PROFESSIONAL_PRICE_ID,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=cancel_url,
                subscription_data={
                    'trial_period_days': self.TRIAL_DAYS,
                    'metadata': {
                        'firebase_uid': firebase_uid,
                        'plan': 'professional'
                    }
                },
                payment_method_types=['card', 'blik', 'p24'],  # Metody płatności dla Polski
                billing_address_collection='required',
                locale='pl',
                metadata={
                    'firebase_uid': firebase_uid
                }
            )
            
            logger.info(f"Utworzono sesję checkout: {checkout_session.id}")
            return {
                'checkout_url': checkout_session.url,
                'session_id': checkout_session.id
            }
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia sesji checkout: {e}", exc_info=True)
            raise
    
    async def create_portal_session(
        self,
        firebase_uid: str,
        return_url: str
    ) -> Dict[str, str]:
        """Tworzy sesję Customer Portal do zarządzania subskrypcją"""
        
        # W trybie rozwojowym zwróć dummy URL
        if not self._client:
            logger.info("Tryb rozwojowy - symulacja portal session")
            return {
                'portal_url': f"{return_url}?portal=development",
                'session_id': 'dev_portal_123'
            }
        
        try:
            # Znajdź klienta po Firebase UID
            customers = self._client.customers.list(
                limit=1,
                metadata={'firebase_uid': firebase_uid}
            )
            
            if not customers.data:
                raise ValueError("Nie znaleziono klienta Stripe dla tego użytkownika")
            
            portal_session = self._client.billing_portal.sessions.create(
                customer=customers.data[0].id,
                return_url=return_url,
                locale='pl'
            )
            
            return {
                'portal_url': portal_session.url,
                'session_id': portal_session.id
            }
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia sesji portal: {e}", exc_info=True)
            raise
    
    async def get_subscription_status(self, firebase_uid: str) -> Dict[str, Any]:
        """Pobiera aktualny status subskrypcji użytkownika"""
        
        # W trybie rozwojowym zawsze zwracaj aktywną subskrypcję
        if not self._client:
            logger.info("Tryb rozwojowy - symulacja aktywnej subskrypcji")
            return {
                'status': 'active',
                'has_access': True,
                'subscription_id': 'dev_sub_123',
                'customer_id': 'dev_cus_123',
                'amount': 49900,
                'currency': 'PLN',
                'interval': 'month',
                'current_period_end': int(time.time()) + 30 * 86400,
                'cancel_at_period_end': False,
                'trial_end': None,
                'trial_days_remaining': 0,
                'created': int(time.time())
            }
        
        try:
            # Znajdź klienta
            customers = self._client.customers.list(
                limit=1,
                metadata={'firebase_uid': firebase_uid}
            )
            
            if not customers.data:
                return {
                    'status': 'no_customer',
                    'has_access': False
                }
            
            # Pobierz aktywne subskrypcje
            subscriptions = self._client.subscriptions.list(
                customer=customers.data[0].id,
                status='all',
                limit=1
            )
            
            if not subscriptions.data:
                return {
                    'status': 'no_subscription',
                    'has_access': False,
                    'customer_id': customers.data[0].id
                }
            
            subscription = subscriptions.data[0]
            
            # Oblicz pozostałe dni trialu
            trial_days_remaining = 0
            if subscription.trial_end:
                trial_days_remaining = max(0,
                    (subscription.trial_end - int(time.time())) // 86400
                )
            
            # Określ czy użytkownik ma dostęp
            has_access = subscription.status in ['active', 'trialing']
            
            return {
                'status': subscription.status,
                'has_access': has_access,
                'subscription_id': subscription.id,
                'customer_id': customers.data[0].id,
                'amount': subscription.items.data[0].price.unit_amount,
                'currency': subscription.currency.upper(),
                'interval': subscription.items.data[0].price.recurring.interval,
                'current_period_end': subscription.current_period_end,
                'cancel_at_period_end': subscription.cancel_at_period_end,
                'trial_end': subscription.trial_end,
                'trial_days_remaining': trial_days_remaining,
                'created': subscription.created
            }
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania statusu subskrypcji: {e}", exc_info=True)
            return {
                'status': 'error',
                'has_access': False,
                'error': str(e)
            }
    
    async def update_firebase_claims(
        self,
        firebase_uid: str,
        subscription_data: Dict[str, Any]
    ):
        """Aktualizuje custom claims w Firebase na podstawie subskrypcji"""
        
        # Pomiń w trybie rozwojowym
        settings = get_settings()
        if settings.is_development:
            logger.info("Tryb rozwojowy - pomijanie aktualizacji Firebase claims")
            return
        
        try:
            custom_claims = {
                'stripe_customer_id': subscription_data.get('customer_id'),
                'subscription_status': subscription_data.get('status'),
                'subscription_active': subscription_data.get('has_access', False),
                'plan': 'professional' if subscription_data.get('has_access') else None,
                'updated_at': int(time.time())
            }
            
            # Dodaj informacje o trialu jeśli istnieją
            if subscription_data.get('trial_end'):
                custom_claims['trial_end'] = subscription_data['trial_end']
            
            firebase_auth.set_custom_user_claims(firebase_uid, custom_claims)
            logger.info(f"Zaktualizowano Firebase claims dla {firebase_uid}")
            
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji Firebase claims: {e}", exc_info=True)
    
    def process_webhook_event(self, event: stripe.Event) -> Dict[str, Any]:
        """Przetwarza webhook event od Stripe"""
        
        # W trybie rozwojowym zawsze zwracaj sukces
        if not self._client:
            logger.info("Tryb rozwojowy - pomijanie webhook")
            return {'processed': True, 'reason': 'development_mode'}
        
        logger.info(f"Przetwarzanie webhook event: {event['type']}")
        
        try:
            if event['type'] == 'customer.subscription.created':
                return self._handle_subscription_created(event['data']['object'])
            
            elif event['type'] == 'customer.subscription.updated':
                return self._handle_subscription_updated(event['data']['object'])
            
            elif event['type'] == 'customer.subscription.deleted':
                return self._handle_subscription_deleted(event['data']['object'])
            
            elif event['type'] == 'invoice.payment_succeeded':
                return self._handle_payment_succeeded(event['data']['object'])
            
            elif event['type'] == 'invoice.payment_failed':
                return self._handle_payment_failed(event['data']['object'])
            
            else:
                logger.info(f"Nieobsługiwany typ eventu: {event['type']}")
                return {'processed': False, 'reason': 'unhandled_event_type'}
                
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania webhook: {e}", exc_info=True)
            raise
    
    def _handle_subscription_created(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        """Obsługuje utworzenie nowej subskrypcji"""
        firebase_uid = subscription.get('metadata', {}).get('firebase_uid')
        if not firebase_uid:
            logger.warning("Brak firebase_uid w metadanych subskrypcji")
            return {'processed': False, 'reason': 'missing_firebase_uid'}
        
        # Aktualizacja claims będzie wykonana asynchronicznie
        return {
            'processed': True,
            'action': 'update_claims',
            'firebase_uid': firebase_uid,
            'subscription_id': subscription['id']
        }
    
    def _handle_subscription_updated(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        """Obsługuje aktualizację subskrypcji"""
        firebase_uid = subscription.get('metadata', {}).get('firebase_uid')
        if not firebase_uid:
            # Spróbuj pobrać z klienta
            customer_id = subscription.get('customer')
            if customer_id:
                customer = self._client.customers.retrieve(customer_id)
                firebase_uid = customer.metadata.get('firebase_uid')
        
        return {
            'processed': True,
            'action': 'update_claims',
            'firebase_uid': firebase_uid,
            'subscription_id': subscription['id']
        }
    
    def _handle_subscription_deleted(self, subscription: Dict[str, Any]) -> Dict[str, Any]:
        """Obsługuje anulowanie subskrypcji"""
        return self._handle_subscription_updated(subscription)
    
    def _handle_payment_succeeded(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Obsługuje udaną płatność"""
        logger.info(f"Płatność zakończona sukcesem dla faktury: {invoice['id']}")
        return {'processed': True, 'action': 'payment_success'}
    
    def _handle_payment_failed(self, invoice: Dict[str, Any]) -> Dict[str, Any]:
        """Obsługuje nieudaną płatność"""
        logger.warning(f"Płatność nieudana dla faktury: {invoice['id']}")
        # Tu można dodać wysyłanie emaili o problemie z płatnością
        return {'processed': True, 'action': 'payment_failed'}
    
    def clear_cache(self, firebase_uid: Optional[str] = None):
        """Czyści cache klientów"""
        if firebase_uid:
            # Usuń wszystkie wpisy dla danego firebase_uid
            keys_to_remove = [k for k in self._customer_cache.keys() if firebase_uid in k]
            for key in keys_to_remove:
                del self._customer_cache[key]
        else:
            self._customer_cache.clear()


# Singleton getter
def get_stripe_service() -> StripeService:
    """Zwraca instancję StripeService"""
    return StripeService()
