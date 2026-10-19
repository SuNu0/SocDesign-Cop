"""Independent external-vector loader tests; fixtures never modify A's bundle.

Run: python -B -m unittest discover -s tb -p test_a_vectors.py
Set A_VECTORS_TEST_DATA to artifacts/real_12_layers to include its full audit.
Set A_VECTORS_TEST_LAYERS to comma-separated IDs to audit only selected layers.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import a_vectors


def _save_json(path,value):
    path.write_text(json.dumps(value,indent=2),encoding='utf-8')


def _json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _signed(raw,bits):
    return raw-(1<<bits) if raw>=(1<<(bits-1)) else raw


def _write_tensor(folder,name,values):
    bits=40 if name=='b' else 16
    digits=10 if name=='b' else 4
    values=[value&((1<<bits)-1) for value in values]
    (folder/(name+'.hex')).write_text(''.join(f'{value:0{digits}x}\n' for value in values),encoding='ascii')
    code='q' if name=='b' else 'h'
    binary=struct.pack('<'+str(len(values))+code,*[_signed(value,bits) for value in values])
    (folder/(name+'.bin')).write_bytes(binary)
    manifest_path=folder/'memory_manifest.json'
    if manifest_path.is_file():
        manifest=_json(manifest_path)
        manifest['files'][name]['sha256']=hashlib.sha256(binary).hexdigest()
        _save_json(manifest_path,manifest)


def _make_fixture(root):
    formats={'input_bits':16,'weight_bits':16,'acc_bits':40,'bias_bits':40,
             'bias_sum_bits':41,'output_bits':16,'rounding':'nearest_ties_away_from_zero',
             'layers':[{'layer':layer,'fx':12 if layer==2 else 3,'fw':16 if layer==2 else 4,
                        'fy':11 if layer==2 else 6,'shift':17 if layer==2 else 1} for layer in range(12)]}
    _save_json(root/'formats.json',formats)
    x=[(row+k)%19-9 for row in range(99) for k in range(64)]
    w=[(k*7+col*5)%101-50 for k in range(64) for col in range(256)]
    b=[col-128 for col in range(256)]
    for layer in (0,2):
        folder=root/f'layer_{layer:02d}'
        folder.mkdir()
        fmt=formats['layers'][layer]
        shift=fmt['shift']
        y=[]
        for row in range(99):
            for col in range(256):
                value=sum(x[row*64+k]*w[k*256+col] for k in range(64))+b[col]
                half=1<<(shift-1)
                rounded=(value+half)//(1<<shift) if value>=0 else -((-value+half)//(1<<shift))
                y.append(min(32767,max(-32768,rounded)))
        for name,values in [('x',x),('w',w),('b',b),('y',y)]:
            _write_tensor(folder,name,values)
        files={}
        for name,shape in {'x':[99,64],'w':[64,256],'b':[256],'y':[99,256]}.items():
            binary=(folder/(name+'.bin')).read_bytes()
            files[name]={'filename':name+'.bin','dtype':'<i8' if name=='b' else '<i2',
                         'shape':shape,'bytes':len(binary),'sha256':hashlib.sha256(binary).hexdigest()}
        manifest={'status':'UNIT_TEST_FIXTURE','layer':layer,'row_major':True,'endianness':'little',
                  'bias_storage':'signed40 sign-extended into signed64 container',
                  'files':files,'numeric_format':fmt}
        _save_json(folder/'memory_manifest.json',manifest)


class AVectorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp=tempfile.TemporaryDirectory(prefix='b_a_vectors_fixture_')
        cls.fixture_root=Path(cls.fixture_temp.name).resolve()
        assert cls.fixture_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        _make_fixture(cls.fixture_root)

    @classmethod
    def tearDownClass(cls):
        assert cls.fixture_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        cls.fixture_temp.cleanup()

    def setUp(self):
        self.case_temp=tempfile.TemporaryDirectory(prefix='b_a_vectors_case_')
        self.root=Path(self.case_temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        shutil.copytree(self.fixture_root,self.root,dirs_exist_ok=True)
        self.folder=self.root/'layer_00'

    def tearDown(self):
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.case_temp.cleanup()

    def load(self):
        return a_vectors.load_tasks(self.root,[0])

    def test_valid_raw_encodings_shift_and_complete_fingerprints(self):
        tasks=a_vectors.load_tasks(self.root,[0,2])
        self.assertEqual([task['layer'] for task in tasks],[0,2])
        self.assertEqual(tasks[1]['shift'],17)
        self.assertEqual((tasks[0]['rows'],tasks[0]['inner'],tasks[0]['cols']),(99,64,256))
        self.assertEqual([len(tasks[0][key]) for key in ('x','w','b','expected')],[6336,16384,256,25344])
        self.assertTrue(any(value>=0x8000 for value in tasks[0]['x']))
        self.assertGreaterEqual(tasks[0]['b'][0],1<<39)
        for task in tasks:
            prefix=f"layer_{task['layer']:02d}"
            expected={'formats.json',prefix+'/memory_manifest.json'}|{
                f'{prefix}/{tensor}.{suffix}' for tensor in ('x','w','b','y') for suffix in ('hex','bin')}
            self.assertEqual(set(task['source_sha256']),expected)
            for relative,digest in task['source_sha256'].items():
                self.assertEqual(hashlib.sha256((self.root/relative).read_bytes()).hexdigest(),digest)

    def test_crop_keeps_w_k_by_channel_orientation_and_original_indices(self):
        task=self.load()[0]
        rows=[0,49,98]
        cols=[0,7,93,128,255]
        cropped=a_vectors.crop_task(task,rows,cols)
        self.assertEqual((cropped['rows'],cropped['inner'],cropped['cols']),(3,64,5))
        self.assertEqual(cropped['selection'],{'rows':rows,'cols':cols})
        self.assertEqual(cropped['source_sha256'],task['source_sha256'])
        for k in range(64):
            for j,col in enumerate(cols):
                self.assertEqual(cropped['w'][k*5+j],task['w'][k*256+col])
        for i,row in enumerate(rows):
            self.assertEqual(cropped['x'][i*64:(i+1)*64],task['x'][row*64:(row+1)*64])
            for j,col in enumerate(cols):
                self.assertEqual(cropped['expected'][i*5+j],task['expected'][row*256+col])
        a_vectors._validate_outputs(cropped)
        second=a_vectors.crop_task(cropped,[2,0],[4,1])
        self.assertEqual(second['selection'],{'rows':[98,0],'cols':[255,7]})
        a_vectors._validate_outputs(second)

    def test_modified_y_even_with_matching_binary_and_hash_is_rejected(self):
        values=[int(line,16) for line in (self.folder/'y.hex').read_text().splitlines()]
        values[0]^=1
        _write_tensor(self.folder,'y',values)
        with self.assertRaisesRegex(a_vectors.VectorDataError,r'Layer 0, row 0, col 0: expected=.*computed='):
            self.load()

    def test_missing_hex_element_is_rejected(self):
        path=self.folder/'w.hex'
        lines=path.read_text().splitlines()
        path.write_text('\n'.join(lines[:-1])+'\n',encoding='ascii')
        with self.assertRaisesRegex(a_vectors.VectorDataError,'expected 16384 elements'):
            self.load()

    def test_invalid_encoding_or_width_is_rejected(self):
        path=self.folder/'x.hex'
        original=path.read_text(encoding='ascii')
        for invalid in ('zzzz','10000','-001',' 0000','0000 // comment',''):
            with self.subTest(invalid=invalid):
                path.write_text(invalid+'\n'+original.split('\n',1)[1],encoding='ascii')
                with self.assertRaises(a_vectors.VectorDataError):
                    self.load()

    def test_binary_corruption_without_updated_manifest_is_rejected(self):
        path=self.folder/'x.bin'
        data=bytearray(path.read_bytes())
        data[0]^=1
        path.write_bytes(data)
        with self.assertRaisesRegex(a_vectors.VectorDataError,'SHA256 mismatch'):
            self.load()

    def test_oversized_binary_is_rejected_before_its_contents_are_read(self):
        path=(self.folder/'x.bin').resolve()
        path.write_bytes(b'\0'*(8*1024*1024))
        original_open=Path.open
        original_read_bytes=Path.read_bytes
        def guarded_open(candidate,*args,**kwargs):
            if candidate==path:
                self.fail('Oversized binary was opened before its size was rejected')
            return original_open(candidate,*args,**kwargs)
        def guarded_read_bytes(candidate):
            if candidate==path:
                self.fail('Oversized binary was read in full')
            return original_read_bytes(candidate)
        with patch.object(Path,'open',guarded_open),patch.object(Path,'read_bytes',guarded_read_bytes):
            with self.assertRaisesRegex(a_vectors.VectorDataError,
                                        'Layer 0/x: binary byte count mismatch: expected 12672, found 8388608'):
                self.load()

    def test_binary_growth_or_shrink_after_stat_is_rejected_with_a_bounded_read(self):
        path=(self.folder/'x.bin').resolve()
        original_data=path.read_bytes()
        original_open=Path.open
        expected_size=len(original_data)
        for simulated_data,found in [(original_data+b'\0'*1024,'at least 12673'),
                                     (original_data[:-1],'12671')]:
            with self.subTest(simulated_bytes=len(simulated_data)):
                read_sizes=[]
                class TrackingFile(io.BytesIO):
                    def read(self,size=-1):
                        read_sizes.append(size)
                        return super().read(size)
                def changing_open(candidate,*args,**kwargs):
                    if candidate==path:
                        self.assertEqual(args,('rb',))
                        return TrackingFile(simulated_data)
                    return original_open(candidate,*args,**kwargs)
                with patch.object(Path,'open',changing_open):
                    with self.assertRaisesRegex(a_vectors.VectorDataError,
                                                'Layer 0/x: binary byte count mismatch during read: expected 12672, found '+found):
                        self.load()
                self.assertEqual(read_sizes,[expected_size+1])

    def test_final_input_recheck_rejects_grown_binary_before_reading_it(self):
        path=(self.folder/'x.bin').resolve()
        original_validate=a_vectors._validate_outputs
        original_open=Path.open
        changed=False
        def change_after_validate(task):
            nonlocal changed
            original_validate(task)
            with original_open(path,'ab') as destination:
                destination.write(b'\0'*1024)
            changed=True
        def guarded_open(candidate,*args,**kwargs):
            if candidate==path and changed:
                self.fail('Final fingerprint recheck read a grown binary before rejecting its size')
            return original_open(candidate,*args,**kwargs)
        with patch.object(a_vectors,'_validate_outputs',side_effect=change_after_validate),patch.object(Path,'open',guarded_open):
            with self.assertRaisesRegex(a_vectors.VectorDataError,
                                        'Layer 0/x: binary byte count mismatch: expected 12672, found 13696'):
                self.load()

    def test_binary_corruption_with_updated_hash_is_still_rejected(self):
        path=self.folder/'x.bin'
        data=bytearray(path.read_bytes())
        data[0]^=1
        path.write_bytes(data)
        manifest=_json(self.folder/'memory_manifest.json')
        manifest['files']['x']['sha256']=hashlib.sha256(data).hexdigest()
        _save_json(self.folder/'memory_manifest.json',manifest)
        with self.assertRaisesRegex(a_vectors.VectorDataError,'binary differs from hex'):
            self.load()

    def test_wrong_manifest_hash_is_rejected(self):
        manifest=_json(self.folder/'memory_manifest.json')
        manifest['files']['b']['sha256']='0'*64
        _save_json(self.folder/'memory_manifest.json',manifest)
        with self.assertRaisesRegex(a_vectors.VectorDataError,'SHA256 mismatch'):
            self.load()

    def test_missing_declared_binary_is_rejected(self):
        (self.folder/'b.bin').unlink()
        with self.assertRaisesRegex(a_vectors.VectorDataError,'Missing or invalid input file'):
            self.load()

    def test_bias_must_be_sign_extended_in_signed64_container(self):
        path=self.folder/'b.bin'
        data=bytearray(path.read_bytes())
        data[:8]=struct.pack('<q',(1<<40)-128)
        path.write_bytes(data)
        manifest=_json(self.folder/'memory_manifest.json')
        manifest['files']['b']['sha256']=hashlib.sha256(data).hexdigest()
        _save_json(self.folder/'memory_manifest.json',manifest)
        with self.assertRaisesRegex(a_vectors.VectorDataError,'binary differs from hex encoding/sign extension'):
            self.load()

    def test_manifest_path_escape_is_rejected(self):
        path=self.folder/'memory_manifest.json'
        manifest=_json(path)
        for filename in ('../../outside.bin','C:\\outside.bin','/outside.bin','..\\..\\outside.bin'):
            with self.subTest(filename=filename):
                manifest['files']['x']['filename']=filename
                _save_json(path,manifest)
                with self.assertRaises(a_vectors.VectorDataError):
                    self.load()

    def test_w_transposed_storage_is_detected_by_independent_y_check(self):
        values=[int(line,16) for line in (self.folder/'w.hex').read_text().splitlines()]
        transposed=[values[k*256+col] for col in range(256) for k in range(64)]
        self.assertNotEqual(values,transposed)
        _write_tensor(self.folder,'w',transposed)
        with self.assertRaisesRegex(a_vectors.VectorDataError,'expected=.*computed='):
            self.load()

    def test_duplicate_or_bool_layer_configuration_is_rejected(self):
        path=self.root/'formats.json'
        original=_json(path)
        for field,value in [('layer',0),('layer',True),('shift',True),('shift',1.0),('shift',64)]:
            with self.subTest(field=field,value=value):
                formats=deepcopy(original)
                formats['layers'][1][field]=value
                _save_json(path,formats)
                with self.assertRaises(a_vectors.VectorDataError):
                    self.load()

    def test_manifest_schema_and_format_mismatch_are_rejected(self):
        path=self.folder/'memory_manifest.json'
        original=_json(path)
        for change in ('shape_bool','bytes_float','layer_bool','shift','row_major'):
            with self.subTest(change=change):
                manifest=deepcopy(original)
                if change=='shape_bool':manifest['files']['x']['shape']=[True,64]
                elif change=='bytes_float':manifest['files']['x']['bytes']=12672.0
                elif change=='layer_bool':manifest['layer']=False
                elif change=='shift':manifest['numeric_format']['shift']=2
                else:manifest['row_major']=1
                _save_json(path,manifest)
                with self.assertRaises(a_vectors.VectorDataError):
                    self.load()

    def test_duplicate_json_key_is_rejected(self):
        path=self.root/'formats.json'
        text=path.read_text(encoding='utf-8')
        path.write_text(text.replace('{','{"input_bits": 16,',1),encoding='utf-8')
        with self.assertRaisesRegex(a_vectors.VectorDataError,'Duplicate JSON key'):
            self.load()

    def test_inputs_changed_during_preparation_are_rejected(self):
        original=a_vectors._validate_outputs
        def mutate_after_check(task):
            original(task)
            path=self.root/'formats.json'
            path.write_bytes(path.read_bytes()+b'\n')
        with patch.object(a_vectors,'_validate_outputs',side_effect=mutate_after_check):
            with self.assertRaisesRegex(a_vectors.VectorDataError,'Input changed while loading: formats.json'):
                self.load()

    def test_requested_layers_and_crop_indices_reject_bool_duplicates_and_empty(self):
        for layers in ([],[True],[0,0],[12],[-1],(0,)):
            with self.subTest(layers=layers):
                with self.assertRaises(a_vectors.VectorDataError):
                    a_vectors.load_tasks(self.root,layers)
        task=self.load()[0]
        for rows,cols in [([], [0]),([True],[0]),([0,0],[0]),([99],[0]),([0],[256]),([0],[False])]:
            with self.subTest(rows=rows,cols=cols):
                with self.assertRaises(a_vectors.VectorDataError):
                    a_vectors.crop_task(task,rows,cols)


class RealABundleTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('A_VECTORS_TEST_DATA'),'A_VECTORS_TEST_DATA is not configured')
    def test_selected_real_layers_match_declared_formats(self):
        root=Path(os.environ['A_VECTORS_TEST_DATA'])
        requested=os.environ.get('A_VECTORS_TEST_LAYERS',','.join(str(layer) for layer in range(12)))
        layers=[int(value.strip()) for value in requested.split(',')]
        tasks=a_vectors.load_tasks(root,layers)
        declared={item['layer']:item for item in _json(root/'formats.json')['layers']}
        self.assertEqual([task['layer'] for task in tasks],layers)
        self.assertEqual(sum(len(task['expected']) for task in tasks),len(layers)*25344)
        for task in tasks:
            self.assertEqual(task['shift'],declared[task['layer']]['shift'])
            self.assertEqual(len(task['source_sha256']),10)
        cropped=a_vectors.crop_task(tasks[0],[0,49,98],[0,7,93,128,255])
        self.assertEqual((cropped['rows'],cropped['inner'],cropped['cols']),(3,64,5))
        a_vectors._validate_outputs(cropped)


if __name__=='__main__':
    unittest.main()
