from ma_service import get_recent_ma_deals
import json

res = get_recent_ma_deals("WBD")
print("Status:", res.status)
print("Deals:", [d.deal_name for d in res.deals])

res = get_recent_ma_deals("Warner Bros")
print("Status:", res.status)
print("Deals:", [d.deal_name for d in res.deals])
