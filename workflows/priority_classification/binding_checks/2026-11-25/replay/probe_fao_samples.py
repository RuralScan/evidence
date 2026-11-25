from pathlib import Path
import urllib.request,urllib.parse,json,datetime
import sys
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
queries={}
def get(label,url,params=None):
 if params:url+='?'+urllib.parse.urlencode({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in params.items()})
 try:
  with urllib.request.urlopen(url,timeout=35) as r: data=json.load(r)
  rec={'url':url,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'response':data}
 except Exception as e:rec={'url':url,'error':str(e)[:600]}
 (out/(label+'.json')).write_text(json.dumps(rec,indent=2)+'\n');return rec.get('response',{})
for product in ['DI_A','ASI_A']:
 base='https://asis-esri.fao.org/image/rest/services/'+product+'/ImageServer'
 rows=get('fao_'+product+'_2024_rows',base+'/query',{'f':'pjson','where':"Year = 2024 AND Season = 'Season 1' AND Land_Type = 'Cropland'",'outFields':'OBJECTID,Name,Year,Season,Land_Type','returnGeometry':'false','resultRecordCount':4})
 features=rows.get('features',[]);print(product,[f['attributes'] for f in features],flush=True)
 if not features:continue
 oid=features[0]['attributes']['OBJECTID']
 summary=[]
 for lon,lat in [(-11,8),(36,0),(84,28),(20,10),(25,22)]:
  rec=get(f'fao_{product}_sample_{lon}_{lat}',base+'/identify',{'f':'pjson','geometry':{'x':lon,'y':lat,'spatialReference':{'wkid':4326}},'geometryType':'esriGeometryPoint','returnGeometry':'false','returnCatalogItems':'false','mosaicRule':{'mosaicMethod':'esriMosaicLockRaster','lockRasterIds':[oid]},'renderingRule':{'rasterFunction':'None'}})
  summary.append({'lon':lon,'lat':lat,'value':rec.get('value'),'properties':rec.get('properties'),'error':rec.get('error')})
 print(product,'raw samples',json.dumps(summary),flush=True)
 # Query distinct catalog dimensions to avoid inferring from marketing coverage.
 catalog=get('fao_'+product+'_dimensions',base+'/query',{'f':'json','where':'1=1','outFields':'Year,Season,Land_Type','returnGeometry':'false','returnDistinctValues':'true','resultRecordCount':1000})
 print(product,'dimension_records',len(catalog.get('features',[])),flush=True)
get('fao_hdf_item','https://www.arcgis.com/sharing/rest/content/items/71a7a03a60e44734adf8c2bab91600f5',{'f':'pjson'})
