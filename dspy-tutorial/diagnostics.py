import json
def classification(status,body):
 try:
  p=json.loads(body)
  if status==429 and p['error'].get('type')=='insufficient_quota' and p['error'].get('code')=='credit_balance_exhausted':return 'INSUFFICIENT_API_CREDITS'
 except (ValueError,KeyError,TypeError,AttributeError):pass
 return 'PROVIDER_OR_PROTOCOL_STOP'
