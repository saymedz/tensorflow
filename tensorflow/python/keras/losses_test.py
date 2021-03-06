# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for Keras loss functions."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import shutil

import numpy as np

from tensorflow.python import keras
from tensorflow.python.framework import constant_op
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import test_util
from tensorflow.python.ops import array_ops
from tensorflow.python.ops.losses import losses_impl
from tensorflow.python.platform import test

try:
  import h5py  # pylint:disable=g-import-not-at-top
except ImportError:
  h5py = None

ALL_LOSSES = [keras.losses.mean_squared_error,
              keras.losses.mean_absolute_error,
              keras.losses.mean_absolute_percentage_error,
              keras.losses.mean_squared_logarithmic_error,
              keras.losses.squared_hinge,
              keras.losses.hinge,
              keras.losses.categorical_crossentropy,
              keras.losses.binary_crossentropy,
              keras.losses.kullback_leibler_divergence,
              keras.losses.poisson,
              keras.losses.cosine_proximity,
              keras.losses.logcosh,
              keras.losses.categorical_hinge]


class _MSEMAELoss(object):
  """Loss function with internal state, for testing serialization code."""

  def __init__(self, mse_fraction):
    self.mse_fraction = mse_fraction

  def __call__(self, y_true, y_pred):
    return (self.mse_fraction * keras.losses.mse(y_true, y_pred) +
            (1 - self.mse_fraction) * keras.losses.mae(y_true, y_pred))

  def get_config(self):
    return {'mse_fraction': self.mse_fraction}


class KerasLossesTest(test.TestCase):

  def test_objective_shapes_3d(self):
    with self.cached_session():
      y_a = keras.backend.variable(np.random.random((5, 6, 7)))
      y_b = keras.backend.variable(np.random.random((5, 6, 7)))
      for obj in ALL_LOSSES:
        objective_output = obj(y_a, y_b)
        self.assertListEqual(objective_output.get_shape().as_list(), [5, 6])

  def test_objective_shapes_2d(self):
    with self.cached_session():
      y_a = keras.backend.variable(np.random.random((6, 7)))
      y_b = keras.backend.variable(np.random.random((6, 7)))
      for obj in ALL_LOSSES:
        objective_output = obj(y_a, y_b)
        self.assertListEqual(objective_output.get_shape().as_list(), [6,])

  def test_cce_one_hot(self):
    with self.cached_session():
      y_a = keras.backend.variable(np.random.randint(0, 7, (5, 6)))
      y_b = keras.backend.variable(np.random.random((5, 6, 7)))
      objective_output = keras.losses.sparse_categorical_crossentropy(y_a, y_b)
      assert keras.backend.eval(objective_output).shape == (5, 6)

      y_a = keras.backend.variable(np.random.randint(0, 7, (6,)))
      y_b = keras.backend.variable(np.random.random((6, 7)))
      objective_output = keras.losses.sparse_categorical_crossentropy(y_a, y_b)
      assert keras.backend.eval(objective_output).shape == (6,)

  @test_util.run_in_graph_and_eager_modes
  def test_categorical_crossentropy_loss(self):
    target = keras.backend.variable(np.random.randint(0, 1, (5, 1)))
    logits = keras.backend.variable(np.random.random((5, 1)))
    softmax_output = keras.backend.softmax(logits)
    output_from_logit = keras.losses.categorical_crossentropy(
        target, logits, from_logits=True)
    output_from_softmax = keras.losses.categorical_crossentropy(
        target, softmax_output)
    np.testing.assert_allclose(
        keras.backend.eval(output_from_logit),
        keras.backend.eval(output_from_softmax), atol=1e-5)

  @test_util.run_in_graph_and_eager_modes
  def test_sparse_categorical_crossentropy_loss(self):
    target = keras.backend.variable(np.random.randint(0, 1, (5, 1)))
    logits = keras.backend.variable(np.random.random((5, 1)))
    softmax_output = keras.backend.softmax(logits)
    output_from_logit = keras.losses.sparse_categorical_crossentropy(
        target, logits, from_logits=True)
    output_from_softmax = keras.losses.sparse_categorical_crossentropy(
        target, softmax_output)
    np.testing.assert_allclose(
        keras.backend.eval(output_from_logit),
        keras.backend.eval(output_from_softmax), atol=1e-5)

  @test_util.run_in_graph_and_eager_modes
  def test_binary_crossentropy_loss(self):
    target = keras.backend.variable(np.random.randint(0, 1, (5, 1)))
    logits = keras.backend.variable(np.random.random((5, 1)))
    sigmoid_output = keras.backend.sigmoid(logits)
    output_from_logit = keras.losses.binary_crossentropy(
        target, logits, from_logits=True)
    output_from_sigmoid = keras.losses.binary_crossentropy(
        target, sigmoid_output)
    np.testing.assert_allclose(
        keras.backend.eval(output_from_logit),
        keras.backend.eval(output_from_sigmoid), atol=1e-5)

  def test_serialization(self):
    fn = keras.losses.get('mse')
    config = keras.losses.serialize(fn)
    new_fn = keras.losses.deserialize(config)
    self.assertEqual(fn, new_fn)

  def test_categorical_hinge(self):
    y_pred = keras.backend.variable(np.array([[0.3, 0.2, 0.1],
                                              [0.1, 0.2, 0.7]]))
    y_true = keras.backend.variable(np.array([[0, 1, 0], [1, 0, 0]]))
    expected_loss = ((0.3 - 0.2 + 1) + (0.7 - 0.1 + 1)) / 2.0
    loss = keras.backend.eval(keras.losses.categorical_hinge(y_true, y_pred))
    self.assertAllClose(expected_loss, np.mean(loss))

  def test_serializing_loss_class(self):
    orig_loss_class = _MSEMAELoss(0.3)
    with keras.utils.custom_object_scope({'_MSEMAELoss': _MSEMAELoss}):
      serialized = keras.losses.serialize(orig_loss_class)

    with keras.utils.custom_object_scope({'_MSEMAELoss': _MSEMAELoss}):
      deserialized = keras.losses.deserialize(serialized)
    assert isinstance(deserialized, _MSEMAELoss)
    assert deserialized.mse_fraction == 0.3

  def test_serializing_model_with_loss_class(self):
    tmpdir = self.get_temp_dir()
    self.addCleanup(shutil.rmtree, tmpdir)
    model_filename = os.path.join(tmpdir, 'custom_loss.h5')

    with self.cached_session():
      with keras.utils.custom_object_scope({'_MSEMAELoss': _MSEMAELoss}):
        loss = _MSEMAELoss(0.3)
        inputs = keras.layers.Input((2,))
        outputs = keras.layers.Dense(1, name='model_output')(inputs)
        model = keras.models.Model(inputs, outputs)
        model.compile(optimizer='sgd', loss={'model_output': loss})
        model.fit(np.random.rand(256, 2), np.random.rand(256, 1))

        if h5py is None:
          return

        model.save(model_filename)

      with keras.utils.custom_object_scope({'_MSEMAELoss': _MSEMAELoss}):
        loaded_model = keras.models.load_model(model_filename)
        loaded_model.predict(np.random.rand(128, 2))


