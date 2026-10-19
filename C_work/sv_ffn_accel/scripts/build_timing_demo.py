"""Capture actual RTL edge snapshots and pack them for the offline HTML timing lab."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'model'))
from reference import save_case


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-only',action='store_true')
    parser.add_argument('--pack-only',action='store_true',help='Reuse already verified captured JSON')
    args=parser.parse_args()
    work=ROOT/'build/timing';work.mkdir(parents=True,exist_ok=True)
    if args.pack_only:
        data=json.loads((work/'timing_data.json').read_text(encoding='utf-8'))
        for filename,digest in data['meta']['source_hashes'].items():
            assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()==digest,filename
        pack_html(data)
        return
    rng=np.random.default_rng(20261018)
    x=rng.integers(-768,769,(99,64),dtype=np.int16)
    w=rng.integers(-32,33,(64,256),dtype=np.int16)
    b=rng.integers(-128,129,256,dtype=np.int16)
    x[0,0]=-512;w[0,0]=64;b[0]=128
    save_case(work,3,x,w,b,'synthetic_timing_example')
    sources=[ROOT/'rtl/ffn_numeric_pkg.sv',ROOT/'rtl/ffn_sram_1rw.sv',ROOT/'rtl/ffn_accel.sv',ROOT/'tb/tb_timing_capture.sv']
    binary=work/'timing.vvp'
    result=subprocess.run([shutil.which('iverilog') or 'iverilog','-g2012','-s','tb_timing_capture','-o',str(binary),*map(str,sources)],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    result=subprocess.run([shutil.which('vvp') or 'vvp',str(binary),f'+FOLDER={work.as_posix()}'],capture_output=True,text=True)
    print(result.stdout+result.stderr,flush=True)
    if result.returncode or 'TIMING TRACE PASS' not in result.stdout:raise RuntimeError('Trace simulation failed')
    groups=[[] for _ in range(7)]
    for line in (work/'trace.jsonl').read_text().splitlines():
        entry=json.loads(line)
        for phase in ['pre','post']:
            entry[phase]={k:(int(v) if v.lstrip('-').isdigit() else None) for k,v in entry[phase].items()}
        groups[entry['scenario']].append(entry)
    core=groups[3]
    start=next(f for f in core if f['pre']['cmd_valid']==1 and f['pre']['cmd_ready']==1 and f['pre']['cmd_addr']==0)
    core=[f for f in core if f['edge']>=start['edge'] and f['post']['cycles']<=100]
    # C0 accepts START; C1..100 are the first group. Retain the C100 transition.
    core=[f for f in core if f['edge']<=start['edge']+100]
    groups[3]=core
    assert len(core)==101,len(core)
    assert all(b['time_ps']-a['time_ps']==6666 for a,b in zip(core,core[1:]))
    assert core[1]['pre']['b_en']==1 and core[1]['pre']['b_addr']==0
    assert core[2]['post']['acc0']==128*256
    assert core[17]['post']['state']==2
    assert core[18]['post']['x_rdata']==-512
    assert core[19]['post']['product0']==-32768
    assert core[20]['post']['acc0']==0
    assert core[83]['post']['state']==3
    assert core[84]['post']['state']==4
    assert core[85]['pre']['y_we']==1 and core[85]['pre']['y_addr']==0
    assert core[100]['post']['state']==1 and core[100]['post']['group']==1 and core[100]['post']['done']==0
    assert any(f['post']['done']==1 and f['post']['cycles']==158400 for f in groups[4])
    assert any(f['post']['rsp_err']==1 for f in groups[5])
    data={'meta':{'source':'Icarus Verilog, unchanged ffn_accel.sv, pre-edge and +1ps post-NBA snapshots',
                 'clock_period_ps':6666,'nominal_clock_hz':150000000,
                 'full_shape':{'X':[99,64],'W':[64,256],'Y':[99,256]},
                 'synthetic':True,'core_cycles':158400,'first_group_cycles':100,
                 'rtl_sha256':hashlib.sha256((ROOT/'rtl/ffn_accel.sv').read_bytes()).hexdigest(),
                 'source_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}},
          'scenarios':groups}
    (work/'timing_data.json').write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print('Validated captured frames:',[len(g) for g in groups],flush=True)
    if not args.capture_only:
        pack_html(data)


def pack_html(data):
    template=ROOT/'docs/timing_template.html'
    target=ROOT.parent/'output/前馈加速器_真实RTL时序动画.html'
    html=template.read_text(encoding='utf-8').replace('__TIMING_DATA__',json.dumps(data,separators=(',',':')))
    target.write_text(html,encoding='utf-8')
    (target.parent/'timing_fixed.html').write_text(html,encoding='utf-8')
    print('HTML:',target,flush=True)


if __name__=='__main__':main()
