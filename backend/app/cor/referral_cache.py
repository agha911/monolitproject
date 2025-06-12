from cachetools import TTLCache

# Кэш: максимум 10 000 записей, живут по 1 часу
referral_cache = TTLCache(maxsize=10000, ttl=3600)