@test_util.run_all_in_graph_and_eager_modes
class MeanSquaredErrorTest(test.TestCase):

  def test_config(self):
    mse_obj = keras.losses.MeanSquaredError(
        reduction=losses_impl.ReductionV2.SUM, name='mse_1')
    self.assertEqual(mse_obj.name, 'mse_1')
    self.assertEqual(mse_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_all_correct_unweighted(self):
    mse_obj = keras.losses.MeanSquaredError()
    y_true = constant_op.constant([4, 8, 12, 8, 1, 3], shape=(2, 3))
    loss = mse_obj(y_true, y_true)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_unweighted(self):
    mse_obj = keras.losses.MeanSquaredError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mse_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 49.5, 3)

  def test_scalar_weighted(self):
    mse_obj = keras.losses.MeanSquaredError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mse_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 113.85, 3)

  def test_sample_weighted(self):
    mse_obj = keras.losses.MeanSquaredError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = mse_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 767.8 / 6, 3)

  def test_timestep_weighted(self):
    mse_obj = keras.losses.MeanSquaredError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = mse_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 587 / 6, 3)

  def test_zero_weighted(self):
    mse_obj = keras.losses.MeanSquaredError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mse_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_invalid_sample_weight(self):
    mse_obj = keras.losses.MeanSquaredError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3], shape=(2, 3, 1))
    sample_weight = constant_op.constant([3, 6, 5, 0], shape=(2, 2))
    with self.assertRaisesRegexp(
        ValueError, r'Shapes \(2, 2\) and \(2, 3\) are incompatible'):
      mse_obj(y_true, y_pred, sample_weight=sample_weight)

  def test_no_reduction(self):
    mse_obj = keras.losses.MeanSquaredError(
        reduction=losses_impl.ReductionV2.NONE)
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mse_obj(y_true, y_pred, sample_weight=2.3)
    loss = self.evaluate(loss)
    self.assertArrayNear(loss, [84.3333, 143.3666], 1e-3)

  def test_sum_reduction(self):
    mse_obj = keras.losses.MeanSquaredError(
        reduction=losses_impl.ReductionV2.SUM)
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mse_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 227.69998, 3)


@test_util.run_all_in_graph_and_eager_modes
class MeanAbsoluteErrorTest(test.TestCase):

  def test_config(self):
    mae_obj = keras.losses.MeanAbsoluteError(
        reduction=losses_impl.ReductionV2.SUM, name='mae_1')
    self.assertEqual(mae_obj.name, 'mae_1')
    self.assertEqual(mae_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_all_correct_unweighted(self):
    mae_obj = keras.losses.MeanAbsoluteError()
    y_true = constant_op.constant([4, 8, 12, 8, 1, 3], shape=(2, 3))
    loss = mae_obj(y_true, y_true)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_unweighted(self):
    mae_obj = keras.losses.MeanAbsoluteError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mae_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 5.5, 3)

  def test_scalar_weighted(self):
    mae_obj = keras.losses.MeanAbsoluteError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mae_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 12.65, 3)

  def test_sample_weighted(self):
    mae_obj = keras.losses.MeanAbsoluteError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = mae_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 81.4 / 6, 3)

  def test_timestep_weighted(self):
    mae_obj = keras.losses.MeanAbsoluteError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = mae_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 83 / 6, 3)

  def test_zero_weighted(self):
    mae_obj = keras.losses.MeanAbsoluteError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mae_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_invalid_sample_weight(self):
    mae_obj = keras.losses.MeanAbsoluteError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3], shape=(2, 3, 1))
    sample_weight = constant_op.constant([3, 6, 5, 0], shape=(2, 2))
    with self.assertRaisesRegexp(
        ValueError, r'Shapes \(2, 2\) and \(2, 3\) are incompatible'):
      mae_obj(y_true, y_pred, sample_weight=sample_weight)

  def test_no_reduction(self):
    mae_obj = keras.losses.MeanAbsoluteError(
        reduction=losses_impl.ReductionV2.NONE)
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mae_obj(y_true, y_pred, sample_weight=2.3)
    loss = self.evaluate(loss)
    self.assertArrayNear(loss, [10.7333, 14.5666], 1e-3)

  def test_sum_reduction(self):
    mae_obj = keras.losses.MeanAbsoluteError(
        reduction=losses_impl.ReductionV2.SUM)
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mae_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 25.29999, 3)


