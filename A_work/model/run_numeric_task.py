"""Run one new FLOAT linear task with an already frozen layer format (no fitting)."""
import argparse
import json
from pathlib import Path
import numpy as np
from numeric import encode, linear, nrmse

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True,help='npz containing x[99,64], w[64,256], b[256]')
    p.add_argument('--formats',type=Path,required=True)
    p.add_argument('--layer',type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not 0<=a.layer<12:raise ValueError('layer must be 0..11')
    if a.out.exists():raise FileExistsError('Output exists; choose a new path')
    cfg=json.loads(a.formats.read_text())['layers'][a.layer]
    data=np.load(a.input)
    x,w,b=data['x'],data['w'],data['b']
    if x.shape!=(99,64) or w.shape!=(64,256) or b.shape!=(256,):raise ValueError('Wrong task shapes')
    fx,fw,fy=cfg['fx'],cfg['fw'],cfg['fy']
    b_scaled=b.astype(np.float64)*2.**(fx+fw)
    if not np.all(np.isfinite(b_scaled)) or np.max(np.abs(b_scaled))>=2**39:
        raise ValueError('Bias cannot be represented in the frozen signed40 format')
    encoded=linear(encode(x,fx),encode(w,fw),encode(b,fx+fw,40),cfg['shift'])
    decoded=encoded.astype(np.float64)*2.**(-fy)
    reference=data['y'] if 'y' in data else x.astype(np.float64)@w.astype(np.float64)+b
    error=nrmse(decoded,reference)
    np.savez_compressed(a.out,encoded=encoded,decoded=decoded,reference=reference)
    print(json.dumps({'layer':a.layer,'nrmse':error,'passes_3_percent':error<=.03}))

if __name__=='__main__':main()
