from ma_service import get_recent_ma_deals
import json

res = get_recent_ma_deals("MSFT")
print(res.status)
for d in res.deals:
    print(f"- {d.deal_name}: {d.deal_value}")
    print(f"  Buy: {d.buy_side_advisors}")
    print(f"  Sell: {d.sell_side_advisors}")
