"""Generate independent scalar/Python integer expectations for XSim regression."""
import argparse
import json
from pathlib import Path
import numpy as np
from numeric import dot64_scalar, requant, write_hex

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--real',type=Path)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    rng=np.random.RandomState(20261017)
    cases=[]
    def add(x,w,b=0,s=0,source='synthetic'):
        x=np.asarray(x,dtype=np.int64);w=np.asarray(w,dtype=np.int64)
        acc=dot64_scalar(x,w)
        cases.append((x,w,b,s,acc,int(requant(acc,b,s)),source))
    for x,w in [(0,0),(1,1),(-1,1),(32767,32767),(-32768,-32768),(-32768,32767)]:
        for shift in [0,16,24,63]:add([x]*64,[w]*64,0,shift)
    add([32767,-32768]*32,[32767,32767]*32,123456,8)
    for i in range(200):
        add(rng.randint(-32768,32768,64),rng.randint(-32768,32768,64),
            int(rng.randint(-(1<<38),1<<38,dtype=np.int64)),int(rng.randint(0,64)))
    synthetic=len(cases)
    if a.real:
        config=json.loads((a.real/'formats.json').read_text())['layers']
        for l in range(12):
            d=np.load(a.real/('layer_%02d'%l)/'encoded_sample.npz')
            for row in [0,49,98]:
                for channel in range(256):
                    add(d['x'][row],d['w'][:,channel],int(d['b'][channel]),config[l]['shift'],
                        'real_layer_%02d_row_%d_channel_%d'%(l,row,channel))
                    if cases[-1][5] != int(d['y'][row,channel]):
                        raise AssertionError('Scalar and matrix integer models disagree')
    for name,v,bits in [('x',[c[0] for c in cases],16),('w',[c[1] for c in cases],16),
            ('b',[c[2] for c in cases],40),('shift',[c[3] for c in cases],8),
            ('acc',[c[4] for c in cases],40),('expected',[c[5] for c in cases],16)]:
        write_hex(a.out/(name+'.hex'),v,bits)
    # Independent bias/requant boundary testing, including 41-bit addition.
    bias_cases=[]
    extremes=[-(1<<39),-(1<<39)+1,-32769,-32768,-1,0,1,32767,32768,(1<<39)-1]
    for shift in range(64):
        for acc in extremes:
            for b in [-(1<<39),0,(1<<39)-1]:
                bias_cases.append((acc,b,shift,int(requant(acc,b,shift))))
        if shift<39 and shift>0:
            for k in [-32769,-32768,-2,-1,0,1,2,32767,32768]:
                for delta in [-1,0,1]:
                    v=k*(1<<shift)+(1<<(shift-1))+delta
                    if -(1<<39)<=v<(1<<39):bias_cases.append((v,0,shift,int(requant(v,0,shift))))
    for name,index,bits in [('rq_acc',0,40),('rq_b',1,40),('rq_shift',2,8),('rq_expected',3,16)]:
        write_hex(a.out/(name+'.hex'),[c[index] for c in bias_cases],bits)
    manifest={'seed':20261017,'dot_cases':len(cases),'synthetic_dot_cases':synthetic,
        'real_dot_cases':len(cases)-synthetic,'requant_cases':len(bias_cases),
        'real_directory':str(a.real.resolve()) if a.real else None,
        'real_source_ids':[c[6] for c in cases[synthetic:]],
        'covers':['signed extremes','zero','random signs','shift 0..63','positive/negative ties',
            'saturation','41-bit bias sum','12 layers x 3 rows x 256 output channels' if a.real else 'no real model data']}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('DOT_CASES=%d REQUANT_CASES=%d'%(len(cases),len(bias_cases)))

if __name__=='__main__':main()
