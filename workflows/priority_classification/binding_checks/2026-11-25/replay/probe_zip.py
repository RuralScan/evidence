import io,urllib.request,zipfile,json,datetime
from pathlib import Path
import sys
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
url='https://naturebase-shared-docs.s3.amazonaws.com/Data-download/for_afc_total.zip'
with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=35) as response:
 meta={'url':url,'headers':dict(response.headers)}
size=int(meta['headers']['Content-Length'])
(out/'naturebase_afc_headers.json').write_text(json.dumps(meta,indent=2)+'\n')
class RemoteFile(io.RawIOBase):
 def __init__(self):self.pos=0;self.fetched=0
 def seekable(self):return True
 def readable(self):return True
 def tell(self):return self.pos
 def seek(self,n,w=0):
  self.pos=n if w==0 else self.pos+n if w==1 else size+n
  return self.pos
 def read(self,n=-1):
  if n<0:n=size-self.pos
  n=min(n,size-self.pos)
  if n<=0:return b''
  if n>2_000_000 or self.fetched+n>5_000_000:raise ValueError('Bounded metadata read exceeded')
  req=urllib.request.Request(url,headers={'Range':f'bytes={self.pos}-{self.pos+n-1}'})
  with urllib.request.urlopen(req,timeout=35) as r:
   if r.status!=206:raise ValueError('Server ignored Range')
   body=r.read(n+1)
  if len(body)!=n:raise ValueError('Unexpected range size')
  self.pos+=n;self.fetched+=n;return body
remote=RemoteFile()
with zipfile.ZipFile(remote) as z:
 entries=[{'name':i.filename,'bytes':i.file_size,'compressed_bytes':i.compress_size,'crc32':i.CRC,'compression':i.compress_type} for i in z.infolist()]
 print(json.dumps(entries,indent=2),flush=True)
 texts={i.filename:z.read(i).decode(errors='replace') for i in z.infolist() if i.file_size<200000 and i.filename.lower().endswith(('.txt','.md','.json','.prj'))}
 result={'url':url,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive_bytes':size,'bytes_fetched':remote.fetched,'entries':entries,'text_files':texts}
 (out/'naturebase_afc_zip.json').write_text(json.dumps(result,indent=2)+'\n')
 print('bytes_fetched',remote.fetched)
