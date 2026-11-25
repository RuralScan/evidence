import ee,json,datetime
from pathlib import Path
ee.Initialize();ee.data.setDeadline(45000)
import sys
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
assets={'spei':'CSIC/SPEI/2_11','forest_loss':'UMD/hansen/global_forest_change_2025_v1_13','forest_emissions':'projects/sat-io/open-datasets/forest_carbon_fluxes/gross_emissions'}
for name,asset in assets.items():
 result={'asset':asset,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  image=ee.ImageCollection(asset).filterDate('2024-12-01','2025-01-01').first().select(['SPEI_03_month','SPEI_12_month']) if name=='spei' else ee.Image(asset)
  bands=['treecover2000','lossyear','datamask'] if name=='forest_loss' else image.bandNames().getInfo()
  image=image.select(bands);result['metadata']=image.getInfo()
  result['samples_not_pilot']=[{'lon':lon,'lat':lat,'values':image.reduceRegion(ee.Reducer.first(),ee.Geometry.Point([lon,lat]),maxPixels=4).getInfo()} for lon,lat in [(-11,8),(36,0),(84,28),(-70,-3),(0,0)]]
  if name=='spei':
   result['december_2024_global_native_range']=image.reduceRegion(ee.Reducer.minMax(),ee.Geometry.Rectangle([-180,-85,180,85],geodesic=False),maxPixels=300000).getInfo()
  result['status']='sample_checked'
 except Exception as e:result['status']='unavailable';result['error']=str(e)[:800]
 (out/(name+'_observations.json')).write_text(json.dumps(result,indent=2)+'\n');print(name,result['status'],result.get('samples_not_pilot'),result.get('december_2024_global_native_range'),result.get('error'),flush=True)