@test_util.run_all_in_graph_and_eager_modes
class MeanAbsolutePercentageErrorTest(test.TestCase):

  def test_config(self):
    mape_obj = keras.losses.MeanAbsolutePercentageError(
        reduction=losses_impl.ReductionV2.SUM, name='mape_1')
    self.assertEqual(mape_obj.name, 'mape_1')
    self.assertEqual(mape_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    mape_obj = keras.losses.MeanAbsolutePercentageError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mape_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 211.8518, 3)

  def test_scalar_weighted(self):
    mape_obj = keras.losses.MeanAbsolutePercentageError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mape_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 487.259, 3)

  def test_sample_weighted(self):
    mape_obj = keras.losses.MeanAbsolutePercentageError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = mape_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 422.8888, 3)

  def test_timestep_weighted(self):
    mape_obj = keras.losses.MeanAbsolutePercentageError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = mape_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 694.4445, 3)

  def test_zero_weighted(self):
    mape_obj = keras.losses.MeanAbsolutePercentageError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = mape_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)


@test_util.run_all_in_graph_and_eager_modes
class MeanSquaredLogarithmicErrorTest(test.TestCase):

  def test_config(self):
    msle_obj = keras.losses.MeanSquaredLogarithmicError(
        reduction=losses_impl.ReductionV2.SUM, name='mape_1')
    self.assertEqual(msle_obj.name, 'mape_1')
    self.assertEqual(msle_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    msle_obj = keras.losses.MeanSquaredLogarithmicError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = msle_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 1.4370, 3)

  def test_scalar_weighted(self):
    msle_obj = keras.losses.MeanSquaredLogarithmicError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = msle_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 3.3051, 3)

  def test_sample_weighted(self):
    msle_obj = keras.losses.MeanSquaredLogarithmicError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = msle_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 3.7856, 3)

  def test_timestep_weighted(self):
    msle_obj = keras.losses.MeanSquaredLogarithmicError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = msle_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 2.6473, 3)

  def test_zero_weighted(self):
    msle_obj = keras.losses.MeanSquaredLogarithmicError()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = msle_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)


@test_util.run_all_in_graph_and_eager_modes
class CosineProximityTest(test.TestCase):

  def test_config(self):
    cosine_obj = keras.losses.CosineProximity(
        reduction=losses_impl.ReductionV2.SUM, name='cosine_loss')
    self.assertEqual(cosine_obj.name, 'cosine_loss')
    self.assertEqual(cosine_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    cosine_obj = keras.losses.CosineProximity()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = cosine_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), -0.18722, 3)

  def test_scalar_weighted(self):
    cosine_obj = keras.losses.CosineProximity()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = cosine_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), -0.43060, 3)

  def test_sample_weighted(self):
    cosine_obj = keras.losses.CosineProximity()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = cosine_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 0.15599, 3)

  def test_timestep_weighted(self):
    cosine_obj = keras.losses.CosineProximity()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = cosine_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), -2.0000, 3)

  def test_zero_weighted(self):
    cosine_obj = keras.losses.CosineProximity()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = cosine_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


