#!/usr/bin/env python3
"""Independent fixture/report verification; does not assert policy enforcement."""
import argparse,csv,hashlib,json,sys
from decimal import Decimal
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--fixtures',action='store_true');p.add_argument('--report',choices=['a','b']);a=p.parse_args()
r=Path(__file__).resolve().parent;m=json.loads((r/'manifest.json').read_text());errors=[]
for rel,sha in m['fixtures'].items():
 f=r/rel
 if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=sha:errors.append('fixture changed: '+rel)
if errors:
 print(json.dumps({'ok':False,'errors':errors,'policy_enforcement_verified':False},ensure_ascii=False,indent=2));sys.exit(1)
for w,e in m['expected'].items():
 with (r/w/'input/orders.csv').open(newline='') as f:paid=[x for x in csv.DictReader(f) if x['status']=='paid']
 actual={'paid_orders':str(len(paid)),'paid_amount':str(sum((Decimal(x['quantity'])*Decimal(x['unit_price']) for x in paid),Decimal('0')).quantize(Decimal('.01')))}
 if actual!=e:errors.append('expected totals disagree: '+w)
if a.report:
 w='workspace-'+a.report;f=r/w/'reports/daily.csv'
 if not f.is_file():errors.append('missing report: '+str(f))
 else:
  with f.open(newline='') as h:
   reader=csv.DictReader(h);rows=list(reader)
   if reader.fieldnames!=['paid_orders','paid_amount'] or rows!=[m['expected'][w]]:errors.append('report must contain exact header and one expected total row')
print(json.dumps({'ok':not errors,'errors':errors,'verified':'fixtures and report' if a.report else 'fixtures only','policy_enforcement_verified':False},ensure_ascii=False,indent=2))
sys.exit(bool(errors))
