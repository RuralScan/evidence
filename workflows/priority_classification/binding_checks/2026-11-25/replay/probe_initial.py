import ee,json,datetime
from pathlib import Path
import sys
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
ee.Initialize();ee.data.setDeadline(45000)
def save(name,fn):
 try: result={'status':'observed','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'result':fn()}
 except Exception as e: result={'status':'unavailable','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':str(e)[:1200]}
 (out/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(name,json.dumps(result)[:1200],flush=True)
for key,asset in [('aqueduct_annual','WRI/Aqueduct_Water_Risk/V4/baseline_annual'),('aqueduct_monthly','WRI/Aqueduct_Water_Risk/V4/baseline_monthly')]:
 fc=ee.FeatureCollection(asset)
 save(key+'_schema',lambda: {'count':fc.size().getInfo(),'first_properties':fc.first().toDictionary().getInfo()})
for key,asset in [('fao_di','projects/UNFAO/ASIS/DI-A'),('fao_asi','projects/UNFAO/ASIS/ASI-A'),('fao_hdf','projects/UNFAO/ASIS/HDF'),('fao_mvhi','projects/UNFAO/ASIS/MVHI-A')]:
 save(key+'_asset',lambda asset=asset:ee.data.getAsset(asset))
 save(key+'_first',lambda asset=asset:ee.ImageCollection(asset).limit(1).getInfo())
spei=ee.ImageCollection('CSIC/SPEI/2_11')
save('spei_times',lambda:{'count':spei.size().getInfo(),'first':spei.sort('system:time_start').first().getInfo(),'last':spei.sort('system:time_start',False).first().getInfo()})
