# Database Seeding Strategy

## Problem

Previously, LLM models were hardcoded in the Alembic migration file (`20251218_0421_add_llm_models_table.py`). This approach had several issues:

1. ❌ **Mixed Concerns** - Schema changes (CREATE TABLE) mixed with data (INSERT)
2. ❌ **Limited Models** - Only 4 models (missing GPT-4o, O1-series, etc.)
3. ❌ **Outdated Pricing** - Hard to update without creating new migrations
4. ❌ **Not Maintainable** - Reference data changes more frequently than schema

## Solution

We now use a **dedicated seed script** approach:

### New Workflow

```bash
# 1. Run migrations (creates tables)
docker exec trading-backend alembic upgrade head

# 2. Run seeds (populates data)
docker exec trading-backend python seed_database.py
```

### Benefits

✅ **Separation of Concerns** - Schema in migrations, data in seeds  
✅ **Idempotent** - Can run multiple times safely (upsert behavior)  
✅ **8 Models** - Includes all current OpenAI models  
✅ **Accurate Pricing** - Updated costs as of January 2026  
✅ **Easy Updates** - Just edit seed file and rerun (no migration needed)  
✅ **Better Documentation** - Rich metadata about each model

## Available LLM Models (Post-Seeding)

| Model | Cost/Execution | Speed | Quality | Use Case |
|-------|---------------|-------|---------|----------|
| **GPT-3.5 Turbo** | $0.010 | Fast | Good | Risk management, reporting |
| **GPT-4** | $0.150 | Medium | Excellent | Complex strategy |
| **GPT-4 Turbo** | $0.080 | Fast | Excellent | All-purpose (Default) |
| **GPT-4o** | $0.050 | Very Fast | Excellent | Chart analysis, multimodal |
| **GPT-4o Mini** | $0.005 | Very Fast | Very Good | High volume, cost-sensitive |
| **O1 Preview** | $0.200 | Slow | Exceptional | Advanced reasoning |
| **O1 Mini** | $0.040 | Medium | Excellent | Balanced reasoning |
| **LM Studio** | $0.000 | Slow | Variable | Dev/testing (local) |

## Seed Files

All seed scripts are located in `backend/app/seeds/`:

- `llm_models.py` - LLM model registry with pricing
- `__init__.py` - Package exports
- `README.md` - Detailed documentation

## Running Seeds

### After Fresh Database Setup
```bash
docker-compose up -d
docker exec trading-backend alembic upgrade head
docker exec trading-backend python seed_database.py
```

### After Data Loss (docker-compose down -v)
```bash
docker-compose up -d
docker exec trading-backend alembic upgrade head
docker exec trading-backend python seed_database.py  # ← Important!
```

### To Update Model Pricing/Info
```bash
# Edit backend/app/seeds/llm_models.py
# Then run:
docker exec trading-backend python seed_database.py
```

## Migration History

- **20251218_0421** - Created `llm_models` table with 4 hardcoded models
- **20260121_remove_seeds** - Documentation migration marking shift to seed-based approach

## Future Enhancements

Consider adding more seed files for:
- Default pipeline templates
- Example scanners
- Sample strategies
- Tutorial data for new users

## For Developers

When adding new reference data that should be in the database:

1. Create a new seed file in `app/seeds/`
2. Import and call it in `seed_database.py`
3. Document it in `app/seeds/README.md`
4. Update this file with the new seed information

**Never** add INSERT statements to Alembic migrations for reference data. Use seeds instead.
