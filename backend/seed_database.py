#!/usr/bin/env python3
"""
Database Seeding Script

Run this script after migrations to populate the database with default data.

Usage:
    python seed_database.py
    
Or from Docker:
    docker exec trading-backend python seed_database.py
"""
import sys
import logging
from app.database import SessionLocal
from app.seeds import seed_llm_models

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run all database seeds."""
    logger.info("🌱 Starting database seeding...")
    
    db = SessionLocal()
    
    try:
        # Seed LLM models
        logger.info("Seeding LLM models...")
        seed_llm_models(db)
        
        # Add more seed functions here as needed
        # seed_example_pipelines(db)
        # seed_default_settings(db)
        
        logger.info("✨ Database seeding completed successfully!")
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error during database seeding: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