@test_util.run_all_in_graph_and_eager_modes
class BinaryCrossentropyTest(test.TestCase):

  def test_config(self):
    bce_obj = keras.losses.BinaryCrossentropy(
        reduction=losses_impl.ReductionV2.SUM, name='bce_1')
    self.assertEqual(bce_obj.name, 'bce_1')
    self.assertEqual(bce_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_all_correct_unweighted(self):
    y_true = constant_op.constant([[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                                  dtype=dtypes.float32)
    bce_obj = keras.losses.BinaryCrossentropy()
    loss = bce_obj(y_true, y_true)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

    # Test with logits.
    logits = constant_op.constant([[100.0, -100.0, -100.0],
                                   [-100.0, 100.0, -100.0],
                                   [-100.0, -100.0, 100.0]])
    bce_obj = keras.losses.BinaryCrossentropy(from_logits=True)
    loss = bce_obj(y_true, logits)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_unweighted(self):
    bce_obj = keras.losses.BinaryCrossentropy()
    y_true = constant_op.constant([1, 0, 1, 0, 0, 1], shape=(2, 3))
    y_pred = constant_op.constant([1, 1, 1, 0, 1, 0],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = bce_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 8.0004, 3)

    # Test with logits.
    logits = constant_op.constant([10., 10., 10., -10., 10, -10],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    bce_obj = keras.losses.BinaryCrossentropy(from_logits=True)
    loss = bce_obj(y_true, logits)
    self.assertAlmostEqual(self.evaluate(loss), 5., 3)

  def test_scalar_weighted(self):
    bce_obj = keras.losses.BinaryCrossentropy()
    y_true = constant_op.constant([1, 0, 1, 0, 0, 1], shape=(2, 3))
    y_pred = constant_op.constant([1, 1, 1, 0, 1, 0],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = bce_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 18.4010, 3)

    # Test with logits.
    y_true = array_ops.ones((32, 1))
    logits = array_ops.ones((32, 1), dtype=dtypes.float32)
    bce_obj = keras.losses.BinaryCrossentropy(from_logits=True)
    loss = bce_obj(y_true, logits, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 0.7205, 3)

  def test_sample_weighted(self):
    bce_obj = keras.losses.BinaryCrossentropy()
    y_true = constant_op.constant([1, 0, 1, 0, 0, 1], shape=(2, 3))
    y_pred = constant_op.constant([1, 1, 1, 0, 1, 0],
                                  shape=(2, 3),
                                  dtype=dtypes.float64)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = bce_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 21.4907, 3)

    # Test with logits.
    y_true = constant_op.constant([[0, 0, 1], [1, 0, 0], [0, 1, 0]])
    logits = constant_op.constant(
        [[100.0, -100.0, -100.0], [-100.0, 100.0, -100.0],
         [-100.0, -100.0, 100.0]],
        dtype=dtypes.float64)
    weights = constant_op.constant([3, 2, 8])
    bce_obj = keras.losses.BinaryCrossentropy(from_logits=True)
    loss = bce_obj(y_true, logits, sample_weight=weights)
    self.assertAlmostEqual(self.evaluate(loss), 288.8888, 3)

  def test_no_reduction(self):
    y_true = constant_op.constant(((1, 0, 1), (1, 1, 0), (0, 1, 1)))
    logits = constant_op.constant(((100.0, -100.0, 100.0),
                                   (100.0, -100.0, 100.0),
                                   (100.0, 100.0, -100.0)))
    bce_obj = keras.losses.BinaryCrossentropy(
        from_logits=True, reduction=losses_impl.ReductionV2.NONE)
    loss = bce_obj(y_true, logits)
    self.assertAllClose((0., 66.6666, 66.6666), self.evaluate(loss), 3)

  def test_label_smoothing(self):
    logits = constant_op.constant([[100.0, -100.0, -100.0]])
    y_true = constant_op.constant([[1, 0, 1]])
    label_smoothing = 0.1
    # Loss: max(x, 0) - x * z + log(1 + exp(-abs(x)))
    # Label smoothing: z' = z * (1 - L) + 0.5L
    #                  1  = 1 - 0.5L
    #                  0  = 0.5L
    # Applying the above two fns to the given input:
    # (100 - 100 * (1 - 0.5 L)  + 0 +
    #  0   + 100 * (0.5 L)      + 0 +
    #  0   + 100 * (1 - 0.5 L)  + 0) * (1/3)
    #  = (100 + 50L) * 1/3
    bce_obj = keras.losses.BinaryCrossentropy(
        from_logits=True, label_smoothing=label_smoothing)
    loss = bce_obj(y_true, logits)
    expected_value = (100.0 + 50.0 * label_smoothing) / 3.0
    self.assertAlmostEqual(self.evaluate(loss), expected_value, 3)


@test_util.run_all_in_graph_and_eager_modes
class CategoricalCrossentropyTest(test.TestCase):

  def test_config(self):
    cce_obj = keras.losses.CategoricalCrossentropy(
        reduction=losses_impl.ReductionV2.SUM, name='bce_1')
    self.assertEqual(cce_obj.name, 'bce_1')
    self.assertEqual(cce_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_all_correct_unweighted(self):
    y_true = constant_op.constant([[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                                  dtype=dtypes.int64)
    y_pred = constant_op.constant([[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                                  dtype=dtypes.float32)
    cce_obj = keras.losses.CategoricalCrossentropy()
    loss = cce_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

    # Test with logits.
    logits = constant_op.constant([[10., 0., 0.], [0., 10., 0.], [0., 0., 10.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_unweighted(self):
    cce_obj = keras.losses.CategoricalCrossentropy()
    y_true = constant_op.constant([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    y_pred = constant_op.constant(
        [[.9, .05, .05], [.5, .89, .6], [.05, .01, .94]], dtype=dtypes.float32)
    loss = cce_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), .3239, 3)

    # Test with logits.
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits)
    self.assertAlmostEqual(self.evaluate(loss), .0573, 3)

  def test_scalar_weighted(self):
    cce_obj = keras.losses.CategoricalCrossentropy()
    y_true = constant_op.constant([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    y_pred = constant_op.constant(
        [[.9, .05, .05], [.5, .89, .6], [.05, .01, .94]], dtype=dtypes.float32)
    loss = cce_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), .7449, 3)

    # Test with logits.
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), .1317, 3)

  def test_sample_weighted(self):
    cce_obj = keras.losses.CategoricalCrossentropy()
    y_true = constant_op.constant([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    y_pred = constant_op.constant(
        [[.9, .05, .05], [.5, .89, .6], [.05, .01, .94]], dtype=dtypes.float32)
    sample_weight = constant_op.constant([[1.2], [3.4], [5.6]], shape=(3, 1))
    loss = cce_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 1.0696, 3)

    # Test with logits.
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 0.31829, 3)

  def test_no_reduction(self):
    y_true = constant_op.constant([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(
        from_logits=True, reduction=losses_impl.ReductionV2.NONE)
    loss = cce_obj(y_true, logits)
    self.assertAllClose((0.001822, 0.000459, 0.169846), self.evaluate(loss), 3)

  def test_label_smoothing(self):
    logits = constant_op.constant([[100.0, -100.0, -100.0]])
    y_true = constant_op.constant([[1, 0, 0]])
    label_smoothing = 0.1
    # Softmax Cross Entropy Loss: -\sum_i p_i \log q_i
    # where for a softmax activation
    # \log q_i = x_i - \log \sum_j \exp x_j
    #          = x_i - x_max - \log \sum_j \exp (x_j - x_max)
    # For our activations, [100, -100, -100]
    # \log ( exp(0) + exp(-200) + exp(-200) ) = 0
    # so our log softmaxes become: [0, -200, -200]
    # Label smoothing: z' = z * (1 - L) + L/n
    #                  1  = 1 - L + L/n
    #                  0  = L/n
    # Applying the above two fns to the given input:
    # -0 * (1 - L + L/n) + 200 * L/n + 200 * L/n = 400 L/n
    cce_obj = keras.losses.CategoricalCrossentropy(
        from_logits=True, label_smoothing=label_smoothing)
    loss = cce_obj(y_true, logits)
    expected_value = 400.0 * label_smoothing / 3.0
    self.assertAlmostEqual(self.evaluate(loss), expected_value, 3)

  def test_all_correct_unweighted_sparse(self):
    y_true = constant_op.constant([[0], [1], [2]], dtype=dtypes.int64)
    y_pred = constant_op.constant([[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                                  dtype=dtypes.float32)
    cce_obj = keras.losses.CategoricalCrossentropy()
    loss = cce_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

    # Test with logits.
    logits = constant_op.constant([[10., 0., 0.], [0., 10., 0.], [0., 0., 10.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_unweighted_sparse(self):
    cce_obj = keras.losses.CategoricalCrossentropy()
    y_true = constant_op.constant([0, 1, 2])
    y_pred = constant_op.constant(
        [[.9, .05, .05], [.5, .89, .6], [.05, .01, .94]], dtype=dtypes.float32)
    loss = cce_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), .3239, 3)

    # Test with logits.
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits)
    self.assertAlmostEqual(self.evaluate(loss), .0573, 3)

  def test_scalar_weighted_sparse(self):
    cce_obj = keras.losses.CategoricalCrossentropy()
    y_true = constant_op.constant([[0], [1], [2]])
    y_pred = constant_op.constant(
        [[.9, .05, .05], [.5, .89, .6], [.05, .01, .94]], dtype=dtypes.float32)
    loss = cce_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), .7449, 3)

    # Test with logits.
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), .1317, 3)

  def test_sample_weighted_sparse(self):
    cce_obj = keras.losses.CategoricalCrossentropy()
    y_true = constant_op.constant([[0], [1], [2]])
    y_pred = constant_op.constant(
        [[.9, .05, .05], [.5, .89, .6], [.05, .01, .94]], dtype=dtypes.float32)
    sample_weight = constant_op.constant([[1.2], [3.4], [5.6]], shape=(3, 1))
    loss = cce_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 1.0696, 3)

    # Test with logits.
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(from_logits=True)
    loss = cce_obj(y_true, logits, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 0.31829, 3)

  def test_no_reduction_sparse(self):
    y_true = constant_op.constant([[0], [1], [2]])
    logits = constant_op.constant([[8., 1., 1.], [0., 9., 1.], [2., 3., 5.]])
    cce_obj = keras.losses.CategoricalCrossentropy(
        from_logits=True, reduction=losses_impl.ReductionV2.NONE)
    loss = cce_obj(y_true, logits)
    self.assertAllClose((0.001822, 0.000459, 0.169846), self.evaluate(loss), 3)


@test_util.run_all_in_graph_and_eager_modes
class HingeTest(test.TestCase):

  def test_config(self):
    hinge_obj = keras.losses.Hinge(
        reduction=losses_impl.ReductionV2.SUM, name='hinge_loss')
    self.assertEqual(hinge_obj.name, 'hinge_loss')
    self.assertEqual(hinge_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    hinge_obj = keras.losses.Hinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = hinge_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 7.3333, 3)

  def test_scalar_weighted(self):
    hinge_obj = keras.losses.Hinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = hinge_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 16.8666, 3)

    # Verify we get the same output when the same input is given
    loss_2 = hinge_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), self.evaluate(loss_2), 3)

  def test_sample_weighted(self):
    hinge_obj = keras.losses.Hinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = hinge_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 24.9333, 3)

  def test_timestep_weighted(self):
    hinge_obj = keras.losses.Hinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = hinge_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 2.0, 3)

  def test_zero_weighted(self):
    hinge_obj = keras.losses.Hinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = hinge_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


@test_util.run_all_in_graph_and_eager_modes
class SquaredHingeTest(test.TestCase):

  def test_config(self):
    sq_hinge_obj = keras.losses.SquaredHinge(
        reduction=losses_impl.ReductionV2.SUM, name='sq_hinge_loss')
    self.assertEqual(sq_hinge_obj.name, 'sq_hinge_loss')
    self.assertEqual(sq_hinge_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    sq_hinge_obj = keras.losses.SquaredHinge()
    y_true = constant_op.constant([1, 9, 2, -5], shape=(2, 2))
    y_pred = constant_op.constant([4, 8, 12, 8],
                                  shape=(2, 2),
                                  dtype=dtypes.float32)

    # Sq hinge = mean(square(max(1. - y_true * y_pred, 0.)), axis=-1)
    # (1. - y_true * y_pred) = [[1-4, 1-72], [1-24, 1+40]] = [0, 48]
    # sq(max(above val, 0)) = sq([[0, 0], [0, 41]) = [[0, 0], [0, 1681]]
    # Mean = [0, 840.5]. Reduced loss = (0 + 840.5)/2 = 420.25
    loss = sq_hinge_obj(y_true, y_pred)
    self.assertAlmostEqual(self.evaluate(loss), 420.25, 3)

  def test_scalar_weighted(self):
    sq_hinge_obj = keras.losses.SquaredHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = sq_hinge_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 647.833, 3)

    # Verify we get the same output when the same input is given
    loss_2 = sq_hinge_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), self.evaluate(loss_2), 3)

  def test_sample_weighted(self):
    sq_hinge_obj = keras.losses.SquaredHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = sq_hinge_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 957.667, 3)

  def test_timestep_weighted(self):
    sq_hinge_obj = keras.losses.SquaredHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = sq_hinge_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 6.0, 3)

  def test_zero_weighted(self):
    sq_hinge_obj = keras.losses.SquaredHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = sq_hinge_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


