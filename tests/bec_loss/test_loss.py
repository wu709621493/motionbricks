import unittest
import numpy as np
from motionbricks.bec_dynamics import Parameters
from motionbricks.bec_loss import (
    accuracy_audit, add_one_isotropic, coherent, density_evolve, density_quality,
    distinguish, operator, remove_one, spectrum, study, vector_evolve,
)
from motionbricks.hopfield_reference import hebbian, recall


def pure(v):
    return np.outer(v, v.conj())


class ChannelTests(unittest.TestCase):
    def test_coherent_loss_remains_coherent(self):
        rho = pure(coherent(8, .3, .2))
        for n in range(7, 0, -1):
            rho = remove_one(rho)
            np.testing.assert_allclose(rho, pure(coherent(n, .3, .2)), atol=1e-12)
            density_quality(rho)

    def test_cat_loss_destroys_unobserved_mode_coherence(self):
        v = np.zeros(6, complex)
        v[0] = v[-1] = 1/np.sqrt(2)
        expected = np.zeros((5, 5), complex)
        expected[0, 0] = expected[-1, -1] = .5
        np.testing.assert_allclose(remove_one(pure(v)), expected, atol=1e-14)

    def test_kraus_representation_and_completeness(self):
        rng = np.random.default_rng(4)
        v = rng.normal(size=5)+1j*rng.normal(size=5)
        rho = pure(v/np.linalg.norm(v))
        a0, a1 = np.zeros((4,5)), np.zeros((4,5))
        for i in range(4):
            a0[i,i+1] = np.sqrt(i+1)
            a1[i,i] = np.sqrt(4-i)
        np.testing.assert_allclose((a0.T@a0+a1.T@a1)/4, np.eye(5))
        np.testing.assert_allclose(remove_one(rho), (a0@rho@a0.T+a1@rho@a1.T)/4)
        b0, b1 = np.zeros((6,5)), np.zeros((6,5))
        for i in range(5):
            b0[i+1,i] = np.sqrt(i+1)
            b1[i,i] = np.sqrt(5-i)
        np.testing.assert_allclose((b0.T@b0+b1.T@b1)/6, np.eye(5))
        np.testing.assert_allclose(add_one_isotropic(rho), (b0@rho@b0.T+b1@rho@b1.T)/6)

    def test_addition_is_not_inverse_loss(self):
        original = np.zeros((3,3), complex)
        original[-1,-1] = 1
        replaced = add_one_isotropic(remove_one(original))
        self.assertAlmostEqual(replaced[-1,-1].real, 2/3)
        self.assertAlmostEqual(replaced[1,1].real, 1/3)
        density_quality(replaced)

    def test_trace_distance_contracts_under_channels(self):
        a, b = pure(coherent(6,.4)), pure(coherent(6,-.4))
        before = distinguish(a,b)['quantum_trace_distance']
        a,b = remove_one(a),remove_one(b)
        lost = distinguish(a,b)['quantum_trace_distance']
        self.assertLessEqual(lost, before+1e-12)
        a,b = add_one_isotropic(a),add_one_isotropic(b)
        self.assertLessEqual(distinguish(a,b)['quantum_trace_distance'],lost+1e-12)

    def test_density_evolution_matches_pure_vector(self):
        p=Parameters(duration=.2)
        v=coherent(6,.2)
        eig=spectrum(6,p)
        actual=density_evolve(pure(v),eig,.2)
        np.testing.assert_allclose(actual,pure(vector_evolve(v,eig,.2)),atol=1e-12)
        density_quality(actual)

    def test_invalid_density_and_boundaries(self):
        for rho in (np.eye(2),np.array([[1,2],[0,0]],complex), np.diag([1.1,-.1]),
                    np.full((2,2),np.nan)):
            with self.assertRaises(ValueError): density_quality(rho)
        np.testing.assert_allclose(remove_one(np.diag([.5,.5])),np.ones((1,1)))
        np.testing.assert_allclose(add_one_isotropic(np.ones((1,1))),np.diag([.5,.5]))
        with self.assertRaises(ValueError): remove_one(np.ones((1,1)))
        with self.assertRaises(ValueError): add_one_isotropic(np.zeros((501,501)))

    def test_500_numerical_accuracy(self):
        result=accuracy_audit(Parameters(duration=.1,samples=3))
        self.assertLess(result['max_state_l2_error_vs_spectral'],1e-8)
        self.assertEqual(result['physical_model_error'],'UNQUANTIFIED_WITHOUT_TRAP_OR_EXPERIMENT_DATA')

    def test_end_to_end_loss_study(self):
        result=study(Parameters(duration=.1,samples=3),removed_counts=(0,1))
        rows=result['event_study']
        self.assertAlmostEqual(rows[0]['replace_isotropic']['fidelity_to_no_loss_positive'],1,places=9)
        self.assertEqual(rows[1]['remaining'],499)
        self.assertLessEqual(rows[1]['replace_isotropic']['quantum_trace_distance'],
                             rows[1]['loss']['quantum_trace_distance']+1e-8)
        self.assertEqual(len(result['fresh_preparation_sweep']),4)
        self.assertEqual(result['evidence'],'NUMERICAL_SIMULATION')

    def test_study_request_rejection(self):
        for counts in ((-1,), (500,), (True,), (1,1), ()):
            with self.assertRaises(ValueError): study(removed_counts=counts)
        with self.assertRaises(ValueError): study(event_fraction=float('nan'))


class HopfieldTests(unittest.TestCase):
    def test_recall_energy_descent(self):
        pattern=np.array([1,-1,1,-1,1,-1,1,-1])
        w=hebbian(pattern[None,:])
        cue=pattern.copy(); cue[0]*=-1
        result,energies,converged=recall(w,cue)
        self.assertTrue(converged)
        np.testing.assert_array_equal(result,pattern)
        self.assertTrue(np.all(np.diff(energies)<=1e-10))
        np.testing.assert_array_equal(cue[1:],pattern[1:])
        self.assertNotEqual(cue[0],result[0])

    def test_deleted_nodes_use_original_synapses(self):
        pattern=np.array([1,-1,1,-1,1,-1,1,-1])
        w=hebbian(pattern[None,:])
        idx=np.array([0,1,2,3,4,5])
        cue=pattern[idx].copy(); cue[0]*=-1
        result,_,_=recall(w[np.ix_(idx,idx)],cue)
        np.testing.assert_array_equal(result,pattern[idx])

    def test_invalid_network(self):
        with self.assertRaises(ValueError): hebbian([[0,1]])
        with self.assertRaises(ValueError): recall(np.eye(2),[1,-1])
        with self.assertRaises(ValueError): recall(np.array([[0,1],[0,0]]),[1,-1])


if __name__=='__main__': unittest.main()
