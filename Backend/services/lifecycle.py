"""
Application lifecycle module (Production Only).
Initializes Firebase Admin SDK, Pub/Sub service, and Redis.
"""
from __future__ import annotations

import logging
import orjson
from orjson import JSONDecodeError

import firebase_admin
from firebase_admin import credentials

from Backend.core.config import get_settings
from Backend.services.email_service import EmailService
from Backend.services.pubsub_service import PubSubService
from Backend.services.news_service import NewsService

logger = logging.getLogger(__name__)

# Global service instances
_pubsub_service = None
_news_service = None


async def app_startup() -> None:
    """Initializes services at application startup."""
    global _pubsub_service, _news_service
    
    logger.info("Starting Vortex Analytica application...")
    try:
        settings = get_settings()
    except Exception as e:
        logger.critical("Stopping application due to configuration error.")
        raise SystemExit(f"Application cannot start due to configuration error: {e}")
    
    # Initialize Firebase Admin SDK
    try:
        if not firebase_admin._apps:
            logger.info(f"Fetching Firebase Admin SDK key from secret: {settings.firebase_service_account_secret_id}")
            firebase_key_json_str = settings.get_secret(settings.firebase_service_account_secret_id)
            
            # Verify content is not empty
            if not firebase_key_json_str:
                logger.critical("Firebase key is empty!")
                raise ValueError("Firebase service account key is empty")
            
            # Parse JSON
            try:
                firebase_credentials_dict = orjson.loads(firebase_key_json_str)
            except JSONDecodeError as json_err:
                logger.critical(f"Invalid Firebase key format: {json_err}")
                raise ValueError(f"Invalid Firebase key format: {json_err}")
            
            # Validate required fields in Firebase key
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_fields = [field for field in required_fields if field not in firebase_credentials_dict]
            
            if missing_fields:
                logger.critical(f"Missing required fields in Firebase key: {', '.join(missing_fields)}")
                raise ValueError(f"Firebase key missing required fields: {', '.join(missing_fields)}")
            
            # Additional check for service account type
            if firebase_credentials_dict.get('type') != 'service_account':
                logger.critical("Invalid Firebase key type: expected 'service_account'")
                raise ValueError("Invalid Firebase key type: expected 'service_account'")
            
            # Create and initialize
            cred = credentials.Certificate(firebase_credentials_dict)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully.")
        else:
            logger.info("Firebase Admin SDK already initialized.")
    except (JSONDecodeError, ValueError, FileNotFoundError, TypeError) as e:
        logger.critical(f"Critical error initializing Firebase Admin SDK: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Could not initialize Firebase Admin SDK: {e}") from e
    except Exception as e:
        logger.critical(f"Unknown error initializing Firebase Admin SDK: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Unexpected error initializing Firebase: {e}") from e
    
    # Initialize NewsService with Redis
    try:
        logger.info("Initializing NewsService with Redis...")
        _news_service = NewsService()
        
        # Test basic Redis operations (asynchronous)
        test_count = await _news_service.get_messages_count()
        logger.info(f"Redis connection verified. Messages in database: {test_count}")
        
        # Optional: clean old messages at startup
        cleaned_count = await _news_service.cleanup_old_messages(max_age_seconds=7 * 24 * 3600)  # 7 days
        if cleaned_count > 0:
            logger.info(f"Cleaned {cleaned_count} old messages at startup")
            
    except Exception as e:
        logger.critical(f"Critical error initializing NewsService with Redis: {e}", exc_info=True)
        raise SystemExit(f"Application startup failed: Could not initialize NewsService with Redis: {e}") from e
    
    # Initialize Pub/Sub Service
    try:
        logger.info("Initializing Pub/Sub service...")
        _pubsub_service = PubSubService(settings)
        
        # Start listening asynchronously for all topics
        if await _pubsub_service.start_listener_async():
            logger.info("Pub/Sub service started successfully (standard + critical + calendar + moc + regular).")
        else:
            logger.warning("Failed to start Pub/Sub listening, but application continues.")
    except Exception as e:
        logger.error(f"Error initializing Pub/Sub service: {e}", exc_info=True)
        logger.warning("Application will continue without Pub/Sub service.")
    
    logger.info("Application started successfully in production mode.")


async def app_shutdown() -> None:
    """Releases resources at application shutdown."""
    global _pubsub_service, _news_service
    
    logger.info("Shutting down Vortex Analytica application...")
    
    # Stop Pub/Sub service
    if _pubsub_service:
        try:
            logger.info("Stopping Pub/Sub service...")
            await _pubsub_service.stop_listener_async()
        except Exception as e:
            logger.warning(f"Error stopping Pub/Sub service: {e}", exc_info=True)
    
    # Close Redis connections in NewsService
    if _news_service:
        try:
            logger.info("Closing Redis connections in NewsService...")
            await _news_service.close_connections()
        except Exception as e:
            logger.warning(f"Error closing Redis connections: {e}", exc_info=True)
    
    # Close SMTP connection pool if EmailService was used
    try:
        email_service = EmailService._instance
        if email_service and hasattr(email_service, 'close_all_connections'):
            logger.info("Closing EmailService connections...")
            email_service.close_all_connections()
    except Exception as e:
        logger.warning(f"Error closing EmailService connection pool: {e}", exc_info=True)
    
    # Try to clean up Firebase apps if they exist
    try:
        if firebase_admin._apps:
            logger.info("Cleaning up Firebase applications...")
            for app in list(firebase_admin._apps.values()):
                try:
                    app.delete()
                except Exception as fe:
                    logger.warning(f"Cannot clean up Firebase application: {fe}")
    except Exception as e:
        logger.warning(f"Error cleaning up Firebase applications: {e}")
    
    logger.info("Application shut down successfully.")