@test_util.run_all_in_graph_and_eager_modes
class CategoricalHingeTest(test.TestCase):

  def test_config(self):
    cat_hinge_obj = keras.losses.CategoricalHinge(
        reduction=losses_impl.ReductionV2.SUM, name='cat_hinge_loss')
    self.assertEqual(cat_hinge_obj.name, 'cat_hinge_loss')
    self.assertEqual(cat_hinge_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    cat_hinge_obj = keras.losses.CategoricalHinge()
    y_true = constant_op.constant([1, 9, 2, -5], shape=(2, 2))
    y_pred = constant_op.constant([4, 8, 12, 8],
                                  shape=(2, 2),
                                  dtype=dtypes.float32)
    loss = cat_hinge_obj(y_true, y_pred)

    # pos = reduce_sum(y_true * y_pred) = [1*4+8*9, 12*2+8*-5] = [76, -16]
    # neg = reduce_max((1. - y_true) * y_pred) = [[0, -64], [-12, 48]] = [0, 48]
    # cat_hinge = max(0., neg - pos + 1.) = [0, 65]
    # reduced_loss = (0 + 65)/2 = 32.5
    self.assertAlmostEqual(self.evaluate(loss), 32.5, 3)

  def test_scalar_weighted(self):
    cat_hinge_obj = keras.losses.CategoricalHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = cat_hinge_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), 83.95, 3)

    # Verify we get the same output when the same input is given
    loss_2 = cat_hinge_obj(y_true, y_pred, sample_weight=2.3)
    self.assertAlmostEqual(self.evaluate(loss), self.evaluate(loss_2), 3)

  def test_sample_weighted(self):
    cat_hinge_obj = keras.losses.CategoricalHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = cat_hinge_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 124.1, 3)

  def test_timestep_weighted(self):
    cat_hinge_obj = keras.losses.CategoricalHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3, 1))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3, 1),
                                  dtype=dtypes.float32)
    sample_weight = constant_op.constant([3, 6, 5, 0, 4, 2], shape=(2, 3))
    loss = cat_hinge_obj(y_true, y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 4.0, 3)

  def test_zero_weighted(self):
    cat_hinge_obj = keras.losses.CategoricalHinge()
    y_true = constant_op.constant([1, 9, 2, -5, -2, 6], shape=(2, 3))
    y_pred = constant_op.constant([4, 8, 12, 8, 1, 3],
                                  shape=(2, 3),
                                  dtype=dtypes.float32)
    loss = cat_hinge_obj(y_true, y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


@test_util.run_all_in_graph_and_eager_modes
class LogLossTest(test.TestCase):

  def setup(self):
    # TODO(psv): Change to setUp() after b/122319309 is fixed.
    y_pred = np.asarray([.9, .2, .2, .8, .4, .6]).reshape((2, 3))
    y_true = np.asarray([1., 0., 1., 1., 0., 0.]).reshape((2, 3))
    epsilon = 1e-7  # to avoid log 0

    self.batch_size = 6
    self.expected_losses = np.multiply(y_true, np.log(y_pred + epsilon))
    self.expected_losses += np.multiply(1 - y_true,
                                        np.log(1 - y_pred + epsilon))
    self.expected_losses = -self.expected_losses

    self.y_pred = constant_op.constant(y_pred)
    self.y_true = constant_op.constant(y_true)

  def test_config(self):
    log_loss_obj = keras.losses.LogLoss(
        reduction=losses_impl.ReductionV2.SUM, name='log')
    self.assertEqual(log_loss_obj.name, 'log')
    self.assertEqual(log_loss_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_all_correct(self):
    self.setup()
    log_loss_obj = keras.losses.LogLoss()
    loss = log_loss_obj(self.y_true, self.y_true)
    self.assertAlmostEqual(self.evaluate(loss), 0.0, 3)

  def test_unweighted(self):
    self.setup()
    log_loss_obj = keras.losses.LogLoss()
    loss = log_loss_obj(self.y_true, self.y_pred)
    actual_loss = np.sum(self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), actual_loss, 3)

  def test_scalar_weighted(self):
    self.setup()
    log_loss_obj = keras.losses.LogLoss()
    sample_weight = 2.3
    loss = log_loss_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    actual_loss = sample_weight * np.sum(self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), actual_loss, 3)

    # Verify we get the same output when the same input is given
    loss_2 = log_loss_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), self.evaluate(loss_2), 3)

  def test_sample_weighted(self):
    self.setup()
    log_loss_obj = keras.losses.LogLoss()
    sample_weight = constant_op.constant((1.2, 3.4), shape=(2, 1))

    loss = log_loss_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    actual_loss = np.multiply(
        self.expected_losses,
        np.asarray([1.2, 1.2, 1.2, 3.4, 3.4, 3.4]).reshape((2, 3)))
    actual_loss = np.sum(actual_loss) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), actual_loss, 3)

  def test_timestep_weighted(self):
    log_loss_obj = keras.losses.LogLoss()

    y_pred = np.asarray([.9, .2, .2, .8, .4, .6]).reshape((2, 3, 1))
    y_true = np.asarray([1., 0., 1., 1., 0., 0.]).reshape((2, 3, 1))
    epsilon = 1e-7  # to avoid log 0
    batch_size = 6

    expected_losses = np.multiply(y_true, np.log(y_pred + epsilon))
    expected_losses += np.multiply(1 - y_true, np.log(1 - y_pred + epsilon))

    y_pred = constant_op.constant(y_pred)
    y_true = constant_op.constant(y_true)
    sample_weight = np.array([3, 6, 5, 0, 4, 2]).reshape((2, 3, 1))
    loss = log_loss_obj(
        y_true,
        y_pred,
        sample_weight=constant_op.constant(sample_weight, shape=(2, 3)))
    actual_loss = np.multiply(-expected_losses, sample_weight)
    actual_loss = np.sum(actual_loss) / batch_size
    self.assertAlmostEqual(self.evaluate(loss), actual_loss, 3)

  def test_zero_weighted(self):
    self.setup()
    log_loss_obj = keras.losses.LogLoss()
    sample_weight = 0
    loss = log_loss_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


