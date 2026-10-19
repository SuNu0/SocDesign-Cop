"""Strict, read-only loading of A's twelve-layer integer handoff bundle.

Only Python's standard library is used. No code from the external data bundle
is imported or executed. Returned tensor lists contain unsigned raw encodings.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import struct


class VectorDataError(ValueError):
    """The external bundle is incomplete, inconsistent, unsafe or changed."""


_SHAPES={'x':[99,64],'w':[64,256],'b':[256],'y':[99,256]}
_BITS={'x':16,'w':16,'b':40,'y':16}
_DTYPES={'x':'<i2','w':'<i2','b':'<i8','y':'<i2'}
_CONTAINERS={'x':'h','w':'h','b':'q','y':'h'}


def _require(condition,message):
    if not condition:
        raise VectorDataError(message)


def _same_json(left,right):
    return json.dumps(left,sort_keys=True,allow_nan=False)==json.dumps(right,sort_keys=True,allow_nan=False)


def _json_object(pairs):
    result={}
    for key,value in pairs:
        _require(key not in result,f'Duplicate JSON key: {key}')
        result[key]=value
    return result


def _invalid_json_constant(value):
    raise VectorDataError(f'Non-finite JSON number is not allowed: {value}')


class _SnapshotReader:
    def __init__(self,root):
        try:
            self.root=Path(root).resolve(strict=True)
        except OSError as exc:
            raise VectorDataError(f'Data root does not exist: {root}') from exc
        _require(self.root.is_dir(),f'Data root is not a directory: {self.root}')
        self.fingerprints={}
        self.expected_sizes={}

    def _path(self,relative):
        _require(isinstance(relative,str) and bool(relative),'Input filename must be a nonempty string')
        _require(not PureWindowsPath(relative).drive and not relative.startswith(('/', '\\')),
                 f'Input path must stay inside data_root: {relative}')
        parts=re.split(r'[/\\]',relative)
        _require(all(part not in ('','.', '..') for part in parts),
                 f'Input path traversal outside data_root is forbidden: {relative}')
        _require(all(':' not in part for part in parts),f'Input drive/stream path is forbidden: {relative}')
        key='/'.join(parts)
        try:
            path=self.root.joinpath(*parts).resolve(strict=True)
        except (OSError,RuntimeError) as exc:
            raise VectorDataError(f'Missing or invalid input file: {relative}') from exc
        _require(path.is_relative_to(self.root),f'Input path escapes data_root: {relative}')
        _require(path.is_file(),f'Input is not a regular file: {relative}')
        return key,path

    @staticmethod
    def _read_content(path,expected_size,label):
        if expected_size is None:
            return path.read_bytes()
        _require(type(expected_size) is int and expected_size>=0,'Expected input size must be a nonnegative integer')
        actual_size=path.stat().st_size
        _require(actual_size==expected_size,
                 f'{label}: binary byte count mismatch: expected {expected_size}, found {actual_size}')
        # The file can change after stat. Read at most one extra byte so growth
        # is rejected without allowing an arbitrarily large allocation.
        with path.open('rb') as source:
            data=source.read(expected_size+1)
        found=f'at least {len(data)}' if len(data)>expected_size else str(len(data))
        _require(len(data)==expected_size,
                 f'{label}: binary byte count mismatch during read: expected {expected_size}, found {found}')
        return data

    def read(self,relative,used,expected_size=None,context=None):
        key,path=self._path(relative)
        label=context or key
        try:
            data=self._read_content(path,expected_size,label)
        except OSError as exc:
            raise VectorDataError(f'Cannot read input {label}: {relative}') from exc
        digest=hashlib.sha256(data).hexdigest()
        previous=self.fingerprints.get(key)
        _require(previous is None or previous==digest,f'Input changed while loading: {key}')
        self.fingerprints[key]=digest
        if expected_size is not None:
            self.expected_sizes[key]=(expected_size,label)
        used.add(key)
        return data

    def json(self,relative,used):
        try:
            value=json.loads(self.read(relative,used).decode('utf-8'),
                             object_pairs_hook=_json_object,parse_constant=_invalid_json_constant)
        except (UnicodeError,json.JSONDecodeError) as exc:
            raise VectorDataError(f'Invalid JSON file {relative}: {exc}') from exc
        _require(isinstance(value,dict),f'{relative}: JSON root must be an object')
        return value

    def verify(self):
        for relative,digest in self.fingerprints.items():
            _,path=self._path(relative)
            expected_size,label=self.expected_sizes.get(relative,(None,relative))
            try:
                current=hashlib.sha256(self._read_content(path,expected_size,label)).hexdigest()
            except OSError as exc:
                raise VectorDataError(f'Cannot recheck input: {relative}') from exc
            _require(current==digest,f'Input changed while loading: {relative}')


def _format_index(formats):
    for key,value in {'input_bits':16,'weight_bits':16,'acc_bits':40,'bias_bits':40,
                      'bias_sum_bits':41,'output_bits':16}.items():
        _require(type(formats.get(key)) is int and formats[key]==value,f'formats.json: {key} must be integer {value}')
    _require(formats.get('rounding')=='nearest_ties_away_from_zero','Unsupported rounding convention')
    entries=formats.get('layers')
    _require(isinstance(entries,list) and len(entries)==12,'formats.json: exactly 12 layer formats are required')
    indexed={}
    for item in entries:
        _require(isinstance(item,dict),'Layer format must be an object')
        for key in ('layer','fx','fw','fy','shift'):
            _require(type(item.get(key)) is int,f'Layer format {key} must be an integer, not bool')
        layer=item['layer']
        _require(0<=layer<12 and layer not in indexed,f'Duplicate or invalid layer format: {layer}')
        _require(0<=item['shift']<=63 and item['shift']==item['fx']+item['fw']-item['fy'],
                 f'Layer {layer}: shift must equal fx+fw-fy and lie in 0..63')
        indexed[layer]=item
    _require(set(indexed)==set(range(12)),'Layer formats must cover 0..11')
    return indexed


def _signed(value,bits):
    return value-(1<<bits) if value&(1<<(bits-1)) else value


def _wrap_signed(value,bits):
    return _signed(value&((1<<bits)-1),bits)


def _hex(reader,relative,bits,count,used):
    try:
        lines=reader.read(relative,used).decode('ascii').splitlines()
    except UnicodeError as exc:
        raise VectorDataError(f'{relative}: hex file must be ASCII') from exc
    _require(len(lines)==count,f'{relative}: expected {count} elements, found {len(lines)}')
    pattern=re.compile(r'[0-9a-fA-F]{'+str((bits+3)//4)+r'}')
    result=[]
    for index,line in enumerate(lines):
        _require(pattern.fullmatch(line) is not None,
                 f'{relative}:{index+1}: expected one {bits}-bit fixed-width hexadecimal word')
        value=int(line,16)
        _require(value<(1<<bits),f'{relative}:{index+1}: value exceeds {bits} bits')
        result.append(value)
    return result


def _load_layer(reader,layer,fmt,formats_paths):
    used=set(formats_paths)
    prefix=f'layer_{layer:02d}'
    manifest=reader.json(f'{prefix}/memory_manifest.json',used)
    _require(type(manifest.get('layer')) is int and manifest['layer']==layer,f'Layer {layer}: manifest identity mismatch')
    _require(manifest.get('row_major') is True,f'Layer {layer}: row-major layout is required')
    _require(manifest.get('endianness')=='little',f'Layer {layer}: little-endian layout is required')
    _require(manifest.get('bias_storage')=='signed40 sign-extended into signed64 container',
             f'Layer {layer}: unsupported bias storage declaration')
    _require(_same_json(manifest.get('numeric_format'),fmt),f'Layer {layer}: manifest numeric_format disagrees with formats.json')
    files=manifest.get('files')
    _require(isinstance(files,dict) and set(files)==set(_SHAPES),f'Layer {layer}: manifest must declare x/w/b/y binaries')
    tensors={}
    for name,shape in _SHAPES.items():
        item=files[name]
        _require(isinstance(item,dict),f'Layer {layer}/{name}: manifest entry must be an object')
        _require(_same_json(item.get('shape'),shape),f'Layer {layer}/{name}: incorrect shape')
        _require(item.get('dtype')==_DTYPES[name],f'Layer {layer}/{name}: unsupported dtype')
        count=1
        for dimension in shape:
            count*=dimension
        expected_bytes=count*struct.calcsize(_CONTAINERS[name])
        _require(type(item.get('bytes')) is int and item['bytes']==expected_bytes,
                 f'Layer {layer}/{name}: incorrect declared byte count')
        filename=item.get('filename')
        _require(isinstance(filename,str) and filename.lower().endswith('.bin'),
                 f'Layer {layer}/{name}: declared binary filename is required')
        # Resolve before reading and reject traversal/symlinks outside data_root.
        binary=reader.read(f'{prefix}/{filename}',used,expected_size=expected_bytes,context=f'Layer {layer}/{name}')
        digest=item.get('sha256')
        _require(isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest) is not None,
                 f'Layer {layer}/{name}: invalid SHA256 declaration')
        _require(hashlib.sha256(binary).hexdigest()==digest,f'Layer {layer}/{name}: binary SHA256 mismatch')
        raw=_hex(reader,f'{prefix}/{name}.hex',_BITS[name],count,used)
        signed_raw=[_signed(value,_BITS[name]) for value in raw]
        decoded=list(struct.unpack('<'+str(count)+_CONTAINERS[name],binary))
        _require(decoded==signed_raw,f'Layer {layer}/{name}: binary differs from hex encoding/sign extension')
        tensors[name]=raw
    task={'layer':layer,'shift':fmt['shift'],'rows':99,'inner':64,'cols':256,
          'x':tensors['x'],'w':tensors['w'],'b':tensors['b'],'expected':tensors['y'],
          'numeric_format':deepcopy(fmt),'source_sha256':{},'_source_paths':used}
    _validate_outputs(task)
    return task


def _validate_outputs(task):
    rows,inner,cols=task['rows'],task['inner'],task['cols']
    x=[_signed(value,16) for value in task['x']]
    w=[_signed(value,16) for value in task['w']]
    b=[_signed(value,40) for value in task['b']]
    columns=[w[col::cols] for col in range(cols)]
    shift=task['shift']
    for row in range(rows):
        xr=x[row*inner:(row+1)*inner]
        for col,wc in enumerate(columns):
            # Every partial sum of 64 signed16 products fits signed40.
            dot40=_wrap_signed(sum(left*right for left,right in zip(xr,wc)),40)
            sum41=_wrap_signed(dot40+b[col],41)
            if shift:
                rounded=(abs(sum41)+(1<<(shift-1)))>>shift
                if sum41<0:
                    rounded=-rounded
            else:
                rounded=sum41
            computed=min(32767,max(-32768,rounded))&0xffff
            expected=task['expected'][row*cols+col]
            _require(computed==expected,
                     f"Layer {task['layer']}, row {row}, col {col}: "
                     f'expected=0x{expected:04x} ({_signed(expected,16)}), '
                     f'computed=0x{computed:04x} ({_signed(computed,16)})')


def load_tasks(data_root:Path,layers:list[int])->list[dict]:
    """Load selected layers, independently verify Y, and fingerprint every input.

    data_root must be A's artifacts/real_12_layers directory. All twelve numeric
    formats are required, while only selected layer directories are accessed.
    Input files are reread after preparation to detect concurrent modification.
    """
    _require(isinstance(layers,list) and bool(layers),'layers must be a nonempty list')
    _require(all(type(layer) is int and 0<=layer<12 for layer in layers),'layers must contain integer IDs in 0..11, not bool')
    _require(len(layers)==len(set(layers)),'Duplicate requested layers are not allowed')
    reader=_SnapshotReader(data_root)
    formats_paths=set()
    formats=_format_index(reader.json('formats.json',formats_paths))
    tasks=[_load_layer(reader,layer,formats[layer],formats_paths) for layer in layers]
    reader.verify()
    for task in tasks:
        task['source_sha256']={name:reader.fingerprints[name] for name in sorted(task.pop('_source_paths'))}
    return tasks


def _indices(indices,limit,label):
    _require(isinstance(indices,list) and bool(indices),f'{label} must be a nonempty list')
    _require(all(type(value) is int and 0<=value<limit for value in indices),f'{label} contains an invalid index or bool')
    _require(len(indices)==len(set(indices)),f'{label} contains duplicate indices')


def crop_task(task:dict,row_indices:list[int],col_indices:list[int])->dict:
    """Select rows/channels while retaining W[k,j] orientation and all 64 k's."""
    _require(isinstance(task,dict),'task must be an object')
    for key in ('rows','inner','cols'):
        _require(type(task.get(key)) is int and task[key]>0,f'task {key} must be a positive integer')
    rows,inner,cols=task['rows'],task['inner'],task['cols']
    _indices(row_indices,rows,'row_indices')
    _indices(col_indices,cols,'col_indices')
    for name,length,bits in [('x',rows*inner,16),('w',inner*cols,16),('b',cols,40),('expected',rows*cols,16)]:
        values=task.get(name)
        _require(isinstance(values,list) and len(values)==length and
                 all(type(value) is int and 0<=value<(1<<bits) for value in values),f'task {name} has invalid encodings or length')
    _require(type(task.get('layer')) is int and 0<=task['layer']<12,'task layer is invalid')
    _require(type(task.get('shift')) is int and 0<=task['shift']<=63,'task shift is invalid')
    _require(isinstance(task.get('numeric_format'),dict) and isinstance(task.get('source_sha256'),dict),
             'task numeric_format/source_sha256 is missing')
    selected=task.get('selection',{'rows':list(range(rows)),'cols':list(range(cols))})
    _require(isinstance(selected,dict) and isinstance(selected.get('rows'),list) and len(selected['rows'])==rows and
             isinstance(selected.get('cols'),list) and len(selected['cols'])==cols,'task selection provenance is invalid')
    return {'layer':task['layer'],'shift':task['shift'],'rows':len(row_indices),'inner':inner,'cols':len(col_indices),
            'x':[task['x'][row*inner+k] for row in row_indices for k in range(inner)],
            'w':[task['w'][k*cols+col] for k in range(inner) for col in col_indices],
            'b':[task['b'][col] for col in col_indices],
            'expected':[task['expected'][row*cols+col] for row in row_indices for col in col_indices],
            'numeric_format':deepcopy(task['numeric_format']),'source_sha256':dict(task['source_sha256']),
            'selection':{'rows':[selected['rows'][row] for row in row_indices],
                         'cols':[selected['cols'][col] for col in col_indices]}}
