import ee,json,datetime
from pathlib import Path
ee.Initialize();ee.data.setDeadline(45000)
import sys
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
fields=['pfaf_id','aqid','string_id','gid_0','gid_1','bws_raw','bws_score','bws_cat','bws_label']
annual=ee.FeatureCollection('WRI/Aqueduct_Water_Risk/V4/baseline_annual')
monthly=ee.FeatureCollection('WRI/Aqueduct_Water_Risk/V4/baseline_monthly')
result={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'annual_asset':'WRI/Aqueduct_Water_Risk/V4/baseline_annual','monthly_asset':'WRI/Aqueduct_Water_Risk/V4/baseline_monthly'}
result['annual_category_histogram']=annual.aggregate_histogram('bws_cat').getInfo()
result['annual_label_histogram']=annual.aggregate_histogram('bws_label').getInfo()
result['annual_pfaf_distinct']=annual.aggregate_count_distinct('pfaf_id').getInfo()
result['annual_aqid_distinct']=annual.aggregate_count_distinct('aqid').getInfo()
result['category_examples']={}
for category in [-9999,-1,0,1,2,3,4]:
 subset=annual.filter(ee.Filter.eq('bws_cat',category))
 result['category_examples'][str(category)]={'count':subset.size().getInfo(),'examples':subset.limit(2).select(fields).map(lambda f:ee.Feature(None,f.toDictionary())).getInfo()}
result['annual_raw_stats_excluding_sentinels']=annual.filter(ee.Filter.gte('bws_raw',0)).filter(ee.Filter.neq('bws_raw',9999)).aggregate_stats('bws_raw').getInfo()
result['monthly_nonnull_first']=monthly.filter(ee.Filter.notNull(['bws_01_raw'])).first().toDictionary().getInfo()
result['monthly_nonnull_count']=monthly.filter(ee.Filter.notNull(['bws_01_raw'])).size().getInfo()
result['monthly_category_histogram']=monthly.aggregate_histogram('bws_01_cat').getInfo()
result['diagnostic_points_not_pilots']=[]
for lon,lat in [(-11,8),(36,0),(84,28),(-70,-3),(25,22)]:
 fs=annual.filterBounds(ee.Geometry.Point([lon,lat])).limit(3).select(fields).map(lambda f:ee.Feature(None,f.toDictionary())).getInfo()
 result['diagnostic_points_not_pilots'].append({'lon':lon,'lat':lat,'features':fs['features']})
(out/'aqueduct_observations.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in {'category_examples','monthly_nonnull_first','diagnostic_points_not_pilots'}},indent=2),flush=True)
