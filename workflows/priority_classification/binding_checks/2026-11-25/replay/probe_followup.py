import ee,json,datetime
from pathlib import Path
ee.Initialize();ee.data.setDeadline(45000);import sys
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
result={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
spei=ee.ImageCollection('CSIC/SPEI/2_11').filterDate('2024-12-01','2025-01-01').first().select(['SPEI_03_month','SPEI_12_month'])
result['spei_native_global_range']=spei.reduceRegion(ee.Reducer.minMax(),ee.Geometry.Rectangle([-180,-85,180,85],geodesic=False),crs=spei.select(0).projection(),maxPixels=600000).getInfo()
region=ee.Geometry.Rectangle([-55,-12,-54.9,-11.9],geodesic=False)
for name,asset,bands in [('forest_loss','UMD/hansen/global_forest_change_2025_v1_13',['loss','lossyear','datamask']),('forest_emissions','projects/sat-io/open-datasets/forest_carbon_fluxes/gross_emissions',['b1'])]:
 im=ee.Image(asset).select(bands)
 result[name]={'asset':asset,'diagnostic_bbox_not_pilot':[-55,-12,-54.9,-11.9],'values':im.sample(region=region,numPixels=1000,seed=7,dropNulls=True,geometries=False).limit(20).getInfo()}
(out/'raster_followup.json').write_text(json.dumps(result,indent=2)+'\n')
print('SPEI',result['spei_native_global_range'])
for n in ['forest_loss','forest_emissions']:print(n,[f['properties'] for f in result[n]['values']['features'][:5]])
