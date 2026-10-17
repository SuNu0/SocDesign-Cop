"""Run official KWT-1, calibrate on TRAINING only, evaluate VALIDATION only.

Uses unmodified upstream AudioProcessor, SpeechFeatures and network classes.
This intentionally uses TF graph mode because the original loader requires it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
os.environ.setdefault('CUDA_VISIBLE_DEVICES','-1')
import numpy as np
from numeric import encode, choose_frac, linear, nrmse, write_hex

COMMIT = '237e4097afd4f6851e0b82f0a8d65c2dfe8eae30'

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):
            h.update(block)
    return h.hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False),encoding='utf-8')

def balanced(samples, word_to_index, per_class):
    if per_class == 0:
        return list(samples)
    count = [0]*12
    chosen=[]
    for item in samples:
        label=word_to_index[item['label']]
        if count[label] < per_class:
            chosen.append(item)
            count[label]+=1
    if min(count) != per_class:
        raise ValueError('Insufficient samples per class: %s'%count)
    return chosen

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--upstream',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--calibration-per-class',type=int,default=16)
    p.add_argument('--validation-per-class',type=int,default=10,help='0 = complete validation split')
    p.add_argument('--batch-size',type=int,default=16)
    a=p.parse_args()
    upstream=a.upstream.resolve()
    actual=subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    if actual != COMMIT:
        raise ValueError('Wrong upstream revision: '+actual)
    if subprocess.check_output(['git','-C',str(upstream),'status','--porcelain','--untracked-files=no'],text=True).strip():
        raise ValueError('Upstream checkout must be unmodified')
    if a.out.exists():
        raise FileExistsError('Use a NEW output directory; never mix frozen configurations')
    a.out.mkdir(parents=True)
    sys.path.insert(0,str(upstream))
    import tensorflow as tf
    # Importing the original loader switches off eager execution.
    from kws_streaming.data import input_data
    # Match upstream entry-point import order (registry before kws_transformer).
    from kws_streaming.models import models as model_registry
    from kws_streaming.models import kws_transformer
    from kws_streaming.models.transformer_utils import KWSTransformer
    tf.random.set_seed(59185)
    np.random.seed(59185)
    model_dir=upstream/'models_data_v2_12_labels'/'kwt1'
    flags=json.loads((model_dir/'flags.json').read_text())
    flags.update(data_dir=str(a.dataset.resolve()), data_url='',batch_size=None,
        training=False,train=0,distill_teacher_json='',approximate_gelu=False,prenorm=False,
        use_spec_augment=0,use_spec_cutout=0,time_shift_ms=0.,sp_time_shift_ms=0.,
        resample=0.,sp_resample=0.,volume_resample=0.,pick_deterministically=1)
    flags=SimpleNamespace(**flags)
    config=tf.compat.v1.ConfigProto(intra_op_parallelism_threads=4,inter_op_parallelism_threads=2)
    with tf.compat.v1.Session(config=config) as sess:
        tf.compat.v1.keras.backend.set_session(sess)
        processor=input_data.AudioProcessor(flags)
        labels=(model_dir/'labels.txt').read_text().splitlines()
        if labels != processor.words_list:
            raise ValueError('labels.txt mapping differs from upstream processor')
        model=kws_transformer.model(flags)
        status=model.load_weights(str(model_dir/'best_weights'))
        status.assert_existing_objects_matched()
        status.expect_partial()  # optimizer slots in published training checkpoint
        trans=next(layer for layer in model.layers if isinstance(layer,KWSTransformer))
        assert len(trans.enc_layers)==12 and trans.d_model==64
        features=model.layers[1].output
        x=trans.patch_proj(features)
        token=tf.broadcast_to(trans.class_emb,[tf.shape(x)[0],1,64])
        x=tf.concat([token,x],axis=1)+trans.pos_emb
        xs=[]; refs=[]
        for block in trans.enc_layers:
            att,_=block.att(x)
            z=block.layernorm1(x+block.dropout1(att,training=False))
            first=block.ffn.layers[0]
            assert first.kernel.shape.as_list()==[64,256]
            xs.append(z)
            refs.append(first(z))
            x,_=block(x,training=False)
        manual_logits=model.layers[-1](x[:,0])
        # load_weights installs restore ops; Keras session initializes/restores pending variables.
        tf.compat.v1.keras.backend.get_session()
        # TF 2.4 emits trackable alias warnings for this published checkpoint's
        # weightless GELU layer. Independently audit EVERY loaded model weight.
        from tensorflow.core.protobuf import trackable_object_graph_pb2
        reader=tf.train.load_checkpoint(str(model_dir/'best_weights'))
        object_graph=trackable_object_graph_pb2.TrackableObjectGraph()
        object_graph.ParseFromString(reader.get_tensor('_CHECKPOINTABLE_OBJECT_GRAPH'))
        checkpoint_names={attr.full_name:attr.checkpoint_key for node in object_graph.nodes
            for attr in node.attributes if '.OPTIMIZER_SLOT/' not in attr.checkpoint_key}
        weight_audit=[]
        for variable in model.weights:
            name=variable.name.rsplit(':',1)[0]
            if name not in checkpoint_names:
                raise ValueError('Model weight absent from checkpoint: '+name)
            actual_weight=sess.run(variable)
            expected_weight=reader.get_tensor(checkpoint_names[name])
            if not np.array_equal(actual_weight,expected_weight):
                raise ValueError('Loaded tensor differs from checkpoint: '+name)
            weight_audit.append({'name':name,'shape':list(actual_weight.shape),
                'checkpoint_key':checkpoint_names[name],'exact_equal':True})
        dump(a.out/'checkpoint_audit.json',weight_audit)
        print('CHECKPOINT_ALL_MODEL_WEIGHTS_EXACT count=%d'%len(weight_audit),flush=True)
        weights=[sess.run([block.ffn.layers[0].kernel,block.ffn.layers[0].bias]) for block in trans.enc_layers]
        cal=balanced(processor.data_index['training'],processor.word_to_index,a.calibration_per_class)
        val=balanced(processor.data_index['validation'],processor.word_to_index,a.validation_per_class)
        manifests={}
        for name,items in [('training',cal),('validation',val)]:
            manifests[name]=[{'id':i,'label':s['label'],'class_index':processor.word_to_index[s['label']],
                'path':Path(s['file']).relative_to(a.dataset.resolve()).as_posix(),
                'sha256':sha(s['file'])} for i,s in enumerate(items)]
        dump(a.out/'samples.json',manifests)
        max_x=np.zeros(12); max_y=np.zeros(12)
        checksum={'commit':COMMIT,'tensorflow':tf.__version__,'numpy':np.__version__,
            'files':{p.name:sha(p) for p in model_dir.glob('best_weights*')},
            'labels_sha256':sha(model_dir/'labels.txt'),'flags_sha256':sha(model_dir/'flags.json'),
            'original_requested_tensorflow':'2.4.0rc1','runtime_deviation':'2.4.0 final used; exact rc1 reference parity not claimed'}
        dump(a.out/'provenance.json',checksum)
        parity_max=0.
        for phase,items in [('training',cal),('validation',val)]:
            processor.data_index[phase]=items
            sums=np.zeros((12,2),dtype=np.float64)
            worst=np.zeros(12); clipped=np.zeros((12,2),dtype=np.int64)
            correct=0
            for start in range(0,len(items),a.batch_size):
                count=min(a.batch_size,len(items)-start)
                audio,truth=processor.get_data(count,start,flags,0.,0.,0,phase,0.,0.,sess)
                values=sess.run(xs+refs+[model.outputs[0],manual_logits],feed_dict={model.input:audio})
                xx,yy=values[:12],values[12:24]
                logits,manual=values[-2:]
                parity_max=max(parity_max,float(np.max(np.abs(logits-manual))))
                if not np.all(np.isfinite(logits)) or parity_max>1e-5:
                    raise ValueError('Instrumented inference differs from original model')
                correct+=int(np.sum(np.argmax(logits,axis=-1)==truth))
                for l,(xv,yv,(w,b)) in enumerate(zip(xx,yy,weights)):
                    assert xv.shape==(count,99,64) and yv.shape==(count,99,256)
                    # Verify orientation and TF-vs-NumPy floating reference.
                    if not np.allclose(xv@w+b,yv,rtol=2e-5,atol=3e-5):
                        raise ValueError('Dense float orientation/reference mismatch')
                    if phase=='training':
                        max_x[l]=max(max_x[l],float(np.max(np.abs(xv))))
                        max_y[l]=max(max_y[l],float(np.max(np.abs(yv))))
                    else:
                        cfg=formats[l]; fx,fw,fy=cfg['fx'],cfg['fw'],cfg['fy']
                        xq=encode(xv,fx); wq=encode(w,fw); bq=encode(b,fx+fw,40)
                        if np.max(np.abs(b*2.**(fx+fw))) >= 2**39:
                            raise ValueError('Bias needs more than signed40')
                        yq=linear(xq,wq,bq,cfg['shift'])
                        decoded=yq.astype(np.float64)*2.**(-fy)
                        delta=decoded-yv.astype(np.float64)
                        sums[l,0]+=np.sum(delta*delta)
                        sums[l,1]+=np.sum(yv.astype(np.float64)**2)
                        for single,ref in zip(decoded,yv):
                            worst[l]=max(worst[l],nrmse(single,ref))
                        clipped[l,0]+=np.sum(np.abs(xv*2.**fx)>32767)
                        clipped[l,1]+=np.sum((yq==-32768)|(yq==32767))
                        if start==0:
                            dest=a.out/('layer_%02d'%l);dest.mkdir()
                            np.savez_compressed(dest/'float_sample.npz',x=xv[0],w=w,b=b,y=yv[0])
                            np.savez_compressed(dest/'encoded_sample.npz',x=xq[0],w=wq,b=bq,y=yq[0])
                            for name,v,bits in [('x',xq[0],16),('w',wq,16),('b',bq,40),('y',yq[0],16)]:
                                write_hex(dest/(name+'.hex'),v,bits)
                            # MAC input packets are contiguous k=0..63 for selected (row,channel).
                            rows=[0,49,98]
                            cases=[{'row':r,'channel':c} for r in rows for c in range(256)]
                            dump(dest/'selected_dots.json',cases)
                if start%128==0:
                    print('%s %d/%d'%(phase,start+count,len(items)),flush=True)
            if phase=='training':
                formats=[]
                for l,(w,b) in enumerate(weights):
                    fx=choose_frac(max_x[l],1.25);fw=choose_frac(float(np.max(np.abs(w))),1.01)
                    fy=choose_frac(max_y[l],1.5)
                    shift=fx+fw-fy
                    if not 0<=shift<=63:raise ValueError('Unsupported requant shift')
                    formats.append({'layer':l,'fx':fx,'fw':fw,'fy':fy,'shift':shift,
                        'input_absmax_train':max_x[l],'output_absmax_train':max_y[l],
                        'weight_absmax':float(np.max(np.abs(w))), 'bias_absmax':float(np.max(np.abs(b)))})
                dump(a.out/'formats.json',{'calibration_split':'training','samples':len(cal),
                    'input_bits':16,'weight_bits':16,'acc_bits':40,'bias_bits':40,'bias_sum_bits':41,
                    'output_bits':16,'rounding':'nearest_ties_away_from_zero','layers':formats})
            else:
                total_outputs=len(val)*99*256
                errors=np.sqrt(sums[:,0]/total_outputs)/np.maximum(np.sqrt(sums[:,1]/total_outputs),1e-8)
                result={'validation_samples':len(val),'complete_validation':a.validation_per_class==0,
                    'calibration_samples':len(cal),'classification_accuracy_observation':correct/len(val),
                    'instrumentation_logits_max_abs_diff':parity_max,
                    'max_layer_nrmse':float(max(errors)),'threshold':.03,
                    'local_precision_pass':bool(max(errors)<=.03),'official_600_sample_pass':False,
                    'layers':[{'layer':l,'nrmse':float(errors[l]),'worst_task_nrmse':float(worst[l]),
                        'input_clipped_values':int(clipped[l,0]),'output_saturated_values':int(clipped[l,1])} for l in range(12)]}
                dump(a.out/'precision_report.json',result)
                print(json.dumps(result,indent=2),flush=True)
                if max(errors)>.03:raise RuntimeError('LOCAL PRECISION FAIL')
    print('A_REAL_MODEL_EVALUATION_PASSED',flush=True)

if __name__=='__main__':main()