@test_util.run_all_in_graph_and_eager_modes
class LogcoshTest(test.TestCase):

  def setup(self):
    y_pred = np.asarray([1, 9, 2, -5, -2, 6]).reshape((2, 3))
    y_true = np.asarray([4, 8, 12, 8, 1, 3]).reshape((2, 3))

    self.batch_size = 6
    error = y_pred - y_true
    self.expected_losses = np.log((np.exp(error) + np.exp(-error)) / 2)

    self.y_pred = constant_op.constant(y_pred, dtype=dtypes.float32)
    self.y_true = constant_op.constant(y_true)

  def test_config(self):
    logcosh_obj = keras.losses.Logcosh(
        reduction=losses_impl.ReductionV2.SUM, name='logcosh_loss')
    self.assertEqual(logcosh_obj.name, 'logcosh_loss')
    self.assertEqual(logcosh_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    self.setup()
    logcosh_obj = keras.losses.Logcosh()

    loss = logcosh_obj(self.y_true, self.y_pred)
    expected_loss = np.sum(self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_scalar_weighted(self):
    self.setup()
    logcosh_obj = keras.losses.Logcosh()
    sample_weight = 2.3

    loss = logcosh_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    expected_loss = sample_weight * np.sum(
        self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

    # Verify we get the same output when the same input is given
    loss_2 = logcosh_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), self.evaluate(loss_2), 3)

  def test_sample_weighted(self):
    self.setup()
    logcosh_obj = keras.losses.Logcosh()

    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = logcosh_obj(self.y_true, self.y_pred, sample_weight=sample_weight)

    expected_loss = np.multiply(
        self.expected_losses,
        np.asarray([1.2, 1.2, 1.2, 3.4, 3.4, 3.4]).reshape((2, 3)))
    expected_loss = np.sum(expected_loss) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_timestep_weighted(self):
    self.setup()
    logcosh_obj = keras.losses.Logcosh()
    y_true = np.asarray([1, 9, 2, -5, -2, 6]).reshape(2, 3, 1)
    y_pred = np.asarray([4, 8, 12, 8, 1, 3]).reshape(2, 3, 1)
    error = y_pred - y_true
    expected_losses = np.log((np.exp(error) + np.exp(-error)) / 2)
    sample_weight = np.array([3, 6, 5, 0, 4, 2]).reshape((2, 3, 1))

    y_pred = constant_op.constant(y_pred, dtype=dtypes.float32)
    y_true = constant_op.constant(y_true)
    loss = logcosh_obj(
        y_true,
        y_pred,
        sample_weight=constant_op.constant(sample_weight, shape=(2, 3)))
    expected_loss = np.sum(expected_losses * sample_weight) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_zero_weighted(self):
    self.setup()
    logcosh_obj = keras.losses.Logcosh()
    sample_weight = 0
    loss = logcosh_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


@test_util.run_all_in_graph_and_eager_modes
class PoissonTest(test.TestCase):

  def setup(self):
    self.np_y_pred = np.asarray([1, 9, 2, 5, 2, 6]).reshape((2, 3))
    self.np_y_true = np.asarray([4, 8, 12, 8, 1, 3]).reshape((2, 3))

    self.batch_size = 6
    self.expected_losses = self.np_y_pred - np.multiply(self.np_y_true,
                                                        np.log(self.np_y_pred))

    self.y_pred = constant_op.constant(self.np_y_pred, dtype=dtypes.float32)
    self.y_true = constant_op.constant(self.np_y_true)

  def test_config(self):
    poisson_obj = keras.losses.Poisson(
        reduction=losses_impl.ReductionV2.SUM, name='poisson')
    self.assertEqual(poisson_obj.name, 'poisson')
    self.assertEqual(poisson_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    self.setup()
    poisson_obj = keras.losses.Poisson()

    loss = poisson_obj(self.y_true, self.y_pred)
    expected_loss = np.sum(self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_scalar_weighted(self):
    self.setup()
    poisson_obj = keras.losses.Poisson()
    sample_weight = 2.3
    loss = poisson_obj(self.y_true, self.y_pred, sample_weight=sample_weight)

    expected_loss = sample_weight * np.sum(
        self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

    # Verify we get the same output when the same input is given
    loss_2 = poisson_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), self.evaluate(loss_2), 3)

  def test_sample_weighted(self):
    self.setup()
    poisson_obj = keras.losses.Poisson()

    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = poisson_obj(self.y_true, self.y_pred, sample_weight=sample_weight)

    expected_loss = np.multiply(
        self.expected_losses,
        np.asarray([1.2, 1.2, 1.2, 3.4, 3.4, 3.4]).reshape((2, 3)))
    expected_loss = np.sum(expected_loss) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_timestep_weighted(self):
    self.setup()
    poisson_obj = keras.losses.Poisson()
    y_true = self.np_y_true.reshape(2, 3, 1)
    y_pred = self.np_y_pred.reshape(2, 3, 1)
    sample_weight = np.asarray([3, 6, 5, 0, 4, 2]).reshape(2, 3, 1)
    expected_losses = y_pred - np.multiply(y_true, np.log(y_pred))

    y_pred = constant_op.constant(y_pred, dtype=dtypes.float32)
    y_true = constant_op.constant(y_true)

    loss = poisson_obj(
        y_true,
        y_pred,
        sample_weight=constant_op.constant(sample_weight, shape=(2, 3)))
    expected_loss = np.sum(expected_losses * sample_weight) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_zero_weighted(self):
    self.setup()
    poisson_obj = keras.losses.Poisson()
    loss = poisson_obj(self.y_true, self.y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


@test_util.run_all_in_graph_and_eager_modes
class KullbackLeiblerDivergenceTest(test.TestCase):

  def setup(self):
    self.np_y_pred = np.asarray([.4, .9, .12, .36, .3, .4]).reshape((2, 3))
    self.np_y_true = np.asarray([.5, .8, .12, .7, .43, .8]).reshape((2, 3))

    self.batch_size = 2
    self.expected_losses = np.multiply(self.np_y_true,
                                       np.log(self.np_y_true / self.np_y_pred))

    self.y_pred = constant_op.constant(self.np_y_pred, dtype=dtypes.float32)
    self.y_true = constant_op.constant(self.np_y_true)

  def test_config(self):
    k_obj = keras.losses.KullbackLeiblerDivergence(
        reduction=losses_impl.ReductionV2.SUM, name='kld')
    self.assertEqual(k_obj.name, 'kld')
    self.assertEqual(k_obj.reduction, losses_impl.ReductionV2.SUM)

  def test_unweighted(self):
    self.setup()
    k_obj = keras.losses.KullbackLeiblerDivergence()

    loss = k_obj(self.y_true, self.y_pred)
    expected_loss = np.sum(self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_scalar_weighted(self):
    self.setup()
    k_obj = keras.losses.KullbackLeiblerDivergence()
    sample_weight = 2.3

    loss = k_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    expected_loss = sample_weight * np.sum(
        self.expected_losses) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

    # Verify we get the same output when the same input is given
    loss_2 = k_obj(self.y_true, self.y_pred, sample_weight=sample_weight)
    self.assertAlmostEqual(self.evaluate(loss), self.evaluate(loss_2), 3)

  def test_sample_weighted(self):
    self.setup()
    k_obj = keras.losses.KullbackLeiblerDivergence()
    sample_weight = constant_op.constant([1.2, 3.4], shape=(2, 1))
    loss = k_obj(self.y_true, self.y_pred, sample_weight=sample_weight)

    expected_loss = np.multiply(
        self.expected_losses,
        np.asarray([1.2, 1.2, 1.2, 3.4, 3.4, 3.4]).reshape(2, 3))
    expected_loss = np.sum(expected_loss) / self.batch_size
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_timestep_weighted(self):
    self.setup()
    k_obj = keras.losses.KullbackLeiblerDivergence()
    y_true = self.np_y_true.reshape(2, 3, 1)
    y_pred = self.np_y_pred.reshape(2, 3, 1)
    sample_weight = np.asarray([3, 6, 5, 0, 4, 2]).reshape(2, 3)
    expected_losses = np.sum(
        np.multiply(y_true, np.log(y_true / y_pred)), axis=-1)

    y_pred = constant_op.constant(y_pred, dtype=dtypes.float32)
    y_true = constant_op.constant(y_true)
    loss = k_obj(
        y_true, y_pred, sample_weight=constant_op.constant(sample_weight))

    num_timesteps = 3
    expected_loss = np.sum(expected_losses * sample_weight) / (
        self.batch_size * num_timesteps)
    self.assertAlmostEqual(self.evaluate(loss), expected_loss, 3)

  def test_zero_weighted(self):
    self.setup()
    k_obj = keras.losses.KullbackLeiblerDivergence()
    loss = k_obj(self.y_true, self.y_pred, sample_weight=0)
    self.assertAlmostEqual(self.evaluate(loss), 0., 3)


if __name__ == '__main__':
  test.main()
