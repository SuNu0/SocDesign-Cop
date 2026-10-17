"""Create an explicit PROPOSED memory ABI for B/C, with byte-exact round trip."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--real',type=Path,required=True)
    a=p.parse_args()
    config=json.loads((a.real/'formats.json').read_text())['layers']
    for l in range(12):
        folder=a.real/('layer_%02d'%l)
        data=np.load(folder/'encoded_sample.npz')
        files={}
        for name,dtype in [('x','<i2'),('w','<i2'),('b','<i8'),('y','<i2')]:
            values=data[name]
            encoded=np.asarray(values,dtype=dtype).tobytes(order='C')
            target=folder/(name+'.bin')
            target.write_bytes(encoded)
            decoded=np.frombuffer(encoded,dtype=dtype).reshape(values.shape)
            np.testing.assert_array_equal(decoded,values)
            files[name]={'filename':target.name,'dtype':dtype,'shape':list(values.shape),
                'bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()}
        manifest={'status':'PROPOSED_ABI_REQUIRES_B_C_REVIEW','layer':l,'row_major':True,
            'endianness':'little','bias_storage':'signed40 sign-extended into signed64 container',
            'address_bases':'not assigned; C must use actual platform memory map',
            'files':files,'numeric_format':config[l]}
        (folder/'memory_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('A_PACKING_ROUNDTRIP_PASSED layers=12')

if __name__=='__main__':main()
