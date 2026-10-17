import unittest
import numpy as np
from numeric import dot64_scalar, requant, encode, linear

class NumericTests(unittest.TestCase):
    def test_signed_extremes(self):
        self.assertEqual(dot64_scalar([-32768]*64,[-32768]*64),1<<36)
        self.assertEqual(dot64_scalar([-32768]*64,[32767]*64),-68717379584)

    def test_round_ties_and_neighbors(self):
        np.testing.assert_array_equal(requant(np.array([-7,-6,-5,-3,-2,-1,0,1,2,3,5,6,7]),0,2),
            [-2,-2,-1,-1,-1,0,0,0,1,1,1,2,2])

    def test_saturation_and_wide_bias_sum(self):
        self.assertEqual(int(requant((1<<39)-1,(1<<39)-1,0)),32767)
        self.assertEqual(int(requant(-(1<<39),-(1<<39),0)),-32768)
        self.assertEqual(int(requant(-(1<<39),-(1<<39),26)),-16384)
        self.assertEqual(int(requant(-(1<<39),-(1<<39),63)),0)

    def test_encoding(self):
        np.testing.assert_array_equal(encode([.5,-.5,40000,-40000],0),[1,-1,32767,-32768])
        with self.assertRaises(ValueError):encode([np.nan],0)

    def test_matrix_vs_sequential_mac(self):
        rng=np.random.RandomState(42)
        x=rng.randint(-32768,32768,(3,64)).astype(np.int64)
        w=rng.randint(-32768,32768,(64,256)).astype(np.int64)
        b=np.arange(256,dtype=np.int64)-128
        y=linear(x,w,b,21)
        for row in range(3):
            for col in [0,1,127,255]:
                self.assertEqual(y[row,col],int(requant(dot64_scalar(x[row],w[:,col]),b[col],21)))

if __name__=='__main__':unittest.main(verbosity=2)
